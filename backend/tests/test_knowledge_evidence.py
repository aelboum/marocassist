"""Unit tests for the evidence pack (Phase 3 WP H): limits, labels, source
cards, statuses and notices, and the fence: every red-team attack placed in
any text the pack carries stays inert data in a well-formed pack."""

from __future__ import annotations

import json
import unicodedata
import xml.etree.ElementTree as ET
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest

from marocassist.knowledge import evidence, sanitise
from marocassist.knowledge.catalogue import FactOut, FactValue, SourceCard
from marocassist.knowledge.fts import ChunkHit

TODAY = date(2026, 11, 21)
NOW = datetime(2026, 11, 21, 12, 0, tzinfo=UTC)
REDTEAM = json.loads(
    (Path(__file__).parent / "fixtures" / "knowledge" / "redteam.json").read_text(encoding="utf-8")
)["attacks"]

OFFICIAL = {
    "source_id": "src-fixture-official",
    "title": "Fixture: official page",
    "publisher": "MAECAMRE",
    "source_type": "official",
    "geo_scope": "global",
    "verified_at": "2026-11-01",
    "review_due_at": "2027-04-30",
    "status": "verified",
    "official_url": "https://www.consulat.ma/fr/passeport-biometrique",
}
SECONDARY = {
    **OFFICIAL,
    "source_id": "src-fixture-secondary",
    "title": "Fixture: a blog",
    "publisher": "Blog",
    "source_type": "secondary",
    "official_url": "https://www.example-blog.nl/paspoort",
}


def _hit(item_id: str, body: str = "Maak een afspraak.", **overrides: Any) -> ChunkHit:
    values: dict[str, Any] = {
        "item_id": item_id,
        "lang": "nl",
        "ordinal": 0,
        "heading": None,
        "kind": "procedure",
        "status": "published",
        "review_due_at": date(2027, 4, 30),
        "source_rank": 1,
        "rank": 0.5,
        "body": body,
    }
    values.update(overrides)
    return ChunkHit(**values)


def _doc(
    item_id: str, *, sources: list[dict[str, Any]] | None = None, **extra: Any
) -> dict[str, Any]:
    doc: dict[str, Any] = {
        "item_id": item_id,
        "status": "published",
        "country_scope": ["NL"],
        "consulate_scope": [],
        "texts": [{"lang": "nl", "title": f"Titel {item_id}", "verified_at": "2026-11-01"}],
        "sources": [OFFICIAL] if sources is None else sources,
    }
    doc.update(extra)
    return doc


def _card(source: dict[str, Any]) -> SourceCard:
    return SourceCard(
        label=1,
        source_id=source["source_id"],
        title=source["title"],
        publisher=source["publisher"],
        badge="official",
        scope="global",
        verified_at=date(2026, 11, 1),
        status="current",
        url=source["official_url"],
    )


def _fact(
    key: str, *values: tuple[str, Any, str], status: str = "current", needs: bool = False
) -> FactOut:
    return FactOut(
        fact_key=key,
        consulate=None,
        scope="global" if values else None,
        status=status if values else None,  # type: ignore[arg-type]
        needs_consulate=needs,
        consulates=["nl-rotterdam"] if needs else [],
        values=[
            FactValue(
                fact_id=fact_id,
                scope="global",
                value=value,
                unit="MAD",
                status=value_status,  # type: ignore[arg-type]
                valid_from=date(2026, 1, 1),
                valid_until=None,
                verified_at=date(2026, 11, 1),
                sources=[_card(OFFICIAL)],
            )
            for fact_id, value, value_status in values
        ],
    )


def _pack(
    hits: list[ChunkHit], docs: dict[str, dict[str, Any]], facts: Any = ()
) -> evidence.EvidencePack:
    return evidence.assemble(hits, docs, facts, lang="nl", consulate=None, today=TODAY, now=NOW)


def _parse(pack: evidence.EvidencePack) -> ET.Element:
    return ET.fromstring(pack.render())  # noqa: S314 - our own output, not untrusted XML


# --- Assembly ----------------------------------------------------------------------


def test_sources_are_labelled_in_rank_order_and_cards_are_shared() -> None:
    docs = {"it-a": _doc("it-a"), "it-b": _doc("it-b")}
    pack = _pack([_hit("it-a"), _hit("it-b")], docs, [_fact("fee.x.y", ("f.1", 300, "current"))])
    assert [s.label for s in pack.sources] == ["S1", "S2"]
    assert [s.item_id for s in pack.sources] == ["it-a", "it-b"]
    assert [f.label for f in pack.facts] == ["F1"]
    assert [c.label for c in pack.cards] == [1]  # one register source, one card
    assert pack.sources[0].cards == ("C1",)
    assert pack.facts[0].cards == ("C1",)
    assert pack.labels == {"S1", "S2", "F1"}
    assert pack.allowed_urls == {OFFICIAL["official_url"]}
    assert pack.notices == frozenset()


def test_at_most_six_sources_and_a_text_budget() -> None:
    docs = {f"it-{n}": _doc(f"it-{n}") for n in range(9)}
    many = _pack([_hit(f"it-{n}") for n in range(9)], docs)
    assert len(many.sources) == evidence.MAX_SOURCES
    long_body = ("woord " * 600).strip()
    big = _pack([_hit(f"it-{n}", long_body) for n in range(4)], docs)
    total = sum(len(s.text) for s in big.sources)
    assert total <= evidence.MAX_EVIDENCE_CHARS + len(big.sources)
    assert big.sources[-1].text.endswith("\u2026")


