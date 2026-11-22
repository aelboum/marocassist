"""Tenant-side "report outdated" rows. Every access runs in
`tenant_session_scope(tenant_id)`, so Row-Level Security applies.

A report stores the item id and a reason code only: no free text, no
user id (the tenant is the user's personal workspace). The same report
for the same item and reason within `DEDUPE_HOURS` is returned instead of
stored again, so repeated clicks do not inflate the editor's queue.

Each new report also adds one to the anonymous counter
`knowledge_report_counts` (item, reason, UTC day), in the same
transaction. The daily editor review report reads only that counter, so it
never needs to read across tenants.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Literal

from saas_os.infra.db import (
    IntegrityError,
    Session,
    acquire_tenant_advisory_lock,
    select,
    tenant_session_scope,
    update,
)

from marocassist.knowledge.models import KnowledgeReport, KnowledgeReportCount

ReasonCode = Literal["outdated", "incorrect", "broken_link", "other"]
DEDUPE_HOURS = 24
# Serialises the check-then-insert below per tenant, so two identical
# concurrent reports cannot both be counted (security review P3-R6).
_REPORT_LOCK = "marocassist.knowledge.report"


@dataclass(frozen=True)
class ReportResult:
    report_id: uuid.UUID
    created_at: datetime
    created: bool


def create_report(tenant_id: uuid.UUID, item_id: str, reason_code: ReasonCode) -> ReportResult:
    since = datetime.now(UTC) - timedelta(hours=DEDUPE_HOURS)
    with tenant_session_scope(tenant_id) as session:
        acquire_tenant_advisory_lock(session, tenant_id, _REPORT_LOCK)
        existing = session.execute(
            select(KnowledgeReport)
            .where(
                KnowledgeReport.tenant_id == tenant_id,
                KnowledgeReport.item_id == item_id,
                KnowledgeReport.reason_code == reason_code,
                KnowledgeReport.created_at >= since,
            )
            .order_by(KnowledgeReport.created_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        if existing is not None:
            return ReportResult(existing.report_id, existing.created_at, created=False)
        row = KnowledgeReport(
            report_id=uuid.uuid4(),
            tenant_id=tenant_id,
            item_id=item_id,
            reason_code=reason_code,
            created_at=datetime.now(UTC),
        )
        session.add(row)
        _count(session, item_id, reason_code, row.created_at.date())
        session.flush()
        return ReportResult(row.report_id, row.created_at, created=True)


def _bump(session: Session, item_id: str, reason_code: str, day: date) -> bool:
    result = session.execute(
        update(KnowledgeReportCount)
        .where(
            KnowledgeReportCount.item_id == item_id,
            KnowledgeReportCount.reason_code == reason_code,
            KnowledgeReportCount.day == day,
        )
        .values(count=KnowledgeReportCount.count + 1)
    )
    return bool(getattr(result, "rowcount", 0))


def _count(session: Session, item_id: str, reason_code: str, day: date) -> None:
    """Add one to the counter, creating it on first use. The UPDATE's row
    lock serialises concurrent reports; when two transactions create the
    same counter at once, the loser's insert fails in its savepoint and it
    updates the winner's row instead."""
    if _bump(session, item_id, reason_code, day):
        return
    try:
        with session.begin_nested():
            session.add(
                KnowledgeReportCount(item_id=item_id, reason_code=reason_code, day=day, count=1)
            )
    except IntegrityError:
        _bump(session, item_id, reason_code, day)


def delete_for_tenant(tenant_id: uuid.UUID) -> None:
    """Purge participant step. Idempotent. No FOR UPDATE: the table has no
    UPDATE grant, and the purge runs once per tenant under SaaS-OS's lock."""
    with tenant_session_scope(tenant_id) as session:
        rows = session.execute(
            select(KnowledgeReport).where(KnowledgeReport.tenant_id == tenant_id)
        ).scalars()
        for row in rows.all():
            session.delete(row)
