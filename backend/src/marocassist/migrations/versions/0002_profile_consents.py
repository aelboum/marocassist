"""accounts: profiles, consents and deletion requests (Phase 2)

Revision ID: 0002_marocassist_profile
Revises: 0001_marocassist_accounts
Create Date: 2026-11-20 00:00:00.000000

Same consumer pattern as 0001: product schema, non-null `tenant_id` FK to
`core.tenants.id`, forced Row-Level Security through SaaS-OS's
`tenant_rls_statements`, explicit minimal grants to the application role.

- `profiles` and `consents` may be updated by the application.
- `deletion_requests` has no UPDATE grant: a request is created once and
  removed only by the tenant purge that carries it out.
"""

import os
import re
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from saas_os.infra.db.rls import tenant_rls_statements

revision: str = "0002_marocassist_profile"
down_revision: str | Sequence[str] | None = "0001_marocassist_accounts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SCHEMA = "marocassist"
_DEFAULT_APP_ROLE = "saas_os_app"


def _app_role() -> str:
    role = os.environ.get("APP_DB_USER", _DEFAULT_APP_ROLE)
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", role):
        raise ValueError("APP_DB_USER must be a plain SQL identifier")
    return role


def _tenant_pk() -> sa.Column:  # type: ignore[type-arg]
    return sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("core.tenants.id"), primary_key=True)


def upgrade() -> None:
    app_role = _app_role()

    op.create_table(
        "profiles",
        _tenant_pk(),
        sa.Column("display_name", sa.String(length=80), nullable=True),
        sa.Column("consulate", sa.String(length=32), nullable=True),
        sa.Column("residence_country", sa.String(length=2), nullable=False),
        sa.Column("age_confirmed", sa.Boolean(), nullable=False),
        sa.Column("onboarded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("residence_country ~ '^[A-Z]{2}$'", name="ck_profiles_country"),
        sa.CheckConstraint(
            "consulate IS NULL OR consulate ~ '^[a-z0-9-]{2,32}$'", name="ck_profiles_consulate"
        ),
        schema=_SCHEMA,
    )

    op.create_table(
        "consents",
        _tenant_pk(),
        sa.Column("purpose", sa.String(length=40), primary_key=True),
        sa.Column("version", sa.String(length=40), nullable=False),
        sa.Column("granted", sa.Boolean(), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column(
            "decided_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("source IN ('web', 'extension')", name="ck_consents_source"),
        schema=_SCHEMA,
    )

    op.create_table(
        "deletion_requests",
        _tenant_pk(),
        sa.Column("requested_by", sa.Uuid(), sa.ForeignKey("core.users.id"), nullable=False),
        sa.Column(
            "requested_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        schema=_SCHEMA,
    )

    for table in ("profiles", "consents", "deletion_requests"):
        for statement in tenant_rls_statements(table, schema=_SCHEMA):
            op.execute(statement)

    op.execute(f'GRANT SELECT, INSERT, UPDATE, DELETE ON {_SCHEMA}.profiles TO "{app_role}"')
    op.execute(f'GRANT SELECT, INSERT, UPDATE, DELETE ON {_SCHEMA}.consents TO "{app_role}"')
    op.execute(f'GRANT SELECT, INSERT, DELETE ON {_SCHEMA}.deletion_requests TO "{app_role}"')


def downgrade() -> None:
    app_role = _app_role()
    for table in ("deletion_requests", "consents", "profiles"):
        op.execute(f'REVOKE ALL ON {_SCHEMA}.{table} FROM "{app_role}"')
        op.drop_table(table, schema=_SCHEMA)
