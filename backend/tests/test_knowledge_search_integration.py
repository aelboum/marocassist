"""Integration tests for the search pipeline (Phase 3 WP C) against a real
PostgreSQL 16: term expansion, title and keyword matching, language
handling, the partial-match pass and the statement timeout.

The fixture bundle is published with the loader, with its Arabic text
approved and two extra terms, so every language is searchable. Search runs
under the application role (the default SaaS-OS session factory).
"""

from __future__ import annotations

import json
import os
import shutil
import uuid
from collections.abc import Iterator
from datetime import date
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import Engine

pytestmark = pytest.mark.integration

VALID = Path(__file__).parent / "fixtures" / "knowledge" / "valid"
TODAY = date(2026, 11, 21)
PASSPORT = "fixture.passport-renewal"
VISIT = "fixture.consulate-visit"


def _ar(*codes: int) -> str:
    return "".join(chr(c) for c in codes)


JAWAZ = _ar(0x062C, 0x0648, 0x0627, 0x0632)  # passport (singular)
JAWAZAT = _ar(0x062C, 0x0648, 0x0627, 0x0632, 0x0627, 0x062A)  # passports (broken plural)


@pytest.fixture(scope="module", autouse=True)
def _migrated() -> None:
    from marocassist.migrate import migrate

    migrate()


@pytest.fixture(scope="module")
def admin() -> Iterator[Engine]:
    engine = sa.create_engine(os.environ["MIGRATIONS_DATABASE_URL"])
    yield engine
    engine.dispose()


def _clear(admin: Engine) -> None:
    from marocassist.knowledge.loader import WRITE_ORDER

    with admin.begin() as conn:
        for table in reversed(WRITE_ORDER):
            conn.execute(sa.text(f"DELETE FROM marocassist.{table}"))
        conn.execute(
            sa.text(
                "DELETE FROM marocassist.knowledge_publications"
                " WHERE content_version LIKE 'sha256:%'"
            )
        )


def _bundle_root(tmp: Path) -> Path:
    root = tmp / "bundle"
    shutil.copytree(VALID, root)
    item_path = root / "items" / f"{PASSPORT}.json"
    item = json.loads(item_path.read_text(encoding="utf-8"))
    item["texts"]["ar"]["lang_status"] = "published"
    item["texts"]["ar"]["review"] = {
        "author": "ed-fixture-author",
        "approver": "ed-fixture-reviewer",
        "approved_at": "2026-11-02",
    }
    item_path.write_bytes(json.dumps(item, ensure_ascii=False, indent=2).encode("utf-8"))
    terms_path = root / "terms.json"
    terms = json.loads(terms_path.read_text(encoding="utf-8"))
    terms["terms"] += [
        {"term": JAWAZ, "lang": "ar", "canonical_key": "passport", "kind": "synonym"},
        {"term": "passeport", "lang": "fr", "canonical_key": "passport", "kind": "synonym"},
    ]
    terms_path.write_bytes(json.dumps(terms, ensure_ascii=False, indent=2).encode("utf-8"))
    return root


@pytest.fixture(scope="module")
def published(admin: Engine, tmp_path_factory: pytest.TempPathFactory) -> Iterator[None]:
    from saas_os.core.identity import get_or_create_user_for_external_identity
    from saas_os.infra.db import build_engine, build_session_factory, get_migrations_database_config

    from marocassist.accounts.provisioning import ensure_personal_workspace
    from marocassist.knowledge.loader import check, publish

    user = get_or_create_user_for_external_identity(
        "http://zitadel.localhost:8081", f"test-search-{uuid.uuid4().hex}"
    )
    tenant_id, _created = ensure_personal_workspace(user.id)
    _clear(admin)
    bundle = check(_bundle_root(tmp_path_factory.mktemp("search")), today=TODAY)
    engine = build_engine(get_migrations_database_config())
    try:
        publish(bundle, tenant_id=tenant_id, session_factory=build_session_factory(engine))
    finally:
        engine.dispose()
    yield
    _clear(admin)


