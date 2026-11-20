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
the mapping row the first committed.

Crash safety (Phase 1 finding S-8): the tenant's name is derived from the
user id (`personal_tenant_name`), and every provisioning step first checks
whether it is already done. If the process dies part-way, the next request
finds the half-provisioned tenant by name and finishes it instead of
creating a second one. A tenant is therefore never orphaned by a crash; a
leftover exists only while its user never comes back, and holds no product
data (the account-deletion runbook finds it by the same name).

Pool safety (S-8): the advisory-lock connection stays open while the Core
calls take a second pooled connection each. Many first logins at once
could otherwise hold every pooled connection for a lock and wait forever
for a second one. A per-process semaphore bounds concurrent provisionings
well below the pool size; waiting for it is bounded too.
"""

from __future__ import annotations

import hashlib
import logging
import threading
import uuid

from saas_os.core.authority import SystemAuthority, SystemCaller
from saas_os.core.identity import add_tenant_membership, get_membership
from saas_os.core.rbac import (
    assign_first_role_for_new_tenant,
    create_role,
    get_role_permission,
    grant_permission,
    list_membership_roles,
    list_roles,
    register_permission,
)
from saas_os.core.tenancy import (
    TenantStatus,
    create_tenant,
    find_tenants_by_name,
    transition_tenant_status,
)
from saas_os.infra.db import acquire_global_advisory_lock, select, session_scope

from marocassist.accounts.models import PersonalWorkspace
from marocassist.permissions import OWNER_ROLE, ROLE_PERMISSIONS

logger = logging.getLogger(__name__)

_PROVISIONING = SystemCaller(SystemAuthority.PROVISIONING)
_LOCK_NAMESPACE = "marocassist.personal_workspace"
_TENANT_NAME_PREFIX = "personal-"

# SaaS-OS's default pool is 5 + 10 overflow; two provisionings hold at most
# four connections. A request that waits longer than the timeout gets a
# retryable 503 instead of hanging a worker thread.
MAX_CONCURRENT_PROVISIONINGS = 2
_PROVISIONING_WAIT_SECONDS = 30.0
_provisioning_slots = threading.BoundedSemaphore(MAX_CONCURRENT_PROVISIONINGS)


class ProvisioningBusyError(Exception):
    """No provisioning slot became free in time; the client may retry."""


class ProvisioningConflictError(Exception):
    """The personal tenant cannot be (re)used: several tenants carry the
    name, or it is no longer active."""


def personal_tenant_name(user_id: uuid.UUID) -> str:
    """Stable, opaque tenant name for a user's personal tenant: a hash of
    the internal user id, never an email or a name."""
    digest = hashlib.sha256(f"marocassist.personal:{user_id}".encode()).hexdigest()
    return f"{_TENANT_NAME_PREFIX}{digest[:32]}"


def get_personal_tenant_id(user_id: uuid.UUID) -> uuid.UUID | None:
    with session_scope() as session:
        return session.execute(
            select(PersonalWorkspace.tenant_id).where(PersonalWorkspace.user_id == user_id)
        ).scalar_one_or_none()


def ensure_personal_workspace(user_id: uuid.UUID) -> tuple[uuid.UUID, bool]:
    """The user's personal tenant id, creating it on first use. Returns
    `(tenant_id, created)`. Idempotent, resumable, and safe under concurrent
    calls."""
    existing = get_personal_tenant_id(user_id)
    if existing is not None:
        return existing, False

    if not _provisioning_slots.acquire(timeout=_PROVISIONING_WAIT_SECONDS):
        raise ProvisioningBusyError
    try:
        with session_scope() as session:
            acquire_global_advisory_lock(session, _LOCK_NAMESPACE, str(user_id))
            existing = session.execute(
                select(PersonalWorkspace.tenant_id).where(PersonalWorkspace.user_id == user_id)
            ).scalar_one_or_none()
            if existing is not None:
                return existing, False
            tenant_id = _provision_tenant(user_id)
            session.add(PersonalWorkspace(user_id=user_id, tenant_id=tenant_id))
    finally:
        _provisioning_slots.release()
    logger.info("personal_workspace_created", extra={"tenant_id": str(tenant_id)})
    return tenant_id, True


def _find_or_create_tenant(user_id: uuid.UUID) -> uuid.UUID:
    name = personal_tenant_name(user_id)
    found = find_tenants_by_name(name)
    if len(found) > 1:
        raise ProvisioningConflictError
    if found:
        tenant = found[0]
        logger.info("personal_workspace_resumed", extra={"tenant_id": str(tenant.id)})
    else:
        tenant = create_tenant(name, caller=_PROVISIONING)
    if tenant.status == TenantStatus.PENDING.value:
        tenant = transition_tenant_status(tenant.id, TenantStatus.ACTIVE, caller=_PROVISIONING)
    if tenant.status != TenantStatus.ACTIVE.value:
        # Suspended or closing: provisioning never reopens a tenant.
        raise ProvisioningConflictError
    return tenant.id


def _provision_tenant(user_id: uuid.UUID) -> uuid.UUID:
    tenant_id = _find_or_create_tenant(user_id)

    existing_roles = {role.name: role.id for role in list_roles(tenant_id)}
    role_ids: dict[str, uuid.UUID] = {}
    for role_name, permissions in ROLE_PERMISSIONS.items():
        role_id = existing_roles.get(role_name)
        if role_id is None:
            role_id = create_role(tenant_id, role_name, caller=_PROVISIONING).id
        role_ids[role_name] = role_id
        for resource, action in permissions:
            permission = register_permission(resource, action)
            if get_role_permission(tenant_id, role_id, permission.id) is None:
                grant_permission(tenant_id, role_id, permission.id, caller=_PROVISIONING)

    membership = get_membership(tenant_id, user_id)
    if membership is None:
        membership = add_tenant_membership(tenant_id, user_id, caller=_PROVISIONING)
    if not list_membership_roles(tenant_id, membership.id):
        assign_first_role_for_new_tenant(
            tenant_id, membership.id, role_ids[OWNER_ROLE], caller=_PROVISIONING
        )
    return tenant_id
