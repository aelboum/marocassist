"""Knowledge search pipeline (Phase 3 WP C; search architecture section 4):
prepare the query, expand terms, search, rerank.

1. `normalise.prepare`: cap and clean the query, detect its language, pick
   the languages to search (UI language first).
2. `fts.expand_terms`: synonyms, plurals and transliterations that share a
   canonical key with a query word.
3. `fts.search_chunks` with every word required. When that finds fewer than
   `limit` chunks and the query has more than one word, a second pass needs
   any word; its hits are worth half, so a full match always ranks first.
4. Rerank in Python: `rank x w_status x w_fresh x w_source`, at most two
   chunks per item and at most six chunks in all.

Expired items stay findable but are flagged and ranked lower; withdrawn and
pending-review content never reaches this module (the SQL filters it).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any

from marocassist.knowledge import fts, normalise
from marocassist.knowledge.fts import ChunkHit, SearchTimeout

MAX_RESULTS = 6
MAX_CHUNKS_PER_ITEM = 2
PARTIAL_MATCH_WEIGHT = 0.5

W_STATUS = {"published": 1.0, "expired": 0.5}
W_SOURCE = {1: 1.0, 2: 0.9, 3: 0.5}
FRESHNESS_FLOOR = 0.5
FRESHNESS_DECAY_DAYS = 180

__all__ = ["Result", "ScoredHit", "SearchTimeout", "rerank", "search"]


@dataclass(frozen=True)
class ScoredHit:
    hit: ChunkHit
    score: float
    partial: bool


@dataclass(frozen=True)
class Result:
    query: normalise.PreparedQuery
    hits: tuple[ScoredHit, ...]


def freshness(review_due_at: date, today: date) -> float:
    """1.0 until the review date, then a linear decay to FRESHNESS_FLOOR."""
    overdue = (today - review_due_at).days
    if overdue <= 0:
        return 1.0
    return max(FRESHNESS_FLOOR, 1.0 - overdue / FRESHNESS_DECAY_DAYS)


def score(hit: ChunkHit, today: date, *, partial: bool = False) -> float:
    value = (
        hit.rank
        * W_STATUS.get(hit.status, 0.0)
        * freshness(hit.review_due_at, today)
        * W_SOURCE.get(hit.source_rank, W_SOURCE[3])
    )
    return value * PARTIAL_MATCH_WEIGHT if partial else value


def rerank(
    strict: Sequence[ChunkHit],
    partial: Sequence[ChunkHit],
    *,
    today: date,
    limit: int = MAX_RESULTS,
) -> tuple[ScoredHit, ...]:
    """Merge both passes, then cap per item and in total. Every full match
    ranks before every partial one; a chunk found by both passes keeps its
    full-match entry. Within each group the order is by score."""
    best: dict[tuple[str, str, int], ScoredHit] = {}
    for hits, is_partial in ((strict, False), (partial, True)):
        for hit in hits:
            key = (hit.item_id, hit.lang, hit.ordinal)
            if hit.status not in W_STATUS or key in best:
                continue
            best[key] = ScoredHit(hit, score(hit, today, partial=is_partial), is_partial)
    ordered = sorted(
        best.values(),
        key=lambda s: (s.partial, -s.score, s.hit.item_id, s.hit.lang, s.hit.ordinal),
    )
    per_item: dict[str, int] = {}
    kept: list[ScoredHit] = []
    cap = max(1, min(limit, MAX_RESULTS))
    for scored in ordered:
        count = per_item.get(scored.hit.item_id, 0)
        if count >= MAX_CHUNKS_PER_ITEM:
            continue
        per_item[scored.hit.item_id] = count + 1
        kept.append(scored)
        if len(kept) == cap:
            break
    return tuple(kept)


def search(
    query: str,
    *,
    ui_lang: str,
    country: str = "NL",
    consulate: str | None = None,
    kinds: Sequence[str] | None = None,
    limit: int = MAX_RESULTS,
    today: date | None = None,
    session_factory: Any = None,
) -> Result:
    """Search published knowledge. Raises `SearchTimeout` when a statement
    exceeds the timeout."""
    prepared = normalise.prepare(query, ui_lang)
    if not prepared.words:
        return Result(prepared, ())
    today = today or date.today()
    with fts.search_session(session_factory=session_factory) as session:
        expansions = fts.expand_terms(session, prepared.words, prepared.langs)
        options: dict[str, Any] = {
            "country": country,
            "consulate": consulate,
            "kinds": kinds,
            "limit": MAX_RESULTS,
        }
        strict = fts.search_chunks(
            session,
            normalise.build_tsquery(prepared.words, expansions),
            prepared.langs,
            **options,
        )
        loose: list[ChunkHit] = []
        if len(strict) < limit and len(prepared.words) > 1:
            loose = fts.search_chunks(
                session,
                normalise.build_tsquery(prepared.words, expansions, match_all=False),
                prepared.langs,
                **options,
            )
    return Result(prepared, rerank(strict, loose, today=today, limit=limit))
