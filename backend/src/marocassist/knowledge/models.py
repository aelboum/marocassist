"""Tables of the knowledge module, in the product's own schema. Created by
`marocassist/migrations/versions/0003_*`.

Two stores, never mixed:

- **Global knowledge** (`knowledge_*`, `consulates`, `consulate_*`): no
  tenant or user column, no RLS. The application role may only SELECT it;
  the publishing loader writes it under the migrations role. Its models are
  added with the modules that read them (catalogue, search).
- **Tenant side**: `knowledge_reports` and `knowledge_review_reports`,
  tenant-owned with forced RLS and removed by the tenant purge. They refer
  to knowledge by id only.
- **Anonymous aggregate**: `knowledge_report_counts`, a per-item, per-reason,
  per-day counter without tenant or user columns (WP F).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from saas_os.infra.db import (
    JSON,
    Base,
    DateTime,
    ForeignKey,
    Integer,
    Mapped,
    String,
    mapped_column,
    now,
)

SCHEMA = "marocassist"


class KnowledgeReport(Base):
    """A user's "report outdated" for one item. Created once, never edited
    (no UPDATE grant); free text is deliberately not stored."""

    __tablename__ = "knowledge_reports"
    __table_args__ = {"schema": SCHEMA}

    report_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("core.tenants.id"), nullable=False)
    item_id: Mapped[str] = mapped_column(String(80), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=now()
    )


class KnowledgeReportCount(Base):
    """How many workspaces reported an item for a reason on a day. No tenant
    or user column: the daily review job reads it without crossing tenants."""

    __tablename__ = "knowledge_report_counts"
    __table_args__ = {"schema": SCHEMA}

    item_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    reason_code: Mapped[str] = mapped_column(String(16), primary_key=True)
    day: Mapped[date] = mapped_column(primary_key=True)
    count: Mapped[int] = mapped_column(Integer, nullable=False)


class KnowledgeReviewReport(Base):
    """The daily editor review report, written in the editorial tenant only.
    One per day (unique), never edited."""

    __tablename__ = "knowledge_review_reports"
    __table_args__ = {"schema": SCHEMA}

    report_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("core.tenants.id"), nullable=False)
    report_date: Mapped[date] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=now()
    )
    summary: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
