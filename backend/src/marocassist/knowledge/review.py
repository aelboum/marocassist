"""Daily editor review report (Phase 3 WP F).

Freshness itself needs no job: expiry is computed when content is read
(`knowledge.catalogue`), so it can never be skipped because a job failed.
This module only tells the editors what needs their attention, once per
UTC day, in the editorial tenant (decision P3-D10):

- items, sources, facts and consulate attributes whose review date has
  passed (`expired`) or falls within `HORIZON_DAYS` (`due_soon`);
- facts under review, and facts in conflict (two values in force for the
  same key and scope);
- user reports from the anonymous per-day counter: yesterday's, and the
  totals of the last `REPORT_WINDOW_DAYS` days per item and reason.

The report holds content ids, dates and counts only: no text, no tenant or
user data. It is stored once per day (`knowledge_review_reports`, unique
per tenant and date); the worker's minutely tick makes it after midnight
UTC and is a no-op for the rest of the day. Without a configured editorial
tenant the job does nothing.
"""

from __future__ import annotations

import json
import logging
import uuid
from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime, timedelta
from typing import Any

from saas_os.infra.db import IntegrityError, select, session_scope, tenant_session_scope

from marocassist.config import ConfigurationError, editorial_tenant_id
from marocassist.knowledge import fts
from marocassist.knowledge.models import KnowledgeReportCount, KnowledgeReviewReport

logger = logging.getLogger(__name__)

HORIZON_DAYS = 14
REPORT_WINDOW_DAYS = 7


def _date(value: Any) -> date | None:
    if value is None or isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _bucket(due: date | None, today: date, horizon: date) -> str | None:
    if due is None:
        return None
    if due < today:
        return "expired"
    if due <= horizon:
        return "due_soon"
    return None


def _split(
    rows: Sequence[Mapping[str, Any]],
    key: str,
    today: date,
    horizon: date,
    *,
    extra_date: str | None = None,
) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {"expired": [], "due_soon": []}
    for row in rows:
        dates = [_date(row.get("review_due_at"))]
        if extra_date:
            dates.append(_date(row.get(extra_date)))
        known = [d for d in dates if d is not None]
        due = min(known) if known else None
        bucket = "expired" if row.get("status") == "expired" else _bucket(due, today, horizon)
        if bucket:
            out[bucket].append({"id": row[key], "review_due_at": due.isoformat() if due else None})
    return out


def _in_force(fact: Mapping[str, Any], today: date) -> bool:
    start = _date(fact.get("valid_from"))
    end = _date(fact.get("valid_until"))
    return start is not None and start <= today and (end is None or end >= today)


def conflicts(facts: Sequence[Mapping[str, Any]], today: date) -> list[dict[str, Any]]:
    """Fact keys with more than one value in force in the same scope."""
    groups: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for fact in facts:
        if fact.get("status") != "withdrawn" and _in_force(fact, today):
            groups[(str(fact["fact_key"]), str(fact["scope"]))].append(fact)
    found = []
    for (key, scope), rows in sorted(groups.items()):
        values = {json.dumps([r.get("value"), r.get("unit")], sort_keys=True) for r in rows}
        if len(values) > 1:
            found.append(
                {
                    "fact_key": key,
                    "scope": scope,
                    "fact_ids": sorted(str(r["fact_id"]) for r in rows),
                }
            )
    return found


