"""Tables of the accounts module, in the product's own schema (ADR-0016 of
SaaS-OS). Created by `marocassist/migrations/versions/0001_*`.

- `personal_workspaces` is a global lookup: which tenant is a user's
  personal one. It cannot be tenant-scoped (the tenant is what is being
  looked up). It holds only two opaque ids, is queried only by the
  verified actor id from the session, and the application role may only
  SELECT and INSERT it (no UPDATE), plus DELETE for the purge participant.
- `workspace_settings`, `profiles`, `consents` and `deletion_requests` are
  tenant-owned: `tenant_id` foreign key and forced Row-Level Security
  through SaaS-OS's `tenant_rls_statements` (migrations 0001 and 0002).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from saas_os.infra.db import (
    Base,
    Boolean,
    DateTime,
    ForeignKey,
    Mapped,
    String,
    mapped_column,
    now,
)

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


class Profile(Base):
    """Phase 2 profile: deliberately minimal (data minimisation). No birth
    date, nationality, civil status or document numbers. `consulate` is a
    code from `marocassist.accounts.profile.CONSULATES`."""

    __tablename__ = "profiles"
    __table_args__ = {"schema": SCHEMA}

    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("core.tenants.id"), primary_key=True)
    display_name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    consulate: Mapped[str | None] = mapped_column(String(32), nullable=True)
    residence_country: Mapped[str] = mapped_column(String(2), nullable=False)
    age_confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    onboarded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=now()
    )


class Consent(Base):
    """Current decision per purpose. The history of every change is the
    SaaS-OS audit log (one row per change, same transaction)."""

    __tablename__ = "consents"
    __table_args__ = {"schema": SCHEMA}

    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("core.tenants.id"), primary_key=True)
    purpose: Mapped[str] = mapped_column(String(40), primary_key=True)
    version: Mapped[str] = mapped_column(String(40), nullable=False)
    granted: Mapped[bool] = mapped_column(Boolean, nullable=False)
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    decided_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=now()
    )


class DeletionRequest(Base):
    """A user's request to delete their account. One per tenant; carried
    out by an operator (docs/runbooks/ACCOUNT_DELETION.md), whose purge of
    the tenant removes this row too."""

    __tablename__ = "deletion_requests"
    __table_args__ = {"schema": SCHEMA}

    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("core.tenants.id"), primary_key=True)
    requested_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("core.users.id"), nullable=False)
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=now()
    )
