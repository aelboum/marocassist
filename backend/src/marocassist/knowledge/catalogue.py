"""Knowledge catalogue (Phase 3 WP D): items, facts and consulates as the
API shows them, with every status computed at read time.

The database returns raw rows as JSON documents (`knowledge.fts`); this
module decides what they mean on a given day, so the rules are unit-tested
with a fixed date:

- **Items:** a published item whose `review_due_at` has passed is `expired`:
  still shown, never as current information. A withdrawn item is a stub
  with its successor and without its body; see content rights section 5.4.
- **Facts:** the most specific scope wins (consulate, then country, then
  global). Rows outside their validity window are history and are ignored.
  Two different values in the winning scope are a `conflict`: every value
  is returned with its sources and none is presented as true (rights 5.3).
  A fact that exists only per consulate, asked without a consulate, returns
  no value and `needs_consulate` (search architecture 4.3: ask, never guess).
- **Consulates:** each attribute has its own status. An attribute not yet
  independently confirmed stays `pending_review` (owner decision P3-D5);
  a verified attribute past its review date is `expired`. Attributes
  without data (opening hours, jurisdiction) are listed as missing and are
  never filled in.
- **Source cards** (rights section 7) are built here from the source
  register, never from model output.

Region scopes (`region:*`) are not matched yet: no consulate-to-region
mapping exists, so a region-scoped fact is never chosen by guesswork.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import date
from typing import Any, Literal

from pydantic import BaseModel

from marocassist.knowledge import fts, normalise, retrieval

ItemStatus = Literal["current", "expired", "withdrawn"]
FactStatus = Literal["current", "expired", "under_review", "conflict"]
ValueStatus = Literal["current", "expired", "under_review"]
SourceStatus = Literal["current", "expired", "withdrawn", "unverified"]
AttributeStatus = Literal["verified", "pending_review", "expired"]
Badge = Literal["official", "secondary", "explanation"]

LANGS = normalise.LANGS
DEFAULT_LANG = normalise.DEFAULT_LANG
DEFAULT_COUNTRY = "NL"
SNIPPET_CHARS = 240
CONSULATE_ATTRIBUTES: tuple[str, ...] = (
    "display_name",
    "physical_city",
    "address",
    "contact",
    "opening_hours",
)
_OFFICIAL_TYPES = frozenset({"official", "consulate", "government"})


class SourceCard(BaseModel):
    label: int
    source_id: str
    title: str
    publisher: str
    badge: Badge
    scope: str
    verified_at: date | None
    status: SourceStatus
    url: str
    locator: str | None = None


class ItemOut(BaseModel):
    item_id: str
    kind: str
    status: ItemStatus
    version: int
    review_due_at: date
    superseded_by: str | None
    country_scope: list[str]
    consulate_scope: list[str]
    lang: str | None
    available_langs: list[str]
    title: str | None
    body: str | None
    verified_at: date | None
    sources: list[SourceCard]


class FactValue(BaseModel):
    fact_id: str
    scope: str
    value: Any
    unit: str | None
    status: ValueStatus
    valid_from: date
    valid_until: date | None
    verified_at: date
    sources: list[SourceCard]


class FactOut(BaseModel):
    fact_key: str
    consulate: str | None
    scope: str | None
    status: FactStatus | None
    needs_consulate: bool
    consulates: list[str]
    values: list[FactValue]


class AttributeOut(BaseModel):
    attribute: str
    lang: str | None
    value: Any
    status: AttributeStatus
    independently_confirmed: bool
    verified_at: date
    source: SourceCard


class ConsulateOut(BaseModel):
    code: str
    country: str
    kind: str
    active: bool
    display_name: str | None
    attributes: list[AttributeOut]
    missing: list[str]


class SearchResultOut(BaseModel):
    item_id: str
    lang: str
    ordinal: int
    kind: str
    status: ItemStatus
    partial: bool
    title: str
    heading: str | None
    snippet: str
    sources: list[SourceCard]


class SearchOut(BaseModel):
    langs: list[str]
    detected_lang: str | None
    results: list[SearchResultOut]


class ItemNotFoundError(LookupError):
    pass


# --- Helpers -----------------------------------------------------------------------


def _date(value: Any) -> date | None:
    if value is None or isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _required_date(value: Any) -> date:
    parsed = _date(value)
    if parsed is None:
        raise ValueError("date missing")
    return parsed


def _past(review_due_at: date | None, today: date) -> bool:
    return review_due_at is not None and review_due_at < today


def item_status(status: str, review_due_at: date, today: date) -> ItemStatus:
    if status == "withdrawn":
        return "withdrawn"
    if status == "expired" or _past(review_due_at, today):
        return "expired"
    return "current"


def source_status(doc: Mapping[str, Any], today: date) -> SourceStatus:
    status = doc.get("status")
    if status == "withdrawn":
        return "withdrawn"
    if status == "expired":
        return "expired"
    if status != "verified":
        return "unverified"
    if _past(_date(doc.get("review_due_at")), today) or _past(_date(doc.get("valid_until")), today):
        return "expired"
    return "current"


def badge(source_type: str) -> Badge:
    if source_type in _OFFICIAL_TYPES:
        return "official"
    if source_type == "internal":
        return "explanation"
    return "secondary"


def source_cards(docs: Sequence[Mapping[str, Any]], today: date) -> list[SourceCard]:
    return [
        SourceCard(
            label=label,
            source_id=str(doc["source_id"]),
            title=str(doc["title"]),
            publisher=str(doc["publisher"]),
            badge=badge(str(doc["source_type"])),
            scope=str(doc["geo_scope"]),
            verified_at=_date(doc.get("verified_at")),
            status=source_status(doc, today),
            url=str(doc["official_url"]),
            locator=doc.get("locator"),
        )
        for label, doc in enumerate(docs, start=1)
    ]


def choose_lang(available: Sequence[str], wanted: str | None) -> str | None:
    """The requested language, else Dutch, else the first available."""
    for lang in (wanted, DEFAULT_LANG):
        if lang in available:
            return lang
    return available[0] if available else None


def snippet(body: str, limit: int = SNIPPET_CHARS) -> str:
    """Plain text: whitespace collapsed, cut at a word boundary. No markup,
    so the client escapes it like any other text."""
    text = " ".join(body.split())
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0] or text[:limit]
    return cut.rstrip(" ,.;:") + "\u2026"


# --- Items -------------------------------------------------------------------------


def item_view(doc: Mapping[str, Any], lang: str | None, today: date) -> ItemOut:
    texts = {str(t["lang"]): t for t in doc.get("texts", [])}
    chosen = choose_lang(sorted(texts), lang)
    text = texts.get(chosen) if chosen else None
    due = _required_date(doc["review_due_at"])
    return ItemOut(
        item_id=str(doc["item_id"]),
        kind=str(doc["kind"]),
        status=item_status(str(doc["status"]), due, today),
        version=int(doc["version"]),
        review_due_at=due,
        superseded_by=doc.get("superseded_by"),
        country_scope=list(doc.get("country_scope") or []),
        consulate_scope=list(doc.get("consulate_scope") or []),
        lang=chosen,
        available_langs=sorted(texts),
        title=text["title"] if text else None,
        body=text["body"] if text else None,
        verified_at=_date(text["verified_at"]) if text else None,
        sources=source_cards(doc.get("sources", []), today),
    )


def get_item(
    item_id: str, *, lang: str | None, today: date | None = None, session_factory: Any = None
) -> ItemOut:
    """One item. Raises `ItemNotFoundError` when it does not exist, or when
    it is not withdrawn but has no published text."""
    today = today or date.today()
    with fts.search_session(session_factory=session_factory) as session:
        docs = fts.fetch_items(session, [item_id])
    if not docs:
        raise ItemNotFoundError(item_id)
    view = item_view(docs[0], lang, today)
    if view.status != "withdrawn" and view.title is None:
        raise ItemNotFoundError(item_id)
    return view


def item_is_reportable(item_id: str, *, session_factory: Any = None) -> bool:
    """True when the item exists and is not withdrawn."""
    with fts.search_session(session_factory=session_factory) as session:
        docs = fts.fetch_items(session, [item_id])
    return bool(docs) and docs[0].get("status") != "withdrawn"


# --- Search ------------------------------------------------------------------------


def search(
    query: str,
    *,
    lang: str,
    consulate: str | None = None,
    kinds: Sequence[str] | None = None,
    today: date | None = None,
    session_factory: Any = None,
) -> SearchOut:
    """Search results with titles, snippets and source cards. Raises
    `fts.SearchTimeout`."""
    today = today or date.today()
    result = retrieval.search(
        query,
        ui_lang=lang,
        country=DEFAULT_COUNTRY,
        consulate=consulate,
        kinds=kinds,
        today=today,
        session_factory=session_factory,
    )
    ids = list(dict.fromkeys(scored.hit.item_id for scored in result.hits))
    docs: dict[str, Mapping[str, Any]] = {}
    if ids:
        with fts.search_session(session_factory=session_factory) as session:
            docs = {str(d["item_id"]): d for d in fts.fetch_items(session, ids)}
    results: list[SearchResultOut] = []
    for scored in result.hits:
        hit = scored.hit
        doc = docs.get(hit.item_id)
        if doc is None or doc.get("status") == "withdrawn":
            continue  # changed between the two reads
        titles = {str(t["lang"]): str(t["title"]) for t in doc.get("texts", [])}
        if hit.lang not in titles:
            continue
        results.append(
            SearchResultOut(
                item_id=hit.item_id,
                lang=hit.lang,
                ordinal=hit.ordinal,
                kind=hit.kind,
                status=item_status(hit.status, hit.review_due_at, today),
                partial=scored.partial,
                title=titles[hit.lang],
                heading=hit.heading,
                snippet=snippet(hit.body),
                sources=source_cards(doc.get("sources", []), today),
            )
        )
    return SearchOut(
        langs=list(result.query.langs),
        detected_lang=result.query.detected,
        results=results,
    )


# --- Facts -------------------------------------------------------------------------


def _in_force(doc: Mapping[str, Any], today: date) -> bool:
    valid_from = _required_date(doc["valid_from"])
    valid_until = _date(doc.get("valid_until"))
    return valid_from <= today and (valid_until is None or valid_until >= today)


def _value_status(doc: Mapping[str, Any], today: date) -> ValueStatus:
    if doc.get("status") == "under_review":
        return "under_review"
    if _past(_date(doc.get("review_due_at")), today):
        return "expired"
    return "current"


def _scope_order(consulate: str | None, country: str) -> list[str]:
    order = [f"consulate:{consulate}"] if consulate else []
    return [*order, f"country:{country}", "global"]


def _value_key(doc: Mapping[str, Any]) -> str:
    return json.dumps([doc.get("value"), doc.get("unit")], sort_keys=True)


def resolve_fact(
    fact_key: str,
    docs: Sequence[Mapping[str, Any]],
    *,
    consulate: str | None,
    today: date,
    country: str = DEFAULT_COUNTRY,
) -> FactOut | None:
    """The fact as it applies to `consulate` (or the country) on `today`.
    None when the key has no row in force in any scope."""
    in_force = [d for d in docs if d.get("status") != "withdrawn" and _in_force(d, today)]
    if not in_force:
        return None
    per_consulate = sorted(
        {
            str(d["scope"]).removeprefix("consulate:")
            for d in in_force
            if str(d["scope"]).startswith("consulate:")
        }
    )
    chosen_scope: str | None = None
    rows: list[Mapping[str, Any]] = []
    for scope in _scope_order(consulate, country):
        rows = [d for d in in_force if d["scope"] == scope]
        if rows:
            chosen_scope = scope
            break
    if not rows:
        return FactOut(
            fact_key=fact_key,
            consulate=consulate,
            scope=None,
            status=None,
            needs_consulate=consulate is None and bool(per_consulate),
            consulates=per_consulate,
            values=[],
        )
    values = [
        FactValue(
            fact_id=str(d["fact_id"]),
            scope=str(d["scope"]),
            value=d.get("value"),
            unit=d.get("unit"),
            status=_value_status(d, today),
            valid_from=_required_date(d["valid_from"]),
            valid_until=_date(d.get("valid_until")),
            verified_at=_required_date(d["verified_at"]),
            sources=source_cards(d.get("sources", []), today),
        )
        for d in rows
    ]
    status: FactStatus
    if len({_value_key(d) for d in rows}) > 1:
        status = "conflict"
    elif any(v.status == "under_review" for v in values):
        status = "under_review"
    elif any(v.status == "expired" for v in values):
        status = "expired"
    else:
        status = "current"
    return FactOut(
        fact_key=fact_key,
        consulate=consulate,
        scope=chosen_scope,
        status=status,
        needs_consulate=False,
        consulates=per_consulate,
        values=values,
    )


def get_fact(
    fact_key: str,
    *,
    consulate: str | None,
    today: date | None = None,
    session_factory: Any = None,
) -> FactOut | None:
    today = today or date.today()
    with fts.search_session(session_factory=session_factory) as session:
        docs = fts.fetch_facts(session, fact_key)
    return resolve_fact(fact_key, docs, consulate=consulate, today=today)


# --- Consulates --------------------------------------------------------------------


def _attribute_status(doc: Mapping[str, Any], today: date) -> AttributeStatus:
    if doc.get("status") == "verified":
        return "expired" if _past(_date(doc.get("review_due_at")), today) else "verified"
    return "pending_review"


def consulate_view(doc: Mapping[str, Any], lang: str | None, today: date) -> ConsulateOut:
    attributes_in = list(doc.get("attributes", []))
    names = {str(a["lang"]): a for a in attributes_in if a["attribute"] == "display_name"}
    name_lang = choose_lang(sorted(names), lang)
    attributes: list[AttributeOut] = []
    for a in attributes_in:
        if a["attribute"] == "display_name" and a["lang"] != name_lang:
            continue
        status = _attribute_status(a, today)
        attributes.append(
            AttributeOut(
                attribute=str(a["attribute"]),
                lang=None if a["lang"] == "und" else str(a["lang"]),
                value=a.get("value"),
                status=status,
                independently_confirmed=status == "verified",
                verified_at=_required_date(a["verified_at"]),
                source=source_cards([a["source"]], today)[0],
            )
        )
    present = {a.attribute for a in attributes}
    return ConsulateOut(
        code=str(doc["code"]),
        country=str(doc["country"]),
        kind=str(doc["kind"]),
        active=bool(doc["active"]),
        display_name=str(names[name_lang]["value"]) if name_lang else None,
        attributes=attributes,
        missing=[name for name in CONSULATE_ATTRIBUTES if name not in present],
    )


def list_consulates(
    *, lang: str | None, today: date | None = None, session_factory: Any = None
) -> list[ConsulateOut]:
    today = today or date.today()
    with fts.search_session(session_factory=session_factory) as session:
        docs = fts.fetch_consulates(session)
    return [consulate_view(d, lang, today) for d in docs]


def get_consulate(
    code: str, *, lang: str | None, today: date | None = None, session_factory: Any = None
) -> ConsulateOut | None:
    today = today or date.today()
    with fts.search_session(session_factory=session_factory) as session:
        docs = fts.fetch_consulates(session, code)
    return consulate_view(docs[0], lang, today) if docs else None
