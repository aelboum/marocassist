"""The database side of knowledge search (Phase 3 WP C).

The only runtime module allowed to import SQLAlchemy, and only `func`
(tests/test_unit.py checks this with the AST): it calls the two SQL
functions from migration 0003, `knowledge_search()` and
`knowledge_expand_terms()`, with bound parameters. It never builds SQL text.

Every statement runs under the application role, in a transaction whose
statements are bounded by a 200 ms timeout (security review T-6). A timeout
is raised as `SearchTimeout`.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date
from typing import Any

from saas_os.infra.db import (
    OperationalError,
    Session,
    is_statement_timeout,
    select,
    session_scope,
    set_local_statement_timeout,
)
from sqlalchemy import func

STATEMENT_TIMEOUT_MS = 200

_SEARCH_COLUMNS = (
    "item_id",
    "lang",
    "ordinal",
    "heading",
    "kind",
    "status",
    "review_due_at",
    "source_rank",
    "rank",
)


class SearchTimeout(Exception):
    """A search statement ran longer than STATEMENT_TIMEOUT_MS."""


@dataclass(frozen=True)
class ChunkHit:
    item_id: str
    lang: str
    ordinal: int
    heading: str | None
    kind: str
    status: str
    review_due_at: date
    source_rank: int
    rank: float


@contextmanager
def search_session(*, session_factory: Any = None) -> Iterator[Session]:
    """A read transaction with the statement timeout already set."""
    with session_scope(session_factory=session_factory) as session:
        set_local_statement_timeout(session, STATEMENT_TIMEOUT_MS)
        try:
            yield session
        except OperationalError as error:
            if is_statement_timeout(error):
                raise SearchTimeout from error
            raise


def expand_terms(
    session: Session, words: Sequence[str], langs: Sequence[str]
) -> Mapping[str, list[str]]:
    """Related terms per query word, from `knowledge_terms`."""
    if not words:
        return {}
    fn = func.marocassist.knowledge_expand_terms(list(words), list(langs)).table_valued(
        "word", "term"
    )
    expansions: dict[str, list[str]] = {}
    for row in session.execute(select(fn.c.word, fn.c.term)):
        expansions.setdefault(row.word, []).append(row.term)
    return expansions


def search_chunks(
    session: Session,
    tsquery: str,
    langs: Sequence[str],
    *,
    country: str,
    consulate: str | None = None,
    kinds: Sequence[str] | None = None,
    limit: int = 6,
) -> list[ChunkHit]:
    """`knowledge_search()`: filters, caps and the base rank are in SQL."""
    if not tsquery:
        return []
    fn = func.marocassist.knowledge_search(
        tsquery,
        list(langs),
        country,
        consulate,
        list(kinds) if kinds is not None else None,
        limit,
    ).table_valued(*_SEARCH_COLUMNS)
    rows = session.execute(select(*(fn.c[name] for name in _SEARCH_COLUMNS)))
    return [
        ChunkHit(
            item_id=row.item_id,
            lang=row.lang,
            ordinal=int(row.ordinal),
            heading=row.heading,
            kind=row.kind,
            status=row.status,
            review_due_at=row.review_due_at,
            source_rank=int(row.source_rank),
            rank=float(row.rank),
        )
        for row in rows
    ]
