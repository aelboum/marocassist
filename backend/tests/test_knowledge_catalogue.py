"""Unit tests for the knowledge catalogue (Phase 3 WP D): read-time status,
fact scope and conflict, consulate attributes and source cards, with a
fixed date. No database; the routes are in
test_knowledge_api_integration.py."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import pytest

from marocassist.knowledge import catalogue

TODAY = date(2026, 11, 21)
SOON = (TODAY + timedelta(days=30)).isoformat()
PAST = (TODAY - timedelta(days=1)).isoformat()


def _source(**overrides: Any) -> dict[str, Any]:
    doc: dict[str, Any] = {
        "source_id": "src-a",
        "title": "A",
        "publisher": "P",
        "source_type": "official",
        "official_url": "https://example.test/a",
        "geo_scope": "global",
        "language": "fr",
        "verified_at": "2026-11-01",
        "review_due_at": SOON,
        "valid_until": None,
        "status": "verified",
        "allowed_use": ["link"],
        "locator": "Tarifs",
    }
    doc.update(overrides)
    return doc


def _fact(fact_id: str, scope: str, value: Any, **overrides: Any) -> dict[str, Any]:
    doc: dict[str, Any] = {
        "fact_id": fact_id,
        "fact_key": "fee.passport.adult",
        "scope": scope,
        "value": value,
        "unit": "MAD",
        "valid_from": "2026-01-01",
        "valid_until": None,
        "status": "published",
        "verified_at": "2026-11-01",
        "review_due_at": SOON,
        "sources": [_source()],
    }
    doc.update(overrides)
    return doc


def _resolve(docs: list[dict[str, Any]], consulate: str | None) -> catalogue.FactOut:
    fact = catalogue.resolve_fact("fee.passport.adult", docs, consulate=consulate, today=TODAY)
    assert fact is not None
    return fact


# --- Status and source cards -------------------------------------------------------


def test_item_status_is_computed_at_read_time() -> None:
    assert catalogue.item_status("published", TODAY, TODAY) == "current"
    assert catalogue.item_status("published", TODAY - timedelta(days=1), TODAY) == "expired"
    assert catalogue.item_status("expired", TODAY + timedelta(days=9), TODAY) == "expired"
    assert catalogue.item_status("withdrawn", TODAY + timedelta(days=9), TODAY) == "withdrawn"


@pytest.mark.parametrize(
    ("overrides", "status"),
    [
        ({}, "current"),
        ({"review_due_at": PAST}, "expired"),
        ({"valid_until": PAST}, "expired"),
        ({"status": "expired"}, "expired"),
        ({"status": "withdrawn"}, "withdrawn"),
        ({"status": "pending_review"}, "unverified"),
    ],
)
def test_source_status(overrides: dict[str, Any], status: str) -> None:
    assert catalogue.source_status(_source(**overrides), TODAY) == status


def test_source_cards_are_labelled_in_order_with_a_badge_per_type() -> None:
    cards = catalogue.source_cards(
        [
            _source(),
            _source(source_id="src-b", source_type="government"),
            _source(source_id="src-c", source_type="secondary"),
            _source(source_id="src-d", source_type="internal"),
        ],
        TODAY,
    )
    assert [c.label for c in cards] == [1, 2, 3, 4]
    assert [c.badge for c in cards] == ["official", "official", "secondary", "explanation"]
    assert cards[0].url == "https://example.test/a"
    assert cards[0].locator == "Tarifs"


def test_snippet_is_plain_text_cut_at_a_word() -> None:
    assert catalogue.snippet("  a  b\n c ") == "a b c"
    cut = catalogue.snippet("woord " * 100, limit=20)
    assert cut == "woord woord woord\u2026"


def test_choose_lang_falls_back_to_dutch_then_the_first_language() -> None:
    assert catalogue.choose_lang(["fr", "nl"], "fr") == "fr"
    assert catalogue.choose_lang(["fr", "nl"], "en") == "nl"
    assert catalogue.choose_lang(["ar", "fr"], "en") == "ar"
    assert catalogue.choose_lang([], "nl") is None


# --- Items -------------------------------------------------------------------------


def _item(**overrides: Any) -> dict[str, Any]:
    doc: dict[str, Any] = {
        "item_id": "x.item",
        "kind": "procedure",
        "status": "published",
        "version": 1,
        "review_due_at": SOON,
        "superseded_by": None,
        "country_scope": ["NL"],
        "consulate_scope": [],
        "texts": [
            {"lang": "fr", "title": "Titre", "body": "Corps", "verified_at": "2026-11-01"},
            {"lang": "nl", "title": "Titel", "body": "Tekst", "verified_at": "2026-11-01"},
        ],
        "sources": [_source()],
    }
    doc.update(overrides)
    return doc


def test_item_view_picks_the_language_and_flags_expiry() -> None:
    view = catalogue.item_view(_item(), "en", TODAY)
    assert (view.lang, view.title, view.status) == ("nl", "Titel", "current")
    assert view.available_langs == ["fr", "nl"]
    expired = catalogue.item_view(_item(review_due_at=PAST), "fr", TODAY)
    assert (expired.lang, expired.status) == ("fr", "expired")


def test_a_withdrawn_item_is_a_stub_with_its_successor() -> None:
    view = catalogue.item_view(
        _item(status="withdrawn", superseded_by="x.new", texts=[]), "nl", TODAY
    )
    assert view.status == "withdrawn"
    assert view.superseded_by == "x.new"
    assert view.title is None and view.body is None


# --- Facts -------------------------------------------------------------------------


def test_the_most_specific_scope_wins() -> None:
    docs = [
        _fact("f-global", "global", 300),
        _fact("f-nl", "country:NL", 310),
        _fact("f-rdam", "consulate:nl-rotterdam", 320),
    ]
    assert _resolve(docs, "nl-rotterdam").values[0].value == 320
    assert _resolve(docs, "nl-utrecht").values[0].value == 310
    assert _resolve(docs, None).values[0].value == 310
    only_global = _resolve(docs[:1], "nl-rotterdam")
    assert (only_global.scope, only_global.status) == ("global", "current")


def test_two_values_in_the_same_scope_are_a_conflict_and_both_are_returned() -> None:
    fact = _resolve(
        [
            _fact("f-1", "consulate:nl-rotterdam", 300),
            _fact("f-2", "consulate:nl-rotterdam", 350, sources=[_source(source_id="src-b")]),
            _fact("f-global", "global", 300),
        ],
        "nl-rotterdam",
    )
    assert fact.status == "conflict"
    assert [v.value for v in fact.values] == [300, 350]
    assert [v.sources[0].source_id for v in fact.values] == ["src-a", "src-b"]


def test_the_same_value_from_two_rows_is_not_a_conflict() -> None:
    fact = _resolve([_fact("f-1", "global", 300), _fact("f-2", "global", 300)], None)
    assert fact.status == "current"
    other_unit = [_fact("f-1", "global", 300), _fact("f-2", "global", 300, unit="EUR")]
    assert _resolve(other_unit, None).status == "conflict"


def test_expired_and_under_review_values_are_never_current() -> None:
    expired = _resolve([_fact("f-1", "global", 300, review_due_at=PAST)], None)
    assert (expired.status, expired.values[0].status) == ("expired", "expired")
    review = _resolve([_fact("f-1", "global", 300, status="under_review")], None)
    assert (review.status, review.values[0].status) == ("under_review", "under_review")


def test_history_and_future_values_are_ignored() -> None:
    docs = [
        _fact("f-old", "consulate:nl-rotterdam", 250, valid_until=PAST),
        _fact("f-next", "consulate:nl-rotterdam", 400, valid_from=SOON),
        _fact("f-global", "global", 300),
    ]
    fact = _resolve(docs, "nl-rotterdam")
    assert (fact.scope, [v.value for v in fact.values]) == ("global", [300])
    assert catalogue.resolve_fact("k.x", docs[:2], consulate=None, today=TODAY) is None
    withdrawn = [_fact("f-1", "global", 300, status="withdrawn")]
    assert catalogue.resolve_fact("k.x", withdrawn, consulate=None, today=TODAY) is None


def test_a_consulate_only_fact_without_a_consulate_asks_instead_of_guessing() -> None:
    docs = [
        _fact("f-r", "consulate:nl-rotterdam", 320),
        _fact("f-u", "consulate:nl-utrecht", 330),
    ]
    fact = _resolve(docs, None)
    assert fact.needs_consulate
    assert fact.values == [] and fact.status is None
    assert fact.consulates == ["nl-rotterdam", "nl-utrecht"]
    other = _resolve(docs, "nl-amsterdam")
    assert not other.needs_consulate and other.values == []


def test_region_scopes_are_not_matched() -> None:
    fact = _resolve([_fact("f-r", "region:randstad", 300)], "nl-rotterdam")
    assert fact.values == []


# --- Consulates --------------------------------------------------------------------


def _attribute(attribute: str, value: Any, lang: str = "und", **overrides: Any) -> dict[str, Any]:
    doc: dict[str, Any] = {
        "attribute": attribute,
        "lang": lang,
        "value": value,
        "verified_at": "2026-11-01",
        "review_due_at": SOON,
        "status": "pending_review",
        "source": _source(source_type="government"),
    }
    doc.update(overrides)
    return doc


def _consulate(*attributes: dict[str, Any]) -> dict[str, Any]:
    return {
        "code": "nl-rotterdam",
        "country": "NL",
        "kind": "consulate_general",
        "active": True,
        "attributes": list(attributes),
    }


def test_rotterdam_shows_schiedam_as_pending_review_and_lists_missing_data() -> None:
    view = catalogue.consulate_view(
        _consulate(
            _attribute("display_name", "Consulaat-generaal Rotterdam", "nl"),
            _attribute("display_name", "Consulat g\u00e9n\u00e9ral de Rotterdam", "fr"),
            _attribute("physical_city", "Schiedam"),
        ),
        "en",
        TODAY,
    )
    assert view.display_name == "Consulaat-generaal Rotterdam"
    city = next(a for a in view.attributes if a.attribute == "physical_city")
    assert (city.value, city.status, city.independently_confirmed) == (
        "Schiedam",
        "pending_review",
        False,
    )
    assert city.lang is None
    assert [a.attribute for a in view.attributes].count("display_name") == 1
    assert view.missing == ["address", "contact", "opening_hours"]


def test_a_verified_attribute_expires_after_its_review_date() -> None:
    view = catalogue.consulate_view(
        _consulate(
            _attribute("address", {"city": "Schiedam"}, status="verified"),
            _attribute("contact", {"phone": "x"}, status="verified", review_due_at=PAST),
        ),
        "nl",
        TODAY,
    )
    statuses = {a.attribute: (a.status, a.independently_confirmed) for a in view.attributes}
    assert statuses == {"address": ("verified", True), "contact": ("expired", False)}
    assert view.display_name is None
