"""Golden-set evaluation of knowledge search and facts (Phase 3 WP G;
architecture section 8; exit criteria 1 and 4).

A golden set lists questions per language with the item ids a good answer
must find, and fact lookups with the exact value and status they must give.
`evaluate` runs them through the same catalogue functions the API uses and
measures:

- **recall@6** and **MRR** per language, on the items a user sees;
- **fact accuracy**: status and the exact (value, unit) set, including the
  clarifying question when a fee exists per consulate only;
- **stale leakage**: an expired item or fact shown as current, or a
  withdrawn or out-of-force row shown at all. Which rows are stale comes
  from the published bundle (`Freshness.from_bundle`), not from the code
  under test, so a bug in the read-time expiry cannot hide itself;
- search latency per language (p95), reported but not gated: CI runners are
  too noisy for a time limit, and the target (< 300 ms) is for production.

The module is pure apart from the clock: the caller supplies the search and
fact functions, so the same harness runs on fixture content in CI and on the
editors' golden set later. The report holds case ids, item ids and numbers,
never query text.
"""

from __future__ import annotations

import json
import math
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Annotated, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, StringConstraints, model_validator

from marocassist.knowledge.catalogue import FactOut, SearchOut
from marocassist.knowledge.content import Bundle

K: Final = 6
RECALL_AT_K_MIN: Final = 0.85
FACT_ACCURACY_MIN: Final = 1.0
LANGS: Final = ("nl", "fr", "ar", "en")
LATENCY_TARGET_MS: Final = 300.0

CaseId = Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9._-]{1,60}$")]
ItemId = Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9.-]{1,79}$")]
FactExpectation = Literal[
    "current", "expired", "conflict", "under_review", "needs_consulate", "absent"
]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SearchCase(_Model):
    id: CaseId
    lang: Literal["nl", "fr", "ar", "en"]
    query: Annotated[str, StringConstraints(min_length=1, max_length=1000)]
    consulate: str | None = None
    expect: list[ItemId] = Field(min_length=1)
    note: str | None = None


class FactCase(_Model):
    id: CaseId
    fact_key: str
    consulate: str | None = None
    expect_status: FactExpectation
    expect_values: list[tuple[JsonValue, str | None]] = Field(default_factory=list)
    note: str | None = None


class GoldenSet(_Model):
    format: Literal[1]
    about: str | None = None
    today: date
    search: list[SearchCase] = Field(min_length=1)
    facts: list[FactCase] = Field(default_factory=list)

    @model_validator(mode="after")
    def _unique_ids(self) -> GoldenSet:
        ids = [c.id for c in self.search] + [c.id for c in self.facts]
        if len(ids) != len(set(ids)):
            raise ValueError("case ids must be unique")
        return self


def load_golden(path: Path) -> GoldenSet:
    return GoldenSet.model_validate_json(path.read_text(encoding="utf-8"))


# --- Ground truth from the bundle ------------------------------------------------


@dataclass(frozen=True)
class Freshness:
    """What must never be shown as current on `today`, computed from the
    published bundle."""

    stale_items: frozenset[str] = frozenset()
    withdrawn_items: frozenset[str] = frozenset()
    stale_facts: frozenset[str] = frozenset()
    hidden_facts: frozenset[str] = frozenset()  # withdrawn or not in force

    @classmethod
    def from_bundle(cls, bundle: Bundle, today: date) -> Freshness:
        return cls(
            stale_items=frozenset(
                i.item_id
                for i in bundle.items
                if i.status == "published" and i.review_due_at < today
            ),
            withdrawn_items=frozenset(i.item_id for i in bundle.items if i.status == "withdrawn"),
            stale_facts=frozenset(
                f.fact_id
                for f in bundle.facts
                if f.status != "withdrawn" and f.review_due_at < today
            ),
            hidden_facts=frozenset(
                f.fact_id
                for f in bundle.facts
                if f.status == "withdrawn"
                or f.valid_from > today
                or (f.valid_until is not None and f.valid_until < today)
            ),
        )