def test_withdrawn_or_missing_items_and_other_languages_are_skipped() -> None:
    docs = {"it-a": _doc("it-a", status="withdrawn"), "it-c": _doc("it-c")}
    pack = _pack([_hit("it-a"), _hit("it-b"), _hit("it-c", lang="fr"), _hit("it-c")], docs)
    assert [(s.label, s.item_id) for s in pack.sources] == [("S1", "it-c")]


def test_statuses_become_notices() -> None:
    docs = {"it-old": _doc("it-old"), "it-blog": _doc("it-blog", sources=[SECONDARY])}
    pack = _pack(
        [_hit("it-old", review_due_at=date(2026, 11, 1)), _hit("it-blog")],
        docs,
        [
            _fact("fee.a.b", ("f.1", 20, "current"), ("f.2", 25, "current"), status="conflict"),
            _fact("fee.c.d", ("f.3", 75, "expired"), status="expired"),
            _fact("fee.e.f", ("f.4", 5, "under_review"), status="under_review"),
        ],
    )
    assert pack.sources[0].status == "expired"
    assert pack.sources[1].secondary_only
    assert pack.sources[1].rank == "secondary"
    assert pack.notices == {"expired", "secondary_only", "conflict", "under_review"}
    assert [f.label for f in pack.facts] == ["F1", "F2", "F3", "F4"]


def test_a_consulate_only_fact_asks_which_consulate() -> None:
    pack = _pack([], {}, [_fact("fee.consular_card.adult", needs=True), None])
    assert pack.needs_clarification
    assert pack.clarify_consulate == ("nl-rotterdam",)
    assert pack.empty  # no values: the answer must ask, not state
    clarify = _parse(pack).find("clarify")
    assert clarify is not None
    assert clarify.get("consulates") == "nl-rotterdam"


def test_the_rendered_pack_is_well_formed_and_complete() -> None:
    docs = {"it-a": _doc("it-a", consulate_scope=["nl-rotterdam"])}
    pack = _pack(
        [_hit("it-a", heading="Voorbereiding")], docs, [_fact("fee.x.y", ("f.1", 300, "current"))]
    )
    root = _parse(pack)
    assert root.tag == "evidence"
    assert root.get("version") == "2026-11-21T12:00:00Z"
    source = root.find("source")
    assert source is not None
    assert dict(source.attrib) == {
        "id": "S1",
        "item": "it-a",
        "rank": "official",
        "status": "current",
        "verified": "2026-11-01",
        "scope": "consulate:nl-rotterdam",
        "lang": "nl",
        "title": "Titel it-a",
        "heading": "Voorbereiding",
        "cards": "C1",
    }
    assert source.text == "Maak een afspraak."
    fact = root.find("fact")
    assert fact is not None
    assert (fact.get("value"), fact.get("unit")) == ("300", "MAD")
    card = root.find("card")
    assert card is not None
    assert card.get("url") == OFFICIAL["official_url"]


# --- The fence (red team) ----------------------------------------------------------

_HIDDEN_CATEGORIES = frozenset({"Cc", "Cf", "Cs", "Co", "Cn", "Zl", "Zp"})


def _hidden(char: str) -> bool:
    return char != "\n" and (
        char in sanitise.BIDI_CONTROLS
        or char in sanitise.ZERO_WIDTH
        or char in sanitise.INVISIBLE
        or unicodedata.category(char) in _HIDDEN_CATEGORIES
    )


@pytest.mark.parametrize("attack", REDTEAM, ids=[a["id"] for a in REDTEAM])
def test_every_attack_stays_data_inside_the_pack(attack: dict[str, Any]) -> None:
    text = attack["text"]
    doc = _doc("it-a")
    doc["texts"][0]["title"] = text
    doc["sources"] = [{**OFFICIAL, "title": text, "publisher": text}]
    pack = _pack(
        [_hit("it-a", body=text, heading=text)],
        {"it-a": doc},
        [_fact("fee.x.y", ("f.1", {"amount": 1, "note": text}, "current"))],
    )
    rendered = pack.render()
    assert not [f"U+{ord(c):04X}" for c in rendered if _hidden(c)]
    assert rendered.count("</evidence>") == 1
    root = ET.fromstring(rendered)  # noqa: S314 - still one well-formed pack
    assert [child.tag for child in root] == ["source", "fact", "card"]  # one shared register card
    source = root.find("source")
    assert source is not None
    assert len(source) == 0  # no element smuggled inside
    assert source.text == text.strip()
    assert source.get("title") == text
    assert source.get("heading") == text
    fact = root.find("fact")
    assert fact is not None
    assert json.loads(fact.get("value") or "")["note"] == text
    hostile_card = root.findall("card")[0]
    assert hostile_card.get("title") == text
    assert hostile_card.get("publisher") == text


def test_escape_handles_markup_and_hidden_characters() -> None:
    assert evidence.escape('<a href="x">&</a>') == "&lt;a href=&quot;x&quot;&gt;&amp;&lt;/a&gt;"
    assert evidence.escape("a\u202eb\u200bc\nd") == "a&#x202E;b&#x200B;c\nd"
