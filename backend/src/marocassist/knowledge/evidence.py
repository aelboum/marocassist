"""Evidence pack and source cards (Phase 3 WP H; search architecture
section 5; security review section 3, control 4).

The evidence pack is the only knowledge that reaches the answer model in
Phase 4. It is built here, deterministically, from published knowledge:

- **Sources** `S1..S6`: the best chunks of the search, with item id,
  language, status (`current` or `expired`), the best source badge,
  whether every cited source is secondary (`secondary_only`), the
  verification date and the scope. At most `MAX_SOURCES` chunks and about
  `MAX_EVIDENCE_CHARS` characters of text in all.
- **Facts** `F1..`: one element per value of each requested fact key, with
  the fact-level status (a conflict shows every value, none as true).
- **Cards** `C1..`: the registered sources behind the sources and facts,
  built from the source register (never from model output). Their URLs are
  the only links an answer may contain (`allowed_urls`).

Editor-approved text is still untrusted data (owner decision 2026-11-20).
It already passed the entry sanitiser; `render` escapes it again: markup
characters become entities, and any bidi, invisible, control or separator
character that might slip through becomes a numeric reference, so no text
can close an element, open a new one, or hide characters. The policy that
says evidence is data, never instructions, lives in the Phase 4 system
message; this module only guarantees the fence.

`assemble` is pure (unit-tested with crafted content); `build_evidence`
fetches the content and calls it.
"""

from __future__ import annotations

import html
import json
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any, Final, Literal

from marocassist.knowledge import catalogue, fts, retrieval, sanitise
from marocassist.knowledge.catalogue import FactOut, SourceCard
from marocassist.knowledge.fts import ChunkHit

MAX_SOURCES: Final = 6
MAX_EVIDENCE_CHARS: Final = 6000
MIN_SOURCE_CHARS: Final = 200
MAX_FACT_KEYS: Final = 10

Notice = Literal["expired", "conflict", "secondary_only", "under_review"]
_BADGE_ORDER: Final = ("official", "explanation", "secondary")
_UNSAFE_CATEGORIES: Final = frozenset({"Cc", "Cf", "Cs", "Co", "Cn", "Zl", "Zp"})


@dataclass(frozen=True)
class EvidenceSource:
    label: str
    item_id: str
    lang: str
    title: str
    heading: str | None
    text: str
    status: Literal["current", "expired"]
    rank: str
    secondary_only: bool
    verified_at: date | None
    scope: str
    cards: tuple[str, ...]


@dataclass(frozen=True)
class EvidenceFact:
    label: str
    fact_key: str
    scope: str
    value: Any
    unit: str | None
    status: str
    value_status: str
    verified_at: date
    cards: tuple[str, ...]


