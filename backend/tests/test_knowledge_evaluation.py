"""Unit tests for the golden-set harness (Phase 3 WP G): the metrics, the
thresholds and the leakage checks on crafted results, and the consistency
of the fixture golden set with the evaluation corpus. No database; the real
run is in test_knowledge_eval_integration.py."""

from __future__ import annotations

from datetime import date
from itertools import count
from pathlib import Path
from typing import Any

import pytest

from marocassist.knowledge import evaluation as ev
from marocassist.knowledge.catalogue import FactOut, FactValue, SearchOut, SearchResultOut
from marocassist.knowledge.content import read_bundle
from marocassist.knowledge.loader import check

FIXTURES = Path(__file__).parent / "fixtures" / "knowledge"
CORPUS = FIXTURES / "eval"
GOLDEN = ev.load_golden(FIXTURES / "golden.json")
TODAY = GOLDEN.today


def _result(item_id: str, status: str = "current") -> SearchResultOut:
    return SearchResultOut(
        item_id=item_id,
        lang="nl",
        ordinal=0,
        kind="procedure",
        status=status,  # type: ignore[arg-type]
        partial=False,
        title="t",
        heading=None,
        snippet="s",
        sources=[],
    )


def _out(*results: SearchResultOut) -> SearchOut:
    return SearchOut(langs=["nl"], detected_lang=None, results=list(results))


def _value(fact_id: str, value: Any, status: str = "current") -> FactValue:
    return FactValue(
        fact_id=fact_id,
        scope="global",
        value=value,
        unit="MAD",
        status=status,  # type: ignore[arg-type]
        valid_from=date(2026, 1, 1),
        valid_until=None,
        verified_at=date(2026, 11, 1),
        sources=[],
    )


def _fact(status: str | None, *values: FactValue, needs_consulate: bool = False) -> FactOut:
    return FactOut(
        fact_key="fee.x.y",
        consulate=None,
        scope="global" if values else None,
        status=status,  # type: ignore[arg-type]
        needs_consulate=needs_consulate,
        consulates=[],
        values=list(values),
    )


def _case(case_id: str, lang: str, *expect: str) -> ev.SearchCase:
    return ev.SearchCase(id=case_id, lang=lang, query="q", expect=list(expect))  # type: ignore[arg-type]


def _golden(*cases: ev.SearchCase, facts: tuple[ev.FactCase, ...] = ()) -> ev.GoldenSet:
    return ev.GoldenSet(format=1, today=TODAY, search=list(cases), facts=list(facts))


# --- Metrics ---------------------------------------------------------------------


def test_recall_and_reciprocal_rank() -> None:
    ranked = ["it-a", "it-b", "c", "d", "e", "f", "g"]
    assert ev.recall_at_k(["c"], ranked) == 1.0
    assert ev.recall_at_k(["g"], ranked) == 0.0  # rank 7 is outside the top 6
    assert ev.recall_at_k(["it-a", "g"], ranked) == 0.5
    assert ev.reciprocal_rank(["c"], ranked) == pytest.approx(1 / 3)
    assert ev.reciprocal_rank(["z"], ranked) == 0.0


def test_ranked_items_count_each_item_once() -> None:
    out = _out(_result("it-a"), _result("it-a"), _result("it-b"))
    assert ev.ranked_items(out) == ["it-a", "it-b"]


def test_p95_is_nearest_rank() -> None:
    assert ev.p95([]) == 0.0
    assert ev.p95([5.0]) == 5.0
    assert ev.p95([float(n) for n in range(1, 101)]) == 95.0


def test_fact_correctness_needs_exact_values_and_status() -> None:
    current = ev.FactCase(
        id="fc-1", fact_key="fee.x.y", expect_status="current", expect_values=[(300, "MAD")]
    )
    assert ev.fact_correct(current, _fact("current", _value("it-a", 300)))
    assert not ev.fact_correct(current, _fact("current", _value("it-a", 300.5)))
    assert not ev.fact_correct(current, _fact("expired", _value("it-a", 300)))
    assert not ev.fact_correct(current, _fact("current", _value("it-a", 300), _value("it-b", 300)))
    assert not ev.fact_correct(current, None)
    ask = ev.FactCase(id="fc-2", fact_key="fee.x.y", expect_status="needs_consulate")
    assert ev.fact_correct(ask, _fact(None, needs_consulate=True))
    assert not ev.fact_correct(ask, _fact("current", _value("it-a", 1)))
    absent = ev.FactCase(id="fc-3", fact_key="fee.x.y", expect_status="absent")
    assert ev.fact_correct(absent, None)
    assert not ev.fact_correct(absent, _fact(None, needs_consulate=True))


# --- Leakage ---------------------------------------------------------------------


FRESHNESS = ev.Freshness(
    stale_items=frozenset({"old"}),
    withdrawn_items=frozenset({"gone"}),
    stale_facts=frozenset({"f.old"}),
    hidden_facts=frozenset({"f.gone"}),
)


def test_search_leaks_are_stale_as_current_or_withdrawn_at_all() -> None:
    assert ev.search_leaks("c", _out(_result("old", "expired")), FRESHNESS) == []
    assert ev.search_leaks("c", _out(_result("old", "current")), FRESHNESS)
    assert ev.search_leaks("c", _out(_result("gone", "expired")), FRESHNESS)


