"""Red-team suite (Phase 3 WP G; security review section 3, control 8).

Every attack in tests/fixtures/knowledge/redteam.json (visible, hidden,
metadata, bidi, homoglyph, delimiter, URL and XSS vectors, in EN, FR, NL, AR
and Darija) must be refused by the entry sanitiser, and refused again by the
loader in every kind of text field it reads: item titles and bodies, source
titles and editorial notes, citation locators, fact and consulate values,
and search terms. Every benign text must pass both, so the rules do not
block ordinary procedural language.

The evidence pack (WP H) escapes the same texts a second time; its tests
reuse this fixture.
"""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from marocassist.knowledge.content import ContentRejectedError, read_bundle
from marocassist.knowledge.sanitise import check_text
from marocassist.knowledge.validate import validate_bundle

FIXTURES = Path(__file__).parent / "fixtures" / "knowledge"
VALID = FIXTURES / "valid"
TODAY = date(2026, 11, 21)
PASSPORT = "items/fixture.passport-renewal.json"

REDTEAM: dict[str, Any] = json.loads((FIXTURES / "redteam.json").read_text(encoding="utf-8"))
ATTACKS: list[dict[str, Any]] = REDTEAM["attacks"]
BENIGN: list[dict[str, Any]] = REDTEAM["benign"]

Json = Any
Place = Callable[[Json, str], None]


def _nl_title(d: Json, text: str) -> None:
    d["texts"]["nl"]["title"] = text


def _nl_body(d: Json, text: str) -> None:
    d["texts"]["nl"]["body"] = text


def _locator(d: Json, text: str) -> None:
    d["citations"][0]["locator"] = text


def _source_title(d: Json, text: str) -> None:
    d[0]["title"] = text


def _source_notes(d: Json, text: str) -> None:
    d[0]["notes"] = text


def _fact_value(d: Json, text: str) -> None:
    d[0]["value"] = {"amount": 300, "note": text}


def _attribute_value(d: Json, text: str) -> None:
    d[0]["attributes"][1]["value"] = text


def _term(d: Json, text: str) -> None:
    d["terms"][0]["term"] = text


PLACEMENTS: dict[str, tuple[str, Place]] = {
    "item title": (PASSPORT, _nl_title),
    "item body": (PASSPORT, _nl_body),
    "citation locator": (PASSPORT, _locator),
    "source title (metadata)": ("sources.json", _source_title),
    "source notes": ("sources.json", _source_notes),
    "fact value": ("facts.json", _fact_value),
    "consulate value": ("consulates.json", _attribute_value),
    "search term": ("terms.json", _term),
}


def _codes_after(tmp_path: Path, file: str, place: Place, text: str) -> set[str]:
    root = tmp_path / "bundle"
    shutil.copytree(VALID, root)
    path = root / file
    data = json.loads(path.read_text(encoding="utf-8"))
    place(data, text)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    try:
        bundle = read_bundle(root)
    except ContentRejectedError as exc:
        return {p.code for p in exc.problems}
    return {p.code for p in validate_bundle(bundle, today=TODAY)}


def test_the_fixture_covers_every_vector_and_language() -> None:
    assert {a["vector"] for a in ATTACKS} >= {
        "visible",
        "hidden",
        "metadata",
        "bidi",
        "homoglyph",
        "delimiter",
        "url",
        "xss",
    }
    visible = {a["lang"] for a in ATTACKS if a["vector"] == "visible"}
    assert visible >= {"en", "fr", "nl", "ar", "ary"}
    ids = [c["id"] for c in ATTACKS + BENIGN]
    assert len(ids) == len(set(ids))


@pytest.mark.parametrize("attack", ATTACKS, ids=[a["id"] for a in ATTACKS])
def test_the_sanitiser_refuses_every_attack(attack: dict[str, Any]) -> None:
    _normalised, findings = check_text(attack["text"], multiline=True)
    assert set(attack["expect"]) <= {f.code for f in findings}


@pytest.mark.parametrize("benign", BENIGN, ids=[b["id"] for b in BENIGN])
def test_the_sanitiser_passes_benign_text(benign: dict[str, Any]) -> None:
    normalised, findings = check_text(benign["text"], multiline=True)
    assert findings == []
    assert normalised == benign["text"]


def test_finding_messages_never_repeat_the_text() -> None:
    for attack in ATTACKS:
        _normalised, findings = check_text(attack["text"], multiline=True)
        for finding in findings:
            assert attack["text"] not in finding.message


@pytest.mark.parametrize("placement", sorted(PLACEMENTS))
@pytest.mark.parametrize("attack", ATTACKS, ids=[a["id"] for a in ATTACKS])
def test_the_loader_refuses_every_attack_in_every_field(
    attack: dict[str, Any], placement: str, tmp_path: Path
) -> None:
    file, place = PLACEMENTS[placement]
    assert "unsafe_text" in _codes_after(tmp_path, file, place, attack["text"])


@pytest.mark.parametrize("benign", BENIGN, ids=[b["id"] for b in BENIGN])
def test_the_loader_accepts_benign_text_in_a_body(benign: dict[str, Any], tmp_path: Path) -> None:
    assert _codes_after(tmp_path, PASSPORT, _nl_body, benign["text"]) == set()