@dataclass(frozen=True)
class EvidencePack:
    generated_at: datetime
    lang: str
    consulate: str | None
    sources: tuple[EvidenceSource, ...] = ()
    facts: tuple[EvidenceFact, ...] = ()
    cards: tuple[SourceCard, ...] = ()
    clarify_consulate: tuple[str, ...] = ()
    content_version: str | None = None
    labels: frozenset[str] = field(init=False)

    def __post_init__(self) -> None:
        labels = {s.label for s in self.sources} | {f.label for f in self.facts}
        object.__setattr__(self, "labels", frozenset(labels))

    @property
    def empty(self) -> bool:
        return not self.sources and not self.facts

    @property
    def needs_clarification(self) -> bool:
        """A requested fact exists per consulate only and no consulate was
        given: ask which one (architecture section 5, rule 6)."""
        return bool(self.clarify_consulate)

    @property
    def allowed_urls(self) -> frozenset[str]:
        return frozenset(c.url for c in self.cards if c.status != "withdrawn")

    @property
    def notices(self) -> frozenset[Notice]:
        """Statuses the answer must state (architecture section 5, rule 5)."""
        found: set[Notice] = set()
        for source in self.sources:
            if source.status == "expired":
                found.add("expired")
            if source.secondary_only:
                found.add("secondary_only")
        for fact in self.facts:
            if fact.status == "conflict":
                found.add("conflict")
            if fact.status == "under_review" or fact.value_status == "under_review":
                found.add("under_review")
            if fact.status == "expired" or fact.value_status == "expired":
                found.add("expired")
        return frozenset(found)

    def fact(self, label: str) -> EvidenceFact | None:
        return next((f for f in self.facts if f.label == label), None)

    def render(self) -> str:
        head = {
            "version": self.generated_at.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "lang": self.lang,
            "content_version": self.content_version,
        }
        lines = [f"<evidence{_attrs(head)}>"]
        for s in self.sources:
            attrs = {
                "id": s.label,
                "item": s.item_id,
                "rank": s.rank,
                "status": s.status,
                "secondary_only": "true" if s.secondary_only else None,
                "verified": s.verified_at.isoformat() if s.verified_at else None,
                "scope": s.scope,
                "lang": s.lang,
                "title": s.title,
                "heading": s.heading,
                "cards": ",".join(s.cards),
            }
            lines.append(f"<source{_attrs(attrs)}>{escape(s.text)}</source>")
        for f in self.facts:
            attrs = {
                "id": f.label,
                "key": f.fact_key,
                "scope": f.scope,
                "value": json.dumps(f.value, ensure_ascii=False, sort_keys=True),
                "unit": f.unit,
                "status": f.status,
                "value_status": f.value_status,
                "verified": f.verified_at.isoformat(),
                "cards": ",".join(f.cards),
            }
            lines.append(f"<fact{_attrs(attrs)}/>")
        for c in self.cards:
            attrs = {
                "id": f"C{c.label}",
                "publisher": c.publisher,
                "title": c.title,
                "badge": c.badge,
                "status": c.status,
                "url": c.url,
            }
            lines.append(f"<card{_attrs(attrs)}/>")
        if self.clarify_consulate:
            lines.append(f"<clarify{_attrs({'consulates': ','.join(self.clarify_consulate)})}/>")
        lines.append("</evidence>")
        return "\n".join(lines)


# --- Escaping --------------------------------------------------------------------


def _unsafe(char: str) -> bool:
    return (
        char in sanitise.BIDI_CONTROLS
        or char in sanitise.ZERO_WIDTH
        or char in sanitise.INVISIBLE
        or (char != "\n" and unicodedata.category(char) in _UNSAFE_CATEGORIES)
    )


def escape(text: str) -> str:
    """Markup characters as entities; bidi, invisible, control and separator
    characters as numeric references. The result cannot end or open an
    element and contains no hidden characters."""
    escaped = html.escape(text, quote=True)
    return "".join(f"&#x{ord(c):X};" if _unsafe(c) else c for c in escaped)


def _attrs(values: Mapping[str, str | None]) -> str:
    return "".join(
        f' {name}="{escape(value).replace(chr(10), "&#xA;")}"'
        for name, value in values.items()
        if value is not None and value != ""
    )


# --- Assembly --------------------------------------------------------------------


def _date(value: Any) -> date | None:
    if value is None or isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _truncate(text: str, limit: int) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0] or text[:limit]
    return cut.rstrip(" ,.;:") + "\u2026"


class _Cards:
    """Register sources, deduplicated and labelled in order of first use."""

    def __init__(self) -> None:
        self.by_id: dict[str, SourceCard] = {}

    def add(self, cards: Iterable[SourceCard]) -> tuple[str, ...]:
        labels = []
        for card in cards:
            known = self.by_id.get(card.source_id)
            if known is None:
                known = card.model_copy(update={"label": len(self.by_id) + 1})
                self.by_id[card.source_id] = known
            labels.append(f"C{known.label}")
        return tuple(dict.fromkeys(labels))


def _scope(doc: Mapping[str, Any]) -> str:
    consulates = list(doc.get("consulate_scope") or [])
    if consulates:
        return ",".join(f"consulate:{c}" for c in consulates)
    return ",".join(f"country:{c}" for c in doc.get("country_scope") or []) or "global"


