"""Permissions and roles MarocAssist declares into SaaS-OS's shared catalog.

Every product resource is prefixed `marocassist.` so it can never collide
with a SaaS-OS or another product's pair. Registration is idempotent and
runs in `marocassist.migrate` (needs the database), never at import time.
Registering grants nothing; roles are created per personal tenant by
`marocassist.accounts.provisioning`.
"""

from __future__ import annotations

from saas_os.core.permission_grants import PermissionGrantMigration
from saas_os.core.rbac import register_permission

WORKSPACE = "marocassist.workspace"
COPILOT = "marocassist.copilot"
PROFILE = "marocassist.profile"
CONSENT = "marocassist.consent"
ACCOUNT = "marocassist.account"
KNOWLEDGE = "marocassist.knowledge"

READ = "read"
UPDATE = "update"
PAIR = "pair"  # create, list and revoke Copilot device pairings
USE = "use"  # call the Copilot API with a paired device credential
ONBOARD = "onboard"  # complete onboarding: profile + required consents at once
EXPORT = "export"  # download a copy of the account's product data
DELETE = "delete"  # request deletion of the account
REPORT = "report"  # report a knowledge item as outdated or incorrect

PHASE_1_PERMISSIONS: tuple[tuple[str, str], ...] = (
    (WORKSPACE, READ),
    (WORKSPACE, UPDATE),
    (COPILOT, PAIR),
    (COPILOT, USE),
)

# Added in Phase 2. Tenants provisioned before Phase 2 receive them through
# the declared grant migration below (SaaS-OS ADR-0060), never by editing
# roles in place.
PHASE_2_PERMISSIONS: tuple[tuple[str, str], ...] = (
    (PROFILE, READ),
    (PROFILE, UPDATE),
    (CONSENT, READ),
    (CONSENT, UPDATE),
    (ACCOUNT, ONBOARD),
    (ACCOUNT, EXPORT),
    (ACCOUNT, DELETE),
)

# Added in Phase 3: read the curated knowledge (search, items, facts,
# consulates) and report an item. Existing tenants receive them through
# grant migration 0002 below.
PHASE_3_PERMISSIONS: tuple[tuple[str, str], ...] = (
    (KNOWLEDGE, READ),
    (KNOWLEDGE, REPORT),
)

PRODUCT_PERMISSIONS: tuple[tuple[str, str], ...] = (
    PHASE_1_PERMISSIONS + PHASE_2_PERMISSIONS + PHASE_3_PERMISSIONS
)

# SaaS-OS permissions the owner needs to pair a device on their own tenant:
# create a service account, give it the Copilot role, issue and revoke its
# key, and disable it (verified at the pin: `create_service_account_api_key`
# checks `api_key:create`, `revoke_service_account_api_key` checks
# `api_key:revoke`, `disable_service_account` checks
# `service_account:disable`). Granted only inside the user's own personal
# tenant, which has no other member.
PLATFORM_PAIRING_PERMISSIONS: tuple[tuple[str, str], ...] = (
    ("service_account", "create"),
    ("service_account", "disable"),
    ("service_account_role", "create"),
    ("api_key", "create"),
    ("api_key", "revoke"),
)

OWNER_ROLE = "owner"
COPILOT_CLIENT_ROLE = "copilot_client"

ROLE_PERMISSIONS: dict[str, tuple[tuple[str, str], ...]] = {
    OWNER_ROLE: PRODUCT_PERMISSIONS + PLATFORM_PAIRING_PERMISSIONS,
    # A paired browser extension can do exactly one thing: call Copilot
    # routes that opt in to API keys. No workspace, profile or billing.
    COPILOT_CLIENT_ROLE: ((COPILOT, USE),),
}


# Append-only (SaaS-OS `saas_os.core.permission_grants`): an applied
# migration is never edited; a later change is a new entry. Applied to
# existing tenants by a platform operator:
#   saas-os-operator apply-permission-grants --namespace marocassist
#     --module marocassist.permissions --all-tenants --reason "..." [--apply]
GRANT_NAMESPACE = "marocassist"
PERMISSION_GRANT_MIGRATIONS: tuple[PermissionGrantMigration, ...] = (
    PermissionGrantMigration(
        id="0001_owner_profile_consent_account",
        namespace=GRANT_NAMESPACE,
        role_name=OWNER_ROLE,
        permissions=PHASE_2_PERMISSIONS,
        reason="Phase 2: profile, consents, onboarding, export and deletion request",
    ),
    PermissionGrantMigration(
        id="0002_owner_knowledge",
        namespace=GRANT_NAMESPACE,
        role_name=OWNER_ROLE,
        permissions=PHASE_3_PERMISSIONS,
        reason="Phase 3: read curated knowledge and report outdated items",
    ),
)


def register_permissions() -> None:
    for resource, action in PRODUCT_PERMISSIONS + PLATFORM_PAIRING_PERMISSIONS:
        register_permission(resource, action)