# --- Metrics ---------------------------------------------------------------------


def ranked_items(out: SearchOut) -> list[str]:
    """Item ids in the order the user sees them, each once."""
    return list(dict.fromkeys(r.item_id for r in out.results))


def recall_at_k(expected: Sequence[str], ranked: Sequence[str], k: int = K) -> float:
    wanted = set(expected)
    return len(wanted & set(ranked[:k])) / len(wanted)


def reciprocal_rank(expected: Sequence[str], ranked: Sequence[str]) -> float:
    wanted = set(expected)
    for position, item_id in enumerate(ranked, start=1):
        if item_id in wanted:
            return 1.0 / position
    return 0.0


def p95(values: Sequence[float]) -> float:
    """Nearest-rank 95th percentile; 0 for no values."""
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[max(0, math.ceil(0.95 * len(ordered)) - 1)]


def search_leaks(case_id: str, out: SearchOut, freshness: Freshness) -> list[str]:
    leaks = []
    for result in out.results:
        if result.item_id in freshness.withdrawn_items:
            leaks.append(f"{case_id}: withdrawn item {result.item_id} returned")
        elif result.item_id in freshness.stale_items and result.status != "expired":
            leaks.append(f"{case_id}: stale item {result.item_id} shown as {result.status}")
    return leaks


def fact_leaks(case_id: str, out: FactOut | None, freshness: Freshness) -> list[str]:
    if out is None:
        return []
    leaks = []
    for value in out.values:
        if value.fact_id in freshness.hidden_facts:
            leaks.append(f"{case_id}: withdrawn or out-of-force fact {value.fact_id} returned")
        elif value.fact_id in freshness.stale_facts and value.status != "expired":
            leaks.append(f"{case_id}: stale fact {value.fact_id} shown as {value.status}")
    if out.status == "current" and any(v.fact_id in freshness.stale_facts for v in out.values):
        leaks.append(f"{case_id}: fact {out.fact_key} shown as current with a stale value")
    return leaks


def _value_set(pairs: Sequence[tuple[JsonValue, str | None]]) -> list[str]:
    return sorted(json.dumps([value, unit], sort_keys=True) for value, unit in pairs)


def fact_correct(case: FactCase, out: FactOut | None) -> bool:
    if case.expect_status == "absent":
        return out is None or (not out.values and not out.needs_consulate)
    if out is None:
        return False
    if case.expect_status == "needs_consulate":
        return out.needs_consulate and not out.values
    return out.status == case.expect_status and _value_set(
        [(v.value, v.unit) for v in out.values]
    ) == _value_set(case.expect_values)


# --- Report ----------------------------------------------------------------------


@dataclass(frozen=True)
class LanguageScore:
    lang: str
    cases: int
    recall_at_k: float
    mrr: float
    p95_ms: float
    misses: list[str]


@dataclass(frozen=True)
class Report:
    today: date
    languages: list[LanguageScore]
    facts_total: int
    facts_correct: int
    clarifications_total: int
    clarifications_correct: int
    fact_failures: list[str]
    leaks: list[str]
    k: int = K

    @property
    def fact_accuracy(self) -> float:
        return self.facts_correct / self.facts_total if self.facts_total else 1.0

    def failures(self) -> list[str]:
        """Every exit-criterion threshold this report misses."""
        problems = []
        scored = {s.lang: s for s in self.languages}
        for lang in LANGS:
            score = scored.get(lang)
            if score is None or score.cases == 0:
                problems.append(f"{lang}: no golden questions")
            elif score.recall_at_k < RECALL_AT_K_MIN:
                problems.append(
                    f"{lang}: recall@{self.k} {score.recall_at_k:.2f} < {RECALL_AT_K_MIN:.2f}"
                )
        if self.fact_accuracy < FACT_ACCURACY_MIN:
            problems.append(f"fact accuracy {self.fact_accuracy:.2f} < {FACT_ACCURACY_MIN:.2f}")
        if self.leaks:
            problems.append(f"stale leakage {len(self.leaks)} > 0")
        return problems


