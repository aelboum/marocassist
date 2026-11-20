"""Profile, consents, onboarding and deletion requests of a personal tenant.

The only module that touches `marocassist.profiles`, `consents` and
`deletion_requests`. Every function takes a *verified* tenant id
(`RequestContext.tenant_id`, or the tenant Core is purging) and the verified
user id, and runs in `tenant_session_scope(tenant_id)` (Row-Level Security).

Audit: every change to a consent, the onboarding, a profile change and a
deletion request writes a SaaS-OS audit row with
`record_in_transaction` in the *same* transaction as the change, so a
change without its audit row cannot be committed. Audit metadata never
holds personal values: purposes, versions, booleans and field *names* only.

Data minimisation (Phase 2 decision P2-2): an optional display name, the
consulate (a code), the country of residence and a self-declared 18+
confirmation (P2-4). Nothing else.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from saas_os.core.audit_log import record_in_transaction
from saas_os.core.authority import UserCaller
from saas_os.infra.db import (
    Session,
    acquire_tenant_advisory_lock,
    select,
    tenant_session_scope,
)

from marocassist.accounts.models import Consent, DeletionRequest, Profile, WorkspaceSettings
from marocassist.accounts.workspace_settings import SUPPORTED_LOCALES, Locale

# Draft privacy notice, not legally reviewed (P2-5). A new text gets a new
# version; users are asked to accept it again.
PRIVACY_NOTICE_VERSION = "2026-11-draft"
PRODUCT_EMAILS_VERSION = "2026-11-draft"

ConsentPurpose = Literal["privacy_notice", "product_emails"]
CONSENT_VERSIONS: dict[str, str] = {
    "privacy_notice": PRIVACY_NOTICE_VERSION,
    "product_emails": PRODUCT_EMAILS_VERSION,
}
# Accepting the privacy notice is required to use the service; withdrawing
# it is done by deleting the account, not by a consent switch.
REQUIRED_PURPOSES = frozenset({"privacy_notice"})

# Moroccan consulates-general in the Netherlands (P2-3). Codes only; names
# and addresses are editorial data (Phase 3). To be verified by the owner.
CONSULATES: tuple[str, ...] = ("nl-amsterdam", "nl-den-bosch", "nl-rotterdam", "nl-utrecht")
RESIDENCE_COUNTRY = "NL"  # MVP: the Netherlands only (D-17)

ConsentSource = Literal["web", "extension"]


class NotOnboardedError(Exception):
    """The profile does not exist yet: onboarding comes first."""


class ConsentRefusedError(Exception):
    """The consent change is not allowed (unknown purpose, stale version,
    or withdrawing a required consent)."""


class OnboardingRefusedError(Exception):
    """Onboarding input is not acceptable (age not confirmed, stale
    privacy-notice version, unknown consulate)."""


@dataclass(frozen=True)
class ProfileView:
    display_name: str | None
    consulate: str | None
    residence_country: str
    onboarded_at: datetime | None


@dataclass(frozen=True)
class ConsentView:
    purpose: str
    version: str
    granted: bool
    source: str
    decided_at: datetime
    current_version: str


@dataclass(frozen=True)
class OnboardingStatus:
    onboarded: bool
    privacy_notice_current: bool


def _audit(
    session: Session,
    user_id: uuid.UUID,
    tenant_id: uuid.UUID,
    action: str,
    *,
    resource_type: str,
    metadata: dict[str, object],
    resource_id: str | None = None,
) -> None:
    record_in_transaction(
        session,
        caller=UserCaller(user_id),
        tenant_id=tenant_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        metadata=metadata,
    )


def _clean_name(display_name: str | None) -> str | None:
    if display_name is None:
        return None
    cleaned = " ".join(display_name.split())
    return cleaned or None


def _check_consulate(consulate: str | None) -> None:
    if consulate is not None and consulate not in CONSULATES:
        raise OnboardingRefusedError("unknown consulate")


def _profile(session: Session, tenant_id: uuid.UUID) -> Profile | None:
    return session.execute(
        select(Profile).where(Profile.tenant_id == tenant_id).with_for_update()
    ).scalar_one_or_none()


def _view(row: Profile) -> ProfileView:
    return ProfileView(
        display_name=row.display_name,
        consulate=row.consulate,
        residence_country=row.residence_country,
        onboarded_at=row.onboarded_at,
    )


# --- Profile -------------------------------------------------------------------------


def read_profile(tenant_id: uuid.UUID) -> ProfileView | None:
    with tenant_session_scope(tenant_id) as session:
        row = session.execute(
            select(Profile).where(Profile.tenant_id == tenant_id)
        ).scalar_one_or_none()
        return None if row is None else _view(row)


def update_profile(
    user_id: uuid.UUID, tenant_id: uuid.UUID, *, display_name: str | None, consulate: str | None
) -> ProfileView:
    _check_consulate(consulate)
    name = _clean_name(display_name)
    with tenant_session_scope(tenant_id) as session:
        row = _profile(session, tenant_id)
        if row is None:
            raise NotOnboardedError
        changed = [
            field
            for field, old, new in (
                ("display_name", row.display_name, name),
                ("consulate", row.consulate, consulate),
            )
            if old != new
        ]
        if changed:
            row.display_name = name
            row.consulate = consulate
            row.updated_at = datetime.now(UTC)
            _audit(
                session,
                user_id,
                tenant_id,
                "marocassist.profile.update",
                resource_type="marocassist.profile",
                metadata={"fields": changed},
            )
        return _view(row)


# --- Consents ------------------------------------------------------------------------


def read_consents(tenant_id: uuid.UUID) -> list[ConsentView]:
    with tenant_session_scope(tenant_id) as session:
        rows = (
            session.execute(
                select(Consent).where(Consent.tenant_id == tenant_id).order_by(Consent.purpose)
            )
            .scalars()
            .all()
        )
        return [
            ConsentView(
                purpose=row.purpose,
                version=row.version,
                granted=row.granted,
                source=row.source,
                decided_at=row.decided_at,
                current_version=CONSENT_VERSIONS.get(row.purpose, ""),
            )
            for row in rows
        ]


def _set_consent_in(
    session: Session,
    user_id: uuid.UUID,
    tenant_id: uuid.UUID,
    purpose: str,
    *,
    granted: bool,
    version: str,
    source: ConsentSource,
) -> bool:
    """Record one consent decision in `session`; returns whether it changed."""
    current = CONSENT_VERSIONS.get(purpose)
    if current is None or version != current:
        raise ConsentRefusedError("unknown purpose or stale version")
    if purpose in REQUIRED_PURPOSES and not granted:
        raise ConsentRefusedError("required consent")
    row = session.execute(
        select(Consent)
        .where(Consent.tenant_id == tenant_id, Consent.purpose == purpose)
        .with_for_update()
    ).scalar_one_or_none()
    if row is not None and row.granted == granted and row.version == version:
        return False
    now = datetime.now(UTC)
    if row is None:
        session.add(
            Consent(
                tenant_id=tenant_id,
                purpose=purpose,
                version=version,
                granted=granted,
                source=source,
                decided_at=now,
            )
        )
    else:
        row.granted = granted
        row.version = version
        row.source = source
        row.decided_at = now
    _audit(
        session,
        user_id,
        tenant_id,
        "marocassist.consent.grant" if granted else "marocassist.consent.withdraw",
        resource_type="marocassist.consent",
        metadata={"purpose": purpose, "version": version, "granted": granted, "source": source},
        resource_id=purpose,
    )
    return True


def set_consent(
    user_id: uuid.UUID,
    tenant_id: uuid.UUID,
    purpose: str,
    *,
    granted: bool,
    version: str,
    source: ConsentSource = "web",
) -> bool:
    with tenant_session_scope(tenant_id) as session:
        if _profile(session, tenant_id) is None:
            raise NotOnboardedError
        return _set_consent_in(
            session, user_id, tenant_id, purpose, granted=granted, version=version, source=source
        )


# --- Onboarding ----------------------------------------------------------------------


def onboarding_status(tenant_id: uuid.UUID) -> OnboardingStatus:
    with tenant_session_scope(tenant_id) as session:
        onboarded_at = session.execute(
            select(Profile.onboarded_at).where(Profile.tenant_id == tenant_id)
        ).scalar_one_or_none()
        notice = session.execute(
            select(Consent.version, Consent.granted).where(
                Consent.tenant_id == tenant_id, Consent.purpose == "privacy_notice"
            )
        ).one_or_none()
    current = notice is not None and bool(notice[1]) and notice[0] == PRIVACY_NOTICE_VERSION
    return OnboardingStatus(onboarded=onboarded_at is not None, privacy_notice_current=current)


def complete_onboarding(
    user_id: uuid.UUID,
    tenant_id: uuid.UUID,
    *,
    display_name: str | None,
    consulate: str | None,
    locale: Locale,
    age_confirmed: bool,
    privacy_notice_version: str,
    product_emails: bool,
) -> bool:
    """Create the profile, set the language and record the consents in one
    transaction. Idempotent: returns False (and changes nothing) when the
    user is already onboarded. Concurrent first calls are serialised by the
    tenant advisory lock taken here."""
    if not age_confirmed:
        raise OnboardingRefusedError("age not confirmed")
    if privacy_notice_version != PRIVACY_NOTICE_VERSION:
        raise OnboardingRefusedError("stale privacy notice")
    if locale not in SUPPORTED_LOCALES:
        raise OnboardingRefusedError("unsupported locale")
    _check_consulate(consulate)
    now = datetime.now(UTC)
    with tenant_session_scope(tenant_id) as session:
        acquire_tenant_advisory_lock(session, tenant_id, _ONBOARDING_LOCK)
        if _profile(session, tenant_id) is not None:
            return False
        session.add(
            Profile(
                tenant_id=tenant_id,
                display_name=_clean_name(display_name),
                consulate=consulate,
                residence_country=RESIDENCE_COUNTRY,
                age_confirmed=True,
                onboarded_at=now,
                updated_at=now,
            )
        )
        settings = session.execute(
            select(WorkspaceSettings)
            .where(WorkspaceSettings.tenant_id == tenant_id)
            .with_for_update()
        ).scalar_one_or_none()
        if settings is None:
            session.add(WorkspaceSettings(tenant_id=tenant_id, locale=locale))
        else:
            settings.locale = locale
        _set_consent_in(
            session,
            user_id,
            tenant_id,
            "privacy_notice",
            granted=True,
            version=privacy_notice_version,
            source="web",
        )
        _set_consent_in(
            session,
            user_id,
            tenant_id,
            "product_emails",
            granted=product_emails,
            version=PRODUCT_EMAILS_VERSION,
            source="web",
        )
        _audit(
            session,
            user_id,
            tenant_id,
            "marocassist.account.onboard",
            resource_type="marocassist.profile",
            metadata={"privacy_notice_version": privacy_notice_version, "age_confirmed": True},
        )
    return True


_ONBOARDING_LOCK = "marocassist.onboarding"


# --- Deletion request ----------------------------------------------------------------


def read_deletion_request(tenant_id: uuid.UUID) -> datetime | None:
    with tenant_session_scope(tenant_id) as session:
        return session.execute(
            select(DeletionRequest.requested_at).where(DeletionRequest.tenant_id == tenant_id)
        ).scalar_one_or_none()


def request_deletion(user_id: uuid.UUID, tenant_id: uuid.UUID) -> tuple[datetime, bool]:
    """Record the request (idempotent). Returns `(requested_at, created)`."""
    with tenant_session_scope(tenant_id) as session:
        acquire_tenant_advisory_lock(session, tenant_id, _DELETION_LOCK)
        existing = session.execute(
            select(DeletionRequest.requested_at).where(DeletionRequest.tenant_id == tenant_id)
        ).scalar_one_or_none()
        if existing is not None:
            return existing, False
        now = datetime.now(UTC)
        session.add(DeletionRequest(tenant_id=tenant_id, requested_by=user_id, requested_at=now))
        _audit(
            session,
            user_id,
            tenant_id,
            "marocassist.account.deletion_request",
            resource_type="marocassist.account",
            metadata={"channel": "web"},
        )
    return now, True


_DELETION_LOCK = "marocassist.deletion_request"


# --- Purge ---------------------------------------------------------------------------


def delete_for_tenant(tenant_id: uuid.UUID) -> None:
    """Purge participant step. Idempotent."""
    with tenant_session_scope(tenant_id) as session:
        # No FOR UPDATE: `deletion_requests` has no UPDATE grant, and
        # PostgreSQL requires it for row locks. The purge runs once per
        # tenant under SaaS-OS's purge lock.
        for model in (Consent, DeletionRequest, Profile):
            rows = session.execute(select(model).where(model.tenant_id == tenant_id)).scalars()
            for row in rows.all():
                session.delete(row)
