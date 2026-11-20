"""Export of everything MarocAssist stores for one personal tenant.

Product data only. What the identity provider (ZITADEL) holds -- email
address, password hash, MFA factors -- is exported there; SaaS-OS's audit
log is retained under its own policy (docs/architecture/SECURITY_AND_PRIVACY.md,
Q-P6). The export says so in `notes`, so the user knows where the rest is.

The export itself is audited (`marocassist.account.export`) in its own
tenant transaction; the audit metadata holds no data, only the format
version.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from saas_os.core.audit_log import record_in_transaction
from saas_os.core.authority import UserCaller
from saas_os.infra.db import tenant_session_scope

from marocassist.accounts.profile import read_consents, read_deletion_request, read_profile
from marocassist.accounts.workspace_settings import read_locale
from marocassist.copilot.devices import list_devices

EXPORT_FORMAT_VERSION = 1

NOTES = (
    "Account sign-in data (email address, password, multi-factor settings) is held by the "
    "identity provider and can be viewed and exported there.",
    "Security audit records are kept separately under the retention policy in the privacy notice.",
)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def build_export(user_id: uuid.UUID, tenant_id: uuid.UUID) -> dict[str, Any]:
    profile = read_profile(tenant_id)
    deletion_requested_at = read_deletion_request(tenant_id)
    export: dict[str, Any] = {
        "format_version": EXPORT_FORMAT_VERSION,
        "exported_at": datetime.now(UTC).isoformat(),
        "user_id": str(user_id),
        "workspace_id": str(tenant_id),
        "settings": {"locale": read_locale(tenant_id)},
        "profile": None
        if profile is None
        else {
            "display_name": profile.display_name,
            "consulate": profile.consulate,
            "residence_country": profile.residence_country,
            "onboarded_at": _iso(profile.onboarded_at),
        },
        "consents": [
            {
                "purpose": consent.purpose,
                "version": consent.version,
                "granted": consent.granted,
                "source": consent.source,
                "decided_at": _iso(consent.decided_at),
            }
            for consent in read_consents(tenant_id)
        ],
        "copilot_devices": [
            {
                "id": str(device.id),
                "status": device.status,
                "created_at": _iso(device.created_at),
                "key_expires_at": _iso(device.key_expires_at),
            }
            for device in list_devices(tenant_id, include_disabled=True)
        ],
        "deletion_request": None
        if deletion_requested_at is None
        else {"requested_at": _iso(deletion_requested_at)},
        "notes": list(NOTES),
    }
    with tenant_session_scope(tenant_id) as session:
        record_in_transaction(
            session,
            caller=UserCaller(user_id),
            tenant_id=tenant_id,
            action="marocassist.account.export",
            resource_type="marocassist.account",
            metadata={"format_version": EXPORT_FORMAT_VERSION},
        )
    return export
