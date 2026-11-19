"""Personal workspace provisioning: one SaaS-OS tenant per user (D-06).

SaaS-OS has no self-service sign-up route; a consumer creates a tenant's
initial authority structure with `SystemCaller(SystemAuthority.PROVISIONING)`
-- the purpose SaaS-OS documents for "a consumer's own provisioning/seed
code" (`saas_os.core.authority.caller.SystemAuthority`). Every Core call
below audits itself (actor SYSTEM, `system_authority: provisioning`).

Only the *verified* actor id of the current session is ever passed in
(`marocassist.accounts.routes`), never an id from a URL or a body, so a user
can only ever provision their own workspace.

Concurrency: two first requests of one user are serialised by a
transaction-scoped advisory lock keyed by the user id; the second one finds
the mapping row the first committed. If the process dies after Core created
the tenant but before the mapping committed, a PENDING-or-ACTIVE tenant
without a mapping is left behind and a new one is created on the next
request. It holds no product data and is reported in
docs/phase-1/PHASE1_REPORT.md as a known limitation.
"""

from __future__ import annotations

import logging
import uuid

from saas_os.core.authority import SystemAuthority, SystemCaller
from saas_os.core.identity import add_tenant_membership
from saas_os.core.rbac import (
    assign_first_role_for_new_tenant,
    create_role,
    grant_permission,
    register_permission,
)
from saas_os.core.tenancy import TenantStatus, create_tenant, transition_tenant_status
from saas_os.infra.db import acquire_global_advisory_lock, select, session_scope

from marocassist.accounts.models import PersonalWorkspace
from marocassist.permissions import OWNER_ROLE, ROLE_PERMISSIONS

logger = logging.getLogger(__name__)

_PROVISIONING = SystemCaller(SystemAuthority.PROVISIONING)
_LOCK_NAMESPACE = "marocassist.personal_workspace"


def get_personal_tenant_id(user_id: uuid.UUID) -> uuid.UUID | None:
    with session_scope() as session:
        return session.execute(
            select(PersonalWorkspace.tenant_id).where(PersonalWorkspace.user_id == user_id)
        ).scalar_one_or_none()


def ensure_personal_workspace(user_id: uuid.UUID) -> tuple[uuid.UUID, bool]:
    """The user's personal tenant id, creating it on first use. Returns
    `(tenant_id, created)`. Idempotent and safe under concurrent calls."""
    existing = get_personal_tenant_id(user_id)
    if existing is not None:
        return existing, False

    with session_scope() as session:
        acquire_global_advisory_lock(session, _LOCK_NAMESPACE, str(user_id))
        existing = session.execute(
            select(PersonalWorkspace.tenant_id).where(PersonalWorkspace.user_id == user_id)
        ).scalar_one_or_none()
        if existing is not None:
            return existing, False
        tenant_id = _provision_tenant(user_id)
        session.add(PersonalWorkspace(user_id=user_id, tenant_id=tenant_id))
    logger.info("personal_workspace_created", extra={"tenant_id": str(tenant_id)})
    return tenant_id, True


def _provision_tenant(user_id: uuid.UUID) -> uuid.UUID:
    # The tenant name is random and carries no personal data.
    tenant = create_tenant(f"personal-{uuid.uuid4().hex}", caller=_PROVISIONING)
    if tenant.status != TenantStatus.ACTIVE.value:
        tenant = transition_tenant_status(tenant.id, TenantStatus.ACTIVE, caller=_PROVISIONING)

    role_ids: dict[str, uuid.UUID] = {}
    for role_name, permissions in ROLE_PERMISSIONS.items():
        role = create_role(tenant.id, role_name, caller=_PROVISIONING)
        role_ids[role_name] = role.id
        for resource, action in permissions:
            permission = register_permission(resource, action)
            grant_permission(tenant.id, role.id, permission.id, caller=_PROVISIONING)

    membership = add_tenant_membership(tenant.id, user_id, caller=_PROVISIONING)
    assign_first_role_for_new_tenant(
        tenant.id, membership.id, role_ids[OWNER_ROLE], caller=_PROVISIONING
    )
    return tenant.id