def build_summary(
    snapshot: Mapping[str, Any],
    counts: Sequence[tuple[str, str, date, int]],
    *,
    today: date,
) -> dict[str, Any]:
    horizon = today + timedelta(days=HORIZON_DAYS)
    facts = list(snapshot.get("facts", []))
    attributes = [
        {**a, "id": f"{a['code']}/{a['attribute']}/{a['lang']}"}
        for a in snapshot.get("attributes", [])
    ]
    yesterday = today - timedelta(days=1)
    totals: dict[tuple[str, str], int] = defaultdict(int)
    for item_id, reason, _day, count in counts:
        totals[(item_id, reason)] += count
    summary: dict[str, Any] = {
        "report_date": today.isoformat(),
        "horizon_days": HORIZON_DAYS,
        "items": _split(snapshot.get("items", []), "item_id", today, horizon),
        "sources": _split(
            snapshot.get("sources", []), "source_id", today, horizon, extra_date="valid_until"
        ),
        "facts": _split(facts, "fact_id", today, horizon),
        "consulate_attributes": _split(attributes, "id", today, horizon),
        "facts_under_review": sorted(
            str(f["fact_id"]) for f in facts if f.get("status") == "under_review"
        ),
        "fact_conflicts": conflicts(facts, today),
        "user_reports_yesterday": [
            {"item_id": item_id, "reason_code": reason, "count": count}
            for item_id, reason, day, count in sorted(counts)
            if day == yesterday
        ],
        "user_reports_last_days": [
            {"item_id": item_id, "reason_code": reason, "count": total}
            for (item_id, reason), total in sorted(totals.items())
        ],
        "user_reports_window_days": REPORT_WINDOW_DAYS,
    }
    summary["needs_attention"] = (
        sum(
            len(summary[group]["expired"])
            for group in ("items", "sources", "facts", "consulate_attributes")
        )
        + len(summary["fact_conflicts"])
        + len(summary["user_reports_yesterday"])
    )
    return summary


def _read_counts(since: date, session_factory: Any) -> list[tuple[str, str, date, int]]:
    with session_scope(session_factory=session_factory) as session:
        rows = session.execute(
            select(KnowledgeReportCount).where(KnowledgeReportCount.day >= since)
        ).scalars()
        return [(r.item_id, r.reason_code, r.day, r.count) for r in rows.all()]


def _existing(tenant_id: uuid.UUID, today: date) -> uuid.UUID | None:
    with tenant_session_scope(tenant_id) as session:
        row = session.execute(
            select(KnowledgeReviewReport).where(
                KnowledgeReviewReport.tenant_id == tenant_id,
                KnowledgeReviewReport.report_date == today,
            )
        ).scalar_one_or_none()
        return row.report_id if row else None


def run_daily_review(
    *,
    today: date | None = None,
    tenant_id: uuid.UUID | None = None,
    session_factory: Any = None,
) -> uuid.UUID | None:
    """Write today's report if it does not exist yet. Returns its id, or
    None when no editorial tenant is configured."""
    if tenant_id is None:
        try:
            tenant_id = editorial_tenant_id()
        except ConfigurationError:
            return None
    today = today or datetime.now(UTC).date()
    existing = _existing(tenant_id, today)
    if existing is not None:
        return existing
    with fts.search_session(session_factory=session_factory) as session:
        snapshot = fts.fetch_review_snapshot(session, today + timedelta(days=HORIZON_DAYS))
    counts = _read_counts(today - timedelta(days=REPORT_WINDOW_DAYS), session_factory)
    summary = build_summary(snapshot, counts, today=today)
    report_id = uuid.uuid4()
    try:
        with tenant_session_scope(tenant_id) as session:
            session.add(
                KnowledgeReviewReport(
                    report_id=report_id,
                    tenant_id=tenant_id,
                    report_date=today,
                    created_at=datetime.now(UTC),
                    summary=summary,
                )
            )
    except IntegrityError:
        # Another worker wrote today's report first.
        return _existing(tenant_id, today)
    logger.info(
        "knowledge_review_report_written",
        extra={"report_date": today.isoformat(), "needs_attention": summary["needs_attention"]},
    )
    return report_id


def delete_for_tenant(tenant_id: uuid.UUID) -> None:
    """Purge participant step: the review reports of a purged (editorial)
    tenant. Idempotent."""
    with tenant_session_scope(tenant_id) as session:
        rows = session.execute(
            select(KnowledgeReviewReport).where(KnowledgeReviewReport.tenant_id == tenant_id)
        ).scalars()
        for row in rows.all():
            session.delete(row)
