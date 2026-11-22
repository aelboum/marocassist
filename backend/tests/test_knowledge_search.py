"""Unit tests for the search pipeline (Phase 3 WP C): query preparation and
reranking. No database; the SQL side is in
test_knowledge_search_integration.py."""

from __future__ import annotations

import importlib.util
from datetime import date, timedelta
from pathlib import Path

import pytest

from marocassist.knowledge import normalise
from marocassist.knowledge.fts import ChunkHit
from marocassist.knowledge.retrieval import MAX_RESULTS, freshness, rerank, score

TODAY = date(2026, 11, 21)
MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "marocassist"
    / "migrations"
    / "versions"
    / "0003_knowledge.py"
)


def _ar(*codes: int) -> str:
    return "".join(chr(c) for c in codes)


JAWAZ = _ar(0x062C, 0x0648, 0x0627, 0x0632)  # passport, plain spelling


# --- Cleaning and tokenising -------------------------------------------------------


def test_arabic_folding_matches_the_sql_normaliser() -> None:
    spec = importlib.util.spec_from_file_location("migration_0003", MIGRATION)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    from_chars, to_chars = module.arabic_translate_args()
    assert from_chars == normalise.ARABIC_FROM + normalise.ARABIC_DELETED
    assert to_chars == normalise.ARABIC_TO


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # Diacritics and tatweel removed, alef with hamza unified.
        (_ar(0x062C, 0x064E, 0x0648, 0x0651, 0x0627, 0x0640, 0x0632), JAWAZ),
        (_ar(0x0623, 0x0625, 0x0622), _ar(0x0627, 0x0627, 0x0627)),
        (_ar(0x0663, 0x0660, 0x0660), "300"),
        # Bidi, zero-width and control characters become spaces.
        ("pas\u202espoort\u200b\u0000x", "pas spoort x"),
        # NFKC: full-width letters and ligatures.
        ("\uff50\uff41\uff53 \ufb01n", "pas fin"),
        ("  many   spaces\n\there ", "many spaces here"),
    ],
)
def test_clean(raw: str, expected: str) -> None:
    assert normalise.clean(raw) == expected


def test_clean_caps_the_query() -> None:
    assert len(normalise.clean("a" * 10_000)) == normalise.MAX_QUERY_CHARS


@pytest.mark.parametrize(
    ("text", "words"),
    [
        ("Paspoort verlengen?", ["paspoort", "verlengen"]),
        ("carte d'identit\u00e9", ["carte", "identit\u00e9"]),
        # websearch operators and quotes are separators, "or" is dropped.
        ('"paspoort" -kosten or prijs', ["paspoort", "kosten", "prijs"]),
        ("paspoort & | ! ( ) :* <-> \\", ["paspoort"]),
        ("a b 7 paspoort paspoort", ["7", "paspoort"]),
        ("", []),
    ],
)
def test_tokenise(text: str, words: list[str]) -> None:
    assert normalise.tokenise(text) == words


def test_tokenise_caps_the_number_of_words() -> None:
    text = " ".join(f"word{n}" for n in range(50))
    assert len(normalise.tokenise(text)) == normalise.MAX_WORDS


# --- Language detection ------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "lang"),
    [
        ("Hoe kan ik mijn paspoort verlengen?", "nl"),
        ("Comment renouveler mon passeport ?", "fr"),
        ("\u00e9tat civil", "fr"),
        ("How do I renew my passport?", "en"),
        (_ar(0x062A, 0x062C, 0x062F, 0x064A, 0x062F, 0x0020) + JAWAZ, "ar"),
        ("CNIE", None),
        ("123", None),
        ("", None),
    ],
)
def test_detect_language(text: str, lang: str | None) -> None:
    assert normalise.detect_language(text) == lang


def test_query_langs_put_the_ui_language_first() -> None:
    assert normalise.query_langs("nl", "fr") == ("nl", "fr")
    assert normalise.query_langs("fr", "fr") == ("fr",)
    assert normalise.query_langs("fr", None) == ("fr",)
    assert normalise.query_langs("xx", None) == ("nl",)


