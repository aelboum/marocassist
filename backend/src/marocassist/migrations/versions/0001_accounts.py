"""accounts: personal workspace lookup and workspace settings

Revision ID: 0001_marocassist_accounts
Revises:
Create Date: 2026-11-19 00:00:00.000000

Follows the SaaS-OS consumer pattern (consumer guide sections 5 and 7):

1. the product's own schema `marocassist`, never `core`;
2. tenant-owned tables have a non-null `tenant_id` FK to `core.tenants.id`,
   and forced Row-Level Security through `tenant_rls_statements` (no
   hand-written policy);
3. explicit, minimal grants to the restricted application role.

`personal_workspaces` is the one deliberate global table (see
`marocassist/accounts/models.py`): no RLS is possible because the tenant is
what it looks up. Its grant has no UPDATE, so a mapping cannot be moved to
another tenant by application code.
"""

import os
import re
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from saas_os.infra.db.rls import tenant_rls_statements

revision: str = "0001_marocassist_accounts"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SCHEMA = "marocassist"
_DEFAULT_APP_ROLE = "saas_os_app"


def _app_role() -> str:
    role = os.environ.get("APP_DB_USER", _DEFAULT_APP_ROLE)
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", role):
        raise ValueError("APP_DB_USER must be a plain SQL identifier")
    return role


def upgrade() -> None:
    app_role = _app_role()
    op.execute(f"CREATE SCHEMA IF NOT EXISTS {_SCHEMA}")

    op.create_table(
        "personal_workspaces",
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("core.users.id"), primary_key=True),
        sa.Column(
            "tenant_id", sa.Uuid(), sa.ForeignKey("core.tenants.id"), nullable=False, unique=True
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        schema=_SCHEMA,
    )

    op.create_table(
        "workspace_settings",
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("core.tenants.id"), primary_key=True),
        sa.Column("locale", sa.String(length=8), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "locale IN ('nl', 'fr', 'ar', 'en')", name="ck_workspace_settings_locale"
        ),
        schema=_SCHEMA,
    )
    for statement in tenant_rls_statements("workspace_settings", schema=_SCHEMA):
        op.execute(statement)

    op.execute(f'GRANT USAGE ON SCHEMA {_SCHEMA} TO "{app_role}"')
    op.execute(f'GRANT SELECT, INSERT, DELETE ON {_SCHEMA}.personal_workspaces TO "{app_role}"')
    op.execute(
        f'GRANT SELECT, INSERT, UPDATE, DELETE ON {_SCHEMA}.workspace_settings TO "{app_role}"'
    )


def downgrade() -> None:
    app_role = _app_role()
    op.execute(f'REVOKE ALL ON {_SCHEMA}.workspace_settings FROM "{app_role}"')
    op.execute(f'REVOKE ALL ON {_SCHEMA}.personal_workspaces FROM "{app_role}"')
    op.drop_table("workspace_settings", schema=_SCHEMA)
    op.drop_table("personal_workspaces", schema=_SCHEMA)
    op.execute(f'REVOKE USAGE ON SCHEMA {_SCHEMA} FROM "{app_role}"')
    op.execute(f"DROP SCHEMA IF EXISTS {_SCHEMA}")
