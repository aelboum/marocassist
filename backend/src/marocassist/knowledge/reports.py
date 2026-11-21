"""Tenant-side "report outdated" rows. Every access runs in
`tenant_session_scope(tenant_id)`, so Row-Level Security applies."""

from __future__ import annotations

import uuid

from saas_os.infra.db import select, tenant_session_scope

from marocassist.knowledge.models import KnowledgeReport


def delete_for_tenant(tenant_id: uuid.UUID) -> None:
    """Purge participant step. Idempotent. No FOR UPDATE: the table has no
    UPDATE grant, and the purge runs once per tenant under SaaS-OS's lock."""
    with tenant_session_scope(tenant_id) as session:
        rows = session.execute(
            select(KnowledgeReport).where(KnowledgeReport.tenant_id == tenant_id)
        ).scalars()
        for row in rows.all():
            session.delete(row)