def _rank(cards: Sequence[SourceCard]) -> str:
    badges = {c.badge for c in cards}
    return next((b for b in _BADGE_ORDER if b in badges), "secondary")


def assemble(
    hits: Sequence[ChunkHit],
    docs: Mapping[str, Mapping[str, Any]],
    facts: Sequence[FactOut | None] = (),
    *,
    lang: str,
    consulate: str | None,
    today: date,
    now: datetime | None = None,
    content_version: str | None = None,
) -> EvidencePack:
    """The evidence pack for ranked chunks (best first), the item documents
    they belong to (`fts.fetch_items`), and resolved facts."""
    registry = _Cards()
    sources: list[EvidenceSource] = []
    budget = MAX_EVIDENCE_CHARS
    for hit in hits:
        if len(sources) == MAX_SOURCES or budget < MIN_SOURCE_CHARS:
            break
        doc = docs.get(hit.item_id)
        if doc is None or doc.get("status") == "withdrawn":
            continue  # changed between the two reads
        titles = {str(t["lang"]): t for t in doc.get("texts", [])}
        text_doc = titles.get(hit.lang)
        if text_doc is None or not hit.body.strip():
            continue
        cards = catalogue.source_cards(doc.get("sources", []), today)
        text = _truncate(hit.body, budget)
        budget -= len(text)
        status = catalogue.item_status(hit.status, hit.review_due_at, today)
        sources.append(
            EvidenceSource(
                label=f"S{len(sources) + 1}",
                item_id=hit.item_id,
                lang=hit.lang,
                title=str(text_doc["title"]),
                heading=hit.heading,
                text=text,
                status="expired" if status == "expired" else "current",
                rank=_rank(cards),
                secondary_only=bool(cards) and all(c.badge == "secondary" for c in cards),
                verified_at=_date(text_doc.get("verified_at")),
                scope=_scope(doc),
                cards=registry.add(cards),
            )
        )
    evidence_facts: list[EvidenceFact] = []
    clarify: set[str] = set()
    for fact in facts:
        if fact is None:
            continue
        if fact.needs_consulate:
            clarify.update(fact.consulates)
        for value in fact.values:
            evidence_facts.append(
                EvidenceFact(
                    label=f"F{len(evidence_facts) + 1}",
                    fact_key=fact.fact_key,
                    scope=value.scope,
                    value=value.value,
                    unit=value.unit,
                    status=fact.status or value.status,
                    value_status=value.status,
                    verified_at=value.verified_at,
                    cards=registry.add(value.sources),
                )
            )
    return EvidencePack(
        generated_at=now or datetime.now(UTC),
        lang=lang,
        consulate=consulate,
        sources=tuple(sources),
        facts=tuple(evidence_facts),
        cards=tuple(registry.by_id.values()),
        clarify_consulate=tuple(sorted(clarify)),
        content_version=content_version,
    )


def build_evidence(
    query: str,
    *,
    lang: str,
    consulate: str | None = None,
    fact_keys: Sequence[str] = (),
    today: date | None = None,
    now: datetime | None = None,
    session_factory: Any = None,
) -> EvidencePack:
    """Search, fetch and assemble. Raises `fts.SearchTimeout`."""
    today = today or date.today()
    result = retrieval.search(
        query,
        ui_lang=lang,
        country=catalogue.DEFAULT_COUNTRY,
        consulate=consulate,
        today=today,
        session_factory=session_factory,
    )
    hits = [scored.hit for scored in result.hits]
    ids = list(dict.fromkeys(hit.item_id for hit in hits))
    docs: dict[str, Mapping[str, Any]] = {}
    if ids:
        with fts.search_session(session_factory=session_factory) as session:
            docs = {str(d["item_id"]): d for d in fts.fetch_items(session, ids)}
    facts = [
        catalogue.get_fact(key, consulate=consulate, today=today, session_factory=session_factory)
        for key in list(dict.fromkeys(fact_keys))[:MAX_FACT_KEYS]
    ]
    return assemble(hits, docs, facts, lang=lang, consulate=consulate, today=today, now=now)