def test_fact_leaks() -> None:
    assert ev.fact_leaks("c", _fact("expired", _value("f.old", 1, "expired")), FRESHNESS) == []
    assert ev.fact_leaks("c", _fact("expired", _value("f.old", 1, "current")), FRESHNESS)
    assert ev.fact_leaks("c", _fact("current", _value("f.gone", 1)), FRESHNESS)
    assert ev.fact_leaks("c", None, FRESHNESS) == []


# --- Report ----------------------------------------------------------------------


def _all_languages(found: str) -> list[ev.SearchCase]:
    return [_case(f"{lang}-1", lang, found) for lang in ev.LANGS]


def test_a_perfect_run_passes() -> None:
    report = ev.evaluate(
        _golden(*_all_languages("it-a")),
        search=lambda case: _out(_result("it-a")),
        fact=lambda case: None,
        freshness=ev.Freshness(),
    )
    assert report.failures() == []
    assert "**Result: pass**" in ev.render_markdown(report)


def test_low_recall_a_missing_language_a_wrong_fact_and_a_leak_all_fail() -> None:
    cases = [_case("nl-1", "nl", "it-a"), _case("nl-2", "nl", "it-b"), _case("fr-1", "fr", "it-a")]
    cases += [_case("ar-1", "ar", "it-a")]
    wrong = ev.FactCase(
        id="f1", fact_key="fee.x.y", expect_status="current", expect_values=[(1, "MAD")]
    )
    report = ev.evaluate(
        _golden(*cases, facts=(wrong,)),
        search=lambda case: _out(_result("it-a"), _result("old", "current")),
        fact=lambda case: _fact("current", _value("f.x", 2)),
        freshness=FRESHNESS,
    )
    failures = report.failures()
    assert "nl: recall@6 0.50 < 0.85" in failures
    assert "en: no golden questions" in failures
    assert any(f.startswith("fact accuracy") for f in failures)
    assert any(f.startswith("stale leakage") for f in failures)
    markdown = ev.render_markdown(report)
    assert "**Result: FAIL**" in markdown
    assert "nl-2: got it-a, old" in markdown


def test_the_report_never_contains_query_text() -> None:
    case = ev.SearchCase(id="nl-1", lang="nl", query="geheime vraag", expect=["it-a"])
    report = ev.evaluate(
        _golden(case),
        search=lambda c: _out(_result("it-b")),
        fact=lambda c: None,
        freshness=ev.Freshness(),
    )
    assert "geheime" not in ev.render_markdown(report)


def test_latency_is_measured_per_question() -> None:
    ticks = count()
    report = ev.evaluate(
        _golden(*_all_languages("it-a")),
        search=lambda case: _out(_result("it-a")),
        fact=lambda case: None,
        freshness=ev.Freshness(),
        clock=lambda: next(ticks) * 0.25,  # every search takes 250 ms
    )
    assert {s.p95_ms for s in report.languages} == {250.0}


def test_duplicate_case_ids_are_refused() -> None:
    with pytest.raises(ValueError, match="unique"):
        _golden(_case("nl-1", "nl", "it-a"), _case("nl-1", "nl", "it-b"))


# --- The fixture golden set ------------------------------------------------------


def test_the_corpus_is_publishable_fixture_content() -> None:
    bundle = check(CORPUS, today=TODAY)
    assert all(i.item_id.startswith("fixture.") for i in bundle.items)
    assert all(s.title.startswith("Fixture:") for s in bundle.sources)


def test_the_golden_set_covers_every_language_and_refers_to_the_corpus() -> None:
    bundle = read_bundle(CORPUS)
    published = {i.item_id for i in bundle.items if i.status == "published"}
    per_lang = {lang: [c for c in GOLDEN.search if c.lang == lang] for lang in ev.LANGS}
    assert all(len(cases) >= 5 for cases in per_lang.values())
    for case in GOLDEN.search:
        assert set(case.expect) <= published, case.id
    fact_keys = {f.fact_key for f in bundle.facts}
    expectations = {c.expect_status for c in GOLDEN.facts}
    assert expectations >= {"current", "expired", "conflict", "needs_consulate", "absent"}
    for fact_case in GOLDEN.facts:
        assert fact_case.expect_status == "absent" or fact_case.fact_key in fact_keys


def test_the_corpus_has_stale_and_withdrawn_content_to_leak() -> None:
    freshness = ev.Freshness.from_bundle(read_bundle(CORPUS), TODAY)
    assert freshness.stale_items == {"fixture.eval.consular-card"}
    assert freshness.withdrawn_items == {"fixture.eval.old-consular-card"}
    assert freshness.stale_facts >= {"fixture.eval.fee.national-id.adult"}
    assert freshness.hidden_facts == {
        "fixture.eval.fee.passport.adult-2025",
        "fixture.eval.fee.passport.minor-withdrawn",
    }
    stale_queries = [c for c in GOLDEN.search if "fixture.eval.consular-card" in c.expect]
    assert stale_queries  # the stale item is actually searched for