SearchFn = Callable[[SearchCase], SearchOut]
FactFn = Callable[[FactCase], FactOut | None]


def evaluate(
    golden: GoldenSet,
    *,
    search: SearchFn,
    fact: FactFn,
    freshness: Freshness,
    clock: Callable[[], float] = time.perf_counter,
) -> Report:
    leaks: list[str] = []
    languages = []
    for lang in LANGS:
        cases = [c for c in golden.search if c.lang == lang]
        recalls: list[float] = []
        ranks: list[float] = []
        timings: list[float] = []
        misses: list[str] = []
        for case in cases:
            started = clock()
            out = search(case)
            timings.append((clock() - started) * 1000)
            ranked = ranked_items(out)
            recall = recall_at_k(case.expect, ranked)
            recalls.append(recall)
            ranks.append(reciprocal_rank(case.expect, ranked))
            if recall < 1:
                misses.append(f"{case.id}: got {', '.join(ranked[:K]) or 'nothing'}")
            leaks.extend(search_leaks(case.id, out, freshness))
        languages.append(
            LanguageScore(
                lang=lang,
                cases=len(cases),
                recall_at_k=sum(recalls) / len(recalls) if recalls else 0.0,
                mrr=sum(ranks) / len(ranks) if ranks else 0.0,
                p95_ms=p95(timings),
                misses=misses,
            )
        )
    correct = clarifications = clarified = 0
    fact_failures = []
    for fact_case in golden.facts:
        found = fact(fact_case)
        ok = fact_correct(fact_case, found)
        correct += ok
        if fact_case.expect_status == "needs_consulate":
            clarifications += 1
            clarified += ok
        if not ok:
            got = "nothing" if found is None else f"{found.status}, {len(found.values)} value(s)"
            fact_failures.append(f"{fact_case.id}: expected {fact_case.expect_status}, got {got}")
        leaks.extend(fact_leaks(fact_case.id, found, freshness))
    return Report(
        today=golden.today,
        languages=languages,
        facts_total=len(golden.facts),
        facts_correct=correct,
        clarifications_total=clarifications,
        clarifications_correct=clarified,
        fact_failures=fact_failures,
        leaks=leaks,
    )


def render_markdown(report: Report) -> str:
    lines = [
        f"## Knowledge evaluation ({report.today.isoformat()})",
        "",
        f"| Language | Questions | recall@{report.k} | MRR | p95 search (ms) |",
        "|---|---:|---:|---:|---:|",
    ]
    lines += [
        f"| {s.lang} | {s.cases} | {s.recall_at_k:.2f} | {s.mrr:.2f} | {s.p95_ms:.0f} |"
        for s in report.languages
    ]
    lines += [
        "",
        f"- Fact accuracy: {report.facts_correct}/{report.facts_total}"
        f" ({report.fact_accuracy:.2f})",
        "- Clarifying question when a consulate is needed:"
        f" {report.clarifications_correct}/{report.clarifications_total}",
        f"- Stale leakage: {len(report.leaks)}",
        f"- Thresholds: recall@{report.k} >= {RECALL_AT_K_MIN:.2f} per language,"
        f" fact accuracy {FACT_ACCURACY_MIN:.2f}, stale leakage 0;"
        f" the p95 target < {LATENCY_TARGET_MS:.0f} ms is informational in CI",
    ]
    failures = report.failures()
    lines += ["", "**Result: " + ("FAIL" if failures else "pass") + "**"]
    details = (
        failures
        + [m for s in report.languages for m in s.misses]
        + report.fact_failures
        + report.leaks
    )
    if details:
        lines += ["", *(f"- {d}" for d in details)]
    return "\n".join(lines) + "\n"
