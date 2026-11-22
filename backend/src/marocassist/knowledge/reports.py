"""Tenant-side "report outdated" rows. Every access runs in
`tenant_session_scope(tenant_id)`, so Row-Level Security applies.

A report stores the item id and a reason code only: no free text, no
user id (the tenant is the user's personal workspace). The same report
for the same item and reason within `DEDUPE_HOURS` is returned instead of
stored again, so repeated clicks do not inflate the editor's queue.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

from saas_os.infra.db import select, tenant_session_scope

from marocassist.knowledge.models import KnowledgeReport

ReasonCode = Literal["outdated", "incorrect", "broken_link", "other"]
DEDUPE_HOURS = 24


@dataclass(frozen=True)
class ReportResult:
    report_id: uuid.UUID
    created_at: datetime
    created: bool


def create_report(tenant_id: uuid.UUID, item_id: str, reason_code: ReasonCode) -> ReportResult:
    since = datetime.now(UTC) - timedelta(hours=DEDUPE_HOURS)
    with tenant_session_scope(tenant_id) as session:
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
        session.flush()
        return ReportResult(row.report_id, row.created_at, created=True)


def delete_for_tenant(tenant_id: uuid.UUID) -> None:
    """Purge participant step. Idempotent. No FOR UPDATE: the table has no
    UPDATE grant, and the purge runs once per tenant under SaaS-OS's lock."""
    with tenant_session_scope(tenant_id) as session:
        rows = session.execute(
            select(KnowledgeReport).where(KnowledgeReport.tenant_id == tenant_id)
        ).scalars()
        for row in rows.all():
            session.delete(row)