def test_prepare() -> None:
    prepared = normalise.prepare("Comment renouveler mon passeport ?", "nl")
    assert prepared.detected == "fr"
    assert prepared.langs == ("nl", "fr")
    assert prepared.words == ("comment", "renouveler", "mon", "passeport")


# --- tsquery building --------------------------------------------------------------


def test_build_tsquery_groups_alternatives_per_word() -> None:
    query = normalise.build_tsquery(
        ["paspoort", "afspraak"], {"paspoort": ["passeport", "jawaz safar"]}
    )
    assert query == 'paspoort or passeport or "jawaz safar" afspraak'
    loose = normalise.build_tsquery(["paspoort", "afspraak"], match_all=False)
    assert loose == "paspoort or afspraak"


def test_build_tsquery_neutralises_hostile_expansions() -> None:
    query = normalise.build_tsquery(["x1"], {"x1": ['ab" or -cd', "<->", "or", "x1"]})
    assert query == 'x1 or "ab cd"'


def test_build_tsquery_caps_alternatives() -> None:
    query = normalise.build_tsquery(["w"], {"w": [f"t{n}" for n in range(20)]})
    assert query.count(" or ") == normalise.MAX_ALTERNATIVES


# --- Reranking -----------------------------------------------------------------------


def _hit(
    item: str,
    ordinal: int = 0,
    *,
    rank: float = 1.0,
    status: str = "published",
    due: date = TODAY + timedelta(days=30),
    source_rank: int = 1,
) -> ChunkHit:
    return ChunkHit(item, "nl", ordinal, None, "procedure", status, due, source_rank, rank)


def test_freshness_decays_after_the_review_date_to_a_floor() -> None:
    assert freshness(TODAY, TODAY) == 1.0
    assert freshness(TODAY - timedelta(days=90), TODAY) == pytest.approx(0.5)
    assert freshness(TODAY - timedelta(days=45), TODAY) == pytest.approx(0.75)
    assert freshness(TODAY - timedelta(days=900), TODAY) == 0.5


def test_score_weights_status_freshness_and_source() -> None:
    assert score(_hit("a"), TODAY) == 1.0
    assert score(_hit("a", status="expired"), TODAY) == 0.5
    assert score(_hit("a", source_rank=2), TODAY) == pytest.approx(0.9)
    assert score(_hit("a", source_rank=3), TODAY) == 0.5
    assert score(_hit("a"), TODAY, partial=True) == 0.5


def test_rerank_prefers_full_matches_and_caps_per_item_and_total() -> None:
    strict = [_hit("a", 0, rank=0.4), _hit("a", 1, rank=0.3), _hit("a", 2, rank=0.2)]
    partial = [_hit("b", 0, rank=0.7), _hit("a", 0, rank=0.9)] + [
        _hit(f"c{n}", rank=0.1) for n in range(10)
    ]
    result = rerank(strict, partial, today=TODAY)
    assert len(result) == MAX_RESULTS
    ids = [(r.hit.item_id, r.hit.ordinal) for r in result]
    # Full matches first, even though partial b/0 (0.35) and the partial copy
    # of a/0 (0.45) score higher; a/0 keeps its full-match entry; a/2 is capped.
    assert ids[:3] == [("a", 0), ("a", 1), ("b", 0)]
    assert ("a", 2) not in ids
    assert not result[0].partial
    assert result[0].score == pytest.approx(0.4)


def test_rerank_drops_unknown_statuses_and_respects_the_limit() -> None:
    hits = [_hit("a", status="withdrawn"), _hit("b"), _hit("c", rank=0.5)]
    result = rerank(hits, [], today=TODAY, limit=1)
    assert [r.hit.item_id for r in result] == ["b"]
    assert len(rerank(hits, [], today=TODAY, limit=1000)) == 2