def _search(query: str, ui_lang: str = "nl", **kwargs: object) -> list[str]:
    from marocassist.knowledge.retrieval import search

    result = search(query, ui_lang=ui_lang, today=TODAY, **kwargs)  # type: ignore[arg-type]
    return [scored.hit.item_id for scored in result.hits]


@pytest.mark.usefixtures("published")
def test_a_title_or_keyword_only_query_finds_the_item() -> None:
    from marocassist.knowledge.retrieval import search

    # "verlengen" is only in the Dutch title and keywords, not in the body;
    # the match must be a full one, not the partial fallback.
    best = search("paspoort verlengen", ui_lang="nl", today=TODAY).hits[0]
    assert best.hit.item_id == PASSPORT
    assert not best.partial
    assert PASSPORT in _search("vernieuwen")


@pytest.mark.usefixtures("published")
def test_french_without_accents_finds_accented_text() -> None:
    assert PASSPORT in _search("carte identite", ui_lang="fr")
    assert PASSPORT in _search("empreintes", ui_lang="fr")


@pytest.mark.usefixtures("published")
def test_the_detected_query_language_is_searched_after_the_ui_language() -> None:
    from marocassist.knowledge.retrieval import search

    # The fixture has no English text: a French question from the English UI
    # is answered from the French text.
    result = search("Comment renouveler mon passeport ?", ui_lang="en", today=TODAY)
    assert result.query.langs == ("en", "fr")
    assert PASSPORT in [s.hit.item_id for s in result.hits]
    assert {s.hit.lang for s in result.hits} == {"fr"}


@pytest.mark.usefixtures("published")
def test_arabic_broken_plural_is_found_through_the_term_table() -> None:
    from marocassist.knowledge.fts import expand_terms, search_session

    with search_session() as session:
        assert JAWAZ in expand_terms(session, [JAWAZAT], ["ar"])[JAWAZAT]
    assert PASSPORT in _search(JAWAZAT, ui_lang="ar")


@pytest.mark.usefixtures("published")
def test_transliteration_variants_expand_by_trigram() -> None:
    from marocassist.knowledge.fts import expand_terms, search_session

    with search_session() as session:
        expansions = expand_terms(session, ["kefala", "xy"], ["nl"])
    assert expansions == {"kefala": ["kafala"]}


@pytest.mark.usefixtures("published")
def test_expansion_stays_in_the_query_languages() -> None:
    from marocassist.knowledge.fts import expand_terms, search_session

    with search_session() as session:
        nl = expand_terms(session, ["paspoort"], ["nl"])
        both = expand_terms(session, ["paspoort"], ["nl", "fr"])
    assert nl == {}
    assert both == {"paspoort": ["passeport"]}


@pytest.mark.usefixtures("published")
def test_an_unknown_extra_word_falls_back_to_a_partial_match() -> None:
    from marocassist.knowledge.retrieval import search

    result = search("paspoort zzqqxx", ui_lang="nl", today=TODAY)
    assert result.hits
    assert result.hits[0].hit.item_id == PASSPORT
    assert all(s.partial for s in result.hits)
    assert _search("zzqqxx") == []


@pytest.mark.usefixtures("published")
def test_consulate_scope_and_withdrawn_items() -> None:
    assert VISIT in _search("consulaat bezoek", consulate="nl-rotterdam")
    assert VISIT not in _search("consulaat bezoek", consulate="nl-utrecht")
    assert "fixture.old-passport-procedure" not in _search("paspoort procedure")


@pytest.mark.usefixtures("published")
@pytest.mark.parametrize(
    "query",
    ["", "   ", '"', "or or or", "paspoort & | ! ( ) :* <-> \\", "a" * 10_000, "\u202e\u200b"],
)
def test_hostile_or_empty_queries_return_quietly(query: str) -> None:
    assert len(_search(query)) <= 6


def test_search_statements_are_bounded_by_the_timeout() -> None:
    from marocassist.knowledge.fts import SearchTimeout, search_session

    with search_session() as session:
        assert session.execute(sa.text("SHOW statement_timeout")).scalar_one() == "200ms"
    with pytest.raises(SearchTimeout), search_session() as session:
        session.execute(sa.text("SELECT pg_sleep(1)"))
