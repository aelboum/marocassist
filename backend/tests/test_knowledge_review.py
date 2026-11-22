"""Unit tests for the daily editor review report (Phase 3 WP F) with a fixed
date. No database; the job and storage are in
test_knowledge_review_integration.py."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from marocassist.knowledge import review

TODAY = date(2026, 11, 21)


def _day(offset: int) -> str:
    return (TODAY + timedelta(days=offset)).isoformat()


def _fact(fact_id: str, key: str, scope: str, value: Any, **overrides: Any) -> dict[str, Any]:
    doc: dict[str, Any] = {
        "fact_id": fact_id,
        "fact_key": key,
        "scope": scope,
        "value": value,
        "unit": "MAD",
        "valid_from": "2026-01-01",
        "valid_until": None,
        "status": "published",
        "review_due_at": _day(60),
    }
    doc.update(overrides)
    return doc


def test_review_dates_split_into_expired_and_due_soon() -> None:
    snapshot = {
        "items": [
            {"item_id": "a.late", "status": "published", "review_due_at": _day(-1)},
            {"item_id": "a.today", "status": "published", "review_due_at": _day(0)},
            {
                "item_id": "a.soon",
                "status": "published",
                "review_due_at": _day(review.HORIZON_DAYS),
            },
            {"item_id": "a.marked", "status": "expired", "review_due_at": _day(30)},
        ],
        "sources": [
            {
                "source_id": "src-x",
                "status": "verified",
                "review_due_at": _day(90),
                "valid_until": _day(-2),
            }
        ],
        "attributes": [
            {
                "code": "nl-rotterdam",
                "attribute": "address",
                "lang": "und",
                "status": "pending_review",
                "review_due_at": _day(3),
            }
        ],
        "facts": [_fact("f.late", "fee.x.y", "global", 1, review_due_at=_day(-5))],
    }
    summary = review.build_summary(snapshot, [], today=TODAY)
    assert [i["id"] for i in summary["items"]["expired"]] == ["a.late", "a.marked"]
    assert [i["id"] for i in summary["items"]["due_soon"]] == ["a.today", "a.soon"]
    assert summary["sources"]["expired"] == [{"id": "src-x", "review_due_at": _day(-2)}]
    assert summary["consulate_attributes"]["due_soon"][0]["id"] == "nl-rotterdam/address/und"
    assert [f["id"] for f in summary["facts"]["expired"]] == ["f.late"]
    assert summary["needs_attention"] == 4


def test_conflicts_are_two_values_in_force_for_the_same_key_and_scope() -> None:
    facts = [
        _fact("f.a", "fee.passport.adult", "consulate:nl-rotterdam", 300),
        _fact("f.b", "fee.passport.adult", "consulate:nl-rotterdam", 350),
        _fact("f.c", "fee.passport.adult", "global", 300),
        _fact("f.d", "fee.passport.adult", "global", 300),  # same value: no conflict
        _fact("f.old", "fee.card", "global", 100, valid_until=_day(-1)),
        _fact("f.new", "fee.card", "global", 120),
        _fact("f.gone", "fee.card", "global", 90, status="withdrawn"),
    ]
    assert review.conflicts(facts, TODAY) == [
        {
            "fact_key": "fee.passport.adult",
            "scope": "consulate:nl-rotterdam",
            "fact_ids": ["f.a", "f.b"],
        }
    ]


def test_user_reports_come_from_the_anonymous_counter() -> None:
    yesterday = TODAY - timedelta(days=1)
    counts = [
        ("x.item", "outdated", yesterday, 3),
        ("x.item", "outdated", TODAY - timedelta(days=4), 2),
        ("y.item", "broken_link", TODAY - timedelta(days=2), 1),
    ]
    summary = review.build_summary({}, counts, today=TODAY)
    assert summary["user_reports_yesterday"] == [
        {"item_id": "x.item", "reason_code": "outdated", "count": 3}
    ]
    assert summary["user_reports_last_days"] == [
        {"item_id": "x.item", "reason_code": "outdated", "count": 5},
        {"item_id": "y.item", "reason_code": "broken_link", "count": 1},
    ]
    assert summary["needs_attention"] == 1


def test_the_summary_holds_ids_dates_and_counts_only() -> None:
    summary = review.build_summary(
        {"facts": [_fact("f.a", "fee.x.y", "global", {"amount": 300})]}, [], today=TODAY
    )
    text = repr(summary)
    assert "300" not in text  # fact values are not copied into the report
    assert "tenant" not in text and "user_id" not in text
