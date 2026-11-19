"""Data access for `marocassist.workspace_settings` -- the only module that
touches the table.

Every function takes a *verified* tenant id (`RequestContext.tenant_id`,
or the tenant Core is purging) and runs in
`saas_os.infra.db.tenant_session_scope(tenant_id)`, which binds the session
to that tenant for Row-Level Security. The explicit tenant predicate is
kept as defence in depth.
"""

from __future__ import annotations

import uuid
from typing import Literal

from saas_os.infra.db import select, tenant_session_scope

from marocassist.accounts.models import WorkspaceSettings

Locale = Literal["nl", "fr", "ar", "en"]
SUPPORTED_LOCALES: tuple[Locale, ...] = ("nl", "fr", "ar", "en")
DEFAULT_LOCALE: Locale = "nl"


def read_locale(tenant_id: uuid.UUID) -> str:
    with tenant_session_scope(tenant_id) as session:
        locale = session.execute(
            select(WorkspaceSettings.locale).where(WorkspaceSettings.tenant_id == tenant_id)
        ).scalar_one_or_none()
    return locale or DEFAULT_LOCALE


def write_locale(tenant_id: uuid.UUID, locale: Locale) -> str:
    if locale not in SUPPORTED_LOCALES:
        raise ValueError("unsupported locale")
    with tenant_session_scope(tenant_id) as session:
        row = session.execute(
            select(WorkspaceSettings)
            .where(WorkspaceSettings.tenant_id == tenant_id)
            .with_for_update()
        ).scalar_one_or_none()
        if row is None:
            session.add(WorkspaceSettings(tenant_id=tenant_id, locale=locale))
        else:
            row.locale = locale
    return locale


def delete_for_tenant(tenant_id: uuid.UUID) -> None:
    """Purge participant step. Idempotent."""
    with tenant_session_scope(tenant_id) as session:
        rows = (
            session.execute(
                select(WorkspaceSettings)
                .where(WorkspaceSettings.tenant_id == tenant_id)
                .with_for_update()
            )
            .scalars()
            .all()
        )
        for row in rows:
            session.delete(row)
