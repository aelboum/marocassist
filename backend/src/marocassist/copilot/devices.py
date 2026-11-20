"""Copilot device pairing on top of SaaS-OS service accounts and API keys.

One paired browser = one SaaS-OS service account in the user's personal
tenant, holding only the `copilot_client` role (`marocassist.copilot:use`),
with one API key whose expiry is at most 12 hours away
(`marocassist.config`). Nothing here stores or logs the raw key: SaaS-OS
keeps only its hash and returns the raw value once.

Every step is a Core call with the signed-in user as `UserCaller`, so
SaaS-OS enforces authority and anti-amplification (the user can only give
the device permissions the user holds) and writes the audit rows in the
same transaction as each change.

There is no refresh with the device key itself: SaaS-OS lets a service
account rotate its key only with tenant-wide `api_key:rotate`, which would
let a stolen extension key mint keys. Renewal is a new pairing, started by
the signed-in user from the web app.
"""

from __future__ import annotations

import logging
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from saas_os.core.api_keys import (
    create_service_account_api_key,
    list_api_keys,
    revoke_service_account_api_key,
)
from saas_os.core.authority import UserCaller
from saas_os.core.identity import (
    ServiceAccount,
    ServiceAccountStatus,
    create_service_account,
    disable_service_account,
    get_service_account,
    list_service_accounts,
)
from saas_os.core.rbac import assign_service_account_role, list_roles
from saas_os.infra.db import acquire_tenant_advisory_lock, tenant_session_scope

from marocassist.config import get_settings
from marocassist.permissions import COPILOT_CLIENT_ROLE

logger = logging.getLogger(__name__)

DEVICE_NAME_PREFIX = "copilot-device-"
_KEY_NAME = "copilot"


class DeviceLimitReachedError(Exception):
    """The tenant already has the maximum number of active devices."""


class DeviceHistoryFullError(Exception):
    """The tenant has paired the maximum number of devices over its
    lifetime (`MAROCASSIST_COPILOT_MAX_DEVICE_HISTORY`)."""


class DeviceNotFoundError(Exception):
    """No Copilot device with that id in this tenant."""


@dataclass(frozen=True)
class Device:
    id: uuid.UUID
    status: str
    created_at: datetime
    key_expires_at: datetime | None


@dataclass(frozen=True)
class PairingResult:
    device_id: uuid.UUID
    api_key: str
    expires_at: datetime


def _is_device(name: str) -> bool:
    return name.startswith(DEVICE_NAME_PREFIX)


def _device_accounts(tenant_id: uuid.UUID) -> list[ServiceAccount]:
    return [account for account in list_service_accounts(tenant_id) if _is_device(account.name)]


def list_devices(tenant_id: uuid.UUID, *, include_disabled: bool = False) -> list[Device]:
    """Paired devices. A revoked device stays in SaaS-OS as a disabled
    service account (its audit trail refers to it); it is hidden here
    unless `include_disabled` (Phase 1 finding S-9)."""
    keys = list_api_keys(tenant_id)
    expiry: dict[uuid.UUID, datetime | None] = {}
    for key in keys:
        if key.service_account_id is not None and key.revoked_at is None:
            expiry.setdefault(key.service_account_id, key.expires_at)
    return [
        Device(
            id=account.id,
            status=account.status,
            created_at=account.created_at,
            key_expires_at=expiry.get(account.id),
        )
        for account in _device_accounts(tenant_id)
        if include_disabled or account.status == ServiceAccountStatus.ACTIVE.value
    ]


def _copilot_client_role_id(tenant_id: uuid.UUID) -> uuid.UUID:
    for role in list_roles(tenant_id):
        if role.name == COPILOT_CLIENT_ROLE:
            return role.id
    raise LookupError("copilot_client role missing; workspace was not provisioned")


_PAIRING_LOCK = "marocassist.copilot.pairing"


def pair_device(user_id: uuid.UUID, tenant_id: uuid.UUID) -> PairingResult:
    """Pair one device. Concurrent pairings of one tenant are serialised by a
    transaction-scoped advisory lock, so the device limit cannot be exceeded
    by a race."""
    with tenant_session_scope(tenant_id) as session:
        acquire_tenant_advisory_lock(session, tenant_id, _PAIRING_LOCK)
        return _pair_device_locked(user_id, tenant_id)


def _pair_device_locked(user_id: uuid.UUID, tenant_id: uuid.UUID) -> PairingResult:
    settings = get_settings()
    caller = UserCaller(user_id)
    accounts = _device_accounts(tenant_id)
    active = [a for a in accounts if a.status == ServiceAccountStatus.ACTIVE.value]
    if len(active) >= settings.copilot_max_devices:
        raise DeviceLimitReachedError
    if len(accounts) >= settings.copilot_max_device_history:
        raise DeviceHistoryFullError

    role_id = _copilot_client_role_id(tenant_id)
    account = create_service_account(
        tenant_id, f"{DEVICE_NAME_PREFIX}{secrets.token_hex(6)}", caller=caller
    )
    try:
        assign_service_account_role(
            caller=caller, tenant_id=tenant_id, service_account_id=account.id, role_id=role_id
        )
        expires_at = datetime.now(UTC) + timedelta(seconds=settings.copilot_key_ttl_seconds)
        _key, raw_key = create_service_account_api_key(
            caller=caller,
            tenant_id=tenant_id,
            service_account_id=account.id,
            name=_KEY_NAME,
            expires_at=expires_at,
        )
    except Exception:
        # Leave no half-paired, still-active machine identity behind.
        disable_service_account(tenant_id, account.id, caller=caller)
        raise
    logger.info("copilot_device_paired", extra={"tenant_id": str(tenant_id)})
    return PairingResult(device_id=account.id, api_key=raw_key, expires_at=expires_at)


def revoke_device(user_id: uuid.UUID, tenant_id: uuid.UUID, device_id: uuid.UUID) -> None:
    """Revoke every key of the device, then disable it. Idempotent. Either
    step alone already stops the device: SaaS-OS re-reads both the key and
    the service-account status on every request."""
    account = get_service_account(tenant_id, device_id)
    if account is None or not _is_device(account.name):
        raise DeviceNotFoundError
    caller = UserCaller(user_id)
    for key in list_api_keys(tenant_id):
        if key.service_account_id == device_id and key.revoked_at is None:
            revoke_service_account_api_key(caller=caller, tenant_id=tenant_id, key_id=key.id)
    disable_service_account(tenant_id, device_id, caller=caller)
    logger.info("copilot_device_revoked", extra={"tenant_id": str(tenant_id)})
