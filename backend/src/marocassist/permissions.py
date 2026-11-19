"""Permissions and roles MarocAssist declares into SaaS-OS's shared catalog.

Every product resource is prefixed `marocassist.` so it can never collide
with a SaaS-OS or another product's pair. Registration is idempotent and
runs in `marocassist.migrate` (needs the database), never at import time.
Registering grants nothing; roles are created per personal tenant by
`marocassist.accounts.provisioning`.
"""

from __future__ import annotations

from saas_os.core.rbac import register_permission

WORKSPACE = "marocassist.workspace"
COPILOT = "marocassist.copilot"

READ = "read"
UPDATE = "update"
PAIR = "pair"  # create, list and revoke Copilot device pairings
USE = "use"  # call the Copilot API with a paired device credential

PRODUCT_PERMISSIONS: tuple[tuple[str, str], ...] = (
    (WORKSPACE, READ),
    (WORKSPACE, UPDATE),
    (COPILOT, PAIR),
    (COPILOT, USE),
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


def register_permissions() -> None:
    for resource, action in PRODUCT_PERMISSIONS + PLATFORM_PAIRING_PERMISSIONS:
        register_permission(resource, action)
