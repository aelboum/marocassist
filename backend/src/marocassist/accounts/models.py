"""Tables of the accounts module, in the product's own schema (ADR-0016 of
SaaS-OS). Created by `marocassist/migrations/versions/0001_*`.

- `personal_workspaces` is a global lookup: which tenant is a user's
  personal one. It cannot be tenant-scoped (the tenant is what is being
  looked up). It holds only two opaque ids, is queried only by the
  verified actor id from the session, and the application role may only
  SELECT and INSERT it (no UPDATE), plus DELETE for the purge participant.
- `workspace_settings` is tenant-owned: `tenant_id` foreign key and forced
  Row-Level Security through SaaS-OS's `tenant_rls_statements`.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from saas_os.infra.db import Base, DateTime, ForeignKey, Mapped, String, mapped_column, now

SCHEMA = "marocassist"


class PersonalWorkspace(Base):
    __tablename__ = "personal_workspaces"
    __table_args__ = {"schema": SCHEMA}

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("core.users.id"), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("core.tenants.id"), nullable=False, unique=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=now()
    )


class WorkspaceSettings(Base):
    __tablename__ = "workspace_settings"
    __table_args__ = {"schema": SCHEMA}

    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("core.tenants.id"), primary_key=True)
    locale: Mapped[str] = mapped_column(String(8), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=now()
    )
