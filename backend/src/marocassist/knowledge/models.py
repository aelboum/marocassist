"""Tables of the knowledge module, in the product's own schema. Created by
`marocassist/migrations/versions/0003_*`.

Two stores, never mixed:

- **Global knowledge** (`knowledge_*`, `consulates`, `consulate_*`): no
  tenant or user column, no RLS. The application role may only SELECT it;
  the publishing loader writes it under the migrations role. Its models are
  added with the modules that read them (catalogue, search).
- **Tenant side**: `knowledge_reports`, tenant-owned with forced RLS and
  removed by the tenant purge. It refers to knowledge by id only.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from saas_os.infra.db import (
    Base,
    DateTime,
    ForeignKey,
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
