"""HTTP routes of the accounts module.

Route policies (SaaS-OS `assert_route_policies` refuses to start otherwise):

- `/v1/me/workspace`: *authenticated* (`get_current_actor`). It has no
  tenant yet -- it is how the web app finds or creates the personal one.
  Creating it requires an email address the identity provider verified at
  this sign-in (`Session.verified_email`, set by SaaS-OS only when the ID
  token says `email_verified: true`). The address itself is never read or
  stored here.
- `/v1/tenants/{tenant_id}/...`: *permission* (`require_permission`):
  authentication, tenant resolution (member or the same 404), per-tenant
  rate limit, RBAC. Handlers read the tenant from the verified
  `RequestContext`, never from the path.

Every mutation is a cookie mutation from the web app, so SaaS-OS's
same-origin check (ADR-0044) applies to all of them.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from saas_os.api.context import RequestContext, RequestPrincipal
from saas_os.api.dependencies import get_current_actor, get_current_session, require_permission
from saas_os.api.errors import rate_limited, service_unavailable
from saas_os.core.identity import Session
from saas_os.infra.ratelimit import (
    RateLimitBackendError,
    RateLimitExceededError,
    enforce_rate_limit,
    get_ratelimit_config,
)

from marocassist.accounts.profile import (
    CONSENT_VERSIONS,
    CONSULATES,
    PRIVACY_NOTICE_VERSION,
    ConsentPurpose,
    ConsentRefusedError,
    NotOnboardedError,
    OnboardingRefusedError,
    complete_onboarding,
    onboarding_status,
    read_consents,
    read_profile,
    set_consent,
    update_profile,
)
from marocassist.accounts.provisioning import (
    ProvisioningBusyError,
    ProvisioningConflictError,
    ensure_personal_workspace,
    get_personal_tenant_id,
)
from marocassist.accounts.workspace_settings import Locale, read_locale, write_locale
from marocassist.permissions import (
    ACCOUNT,
    CONSENT,
    ONBOARD,
    PROFILE,
    READ,
    UPDATE,
    WORKSPACE,
)

router = APIRouter(prefix="/v1", tags=["accounts"])

_read_settings = require_permission(WORKSPACE, READ)
_update_settings = require_permission(WORKSPACE, UPDATE)
_read_profile = require_permission(PROFILE, READ)
_update_profile = require_permission(PROFILE, UPDATE)
_read_consents = require_permission(CONSENT, READ)
_update_consents = require_permission(CONSENT, UPDATE)
_onboard = require_permission(ACCOUNT, ONBOARD)


class WorkspaceResponse(BaseModel):
    tenant_id: uuid.UUID
    created: bool = False


class SettingsResponse(BaseModel):
    locale: str


class SettingsUpdate(BaseModel):
    locale: Locale


class OnboardingStatusOut(BaseModel):
    onboarded: bool
    privacy_notice_current: bool
    privacy_notice_version: str
    consulates: list[str]


class OnboardingIn(BaseModel):
    display_name: str | None = Field(default=None, max_length=80)
    consulate: str | None = Field(default=None, max_length=32)
    locale: Locale
    age_confirmed: bool
    privacy_notice_version: str = Field(max_length=40)
    product_emails: bool = False


class OnboardingOut(BaseModel):
    onboarded: bool
    created: bool


class ProfileOut(BaseModel):
    display_name: str | None
    consulate: str | None
    residence_country: str
    onboarded_at: datetime | None


class ProfileIn(BaseModel):
    display_name: str | None = Field(default=None, max_length=80)
    consulate: str | None = Field(default=None, max_length=32)


class ConsentOut(BaseModel):
    purpose: str
    version: str
    granted: bool
    source: str
    decided_at: datetime
    current_version: str


class ConsentIn(BaseModel):
    granted: bool
    version: str = Field(max_length=40)


def _require_user(context: RequestContext) -> uuid.UUID:
    # Defence in depth: none of these routes opts in to API keys.
    if context.principal is not RequestPrincipal.USER:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
    return context.actor_id


def _conflict(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)


def _unprocessable(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=detail)


# --- Personal workspace ------------------------------------------------------------------


@router.get("/me/workspace", response_model=WorkspaceResponse)
def read_my_workspace(actor_id: uuid.UUID = Depends(get_current_actor)) -> WorkspaceResponse:
    tenant_id = get_personal_tenant_id(actor_id)
    if tenant_id is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="workspace_not_found")
    return WorkspaceResponse(tenant_id=tenant_id)


async def _limit_provisioning(actor_id: uuid.UUID = Depends(get_current_actor)) -> uuid.UUID:
    """`require_permission`'s per-tenant limit cannot apply before a tenant
    exists, so the workspace call is limited per user with SaaS-OS's own
    limiter (fails closed when Redis is unavailable)."""
    try:
        await enforce_rate_limit(
            f"marocassist.workspace-provisioning:{actor_id}", config=get_ratelimit_config()
        )
    except RateLimitExceededError as exc:
        raise rate_limited(exc.retry_after_seconds) from None
    except RateLimitBackendError:
        raise service_unavailable(5) from None
    return actor_id


@router.post("/me/workspace", response_model=WorkspaceResponse)
def provision_my_workspace(
    actor_id: uuid.UUID = Depends(_limit_provisioning),
    session: Session = Depends(get_current_session),
) -> WorkspaceResponse:
    if session.verified_email is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="email_not_verified")
    try:
        tenant_id, created = ensure_personal_workspace(actor_id)
    except ProvisioningBusyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="try_again",
            headers={"Retry-After": "5"},
        ) from exc
    except ProvisioningConflictError as exc:
        raise _conflict("workspace_unavailable") from exc
    return WorkspaceResponse(tenant_id=tenant_id, created=created)


# --- Settings --------------------------------------------------------------------------------


@router.get("/tenants/{tenant_id}/workspace/settings", response_model=SettingsResponse)
def read_settings(context: RequestContext = Depends(_read_settings)) -> SettingsResponse:
    return SettingsResponse(locale=read_locale(context.tenant_id))


@router.put("/tenants/{tenant_id}/workspace/settings", response_model=SettingsResponse)
def update_settings(
    body: SettingsUpdate, context: RequestContext = Depends(_update_settings)
) -> SettingsResponse:
    return SettingsResponse(locale=write_locale(context.tenant_id, body.locale))


# --- Onboarding ------------------------------------------------------------------------------


@router.get("/tenants/{tenant_id}/onboarding", response_model=OnboardingStatusOut)
def read_onboarding(context: RequestContext = Depends(_read_profile)) -> OnboardingStatusOut:
    current = onboarding_status(context.tenant_id)
    return OnboardingStatusOut(
        onboarded=current.onboarded,
        privacy_notice_current=current.privacy_notice_current,
        privacy_notice_version=PRIVACY_NOTICE_VERSION,
        consulates=list(CONSULATES),
    )


@router.post("/tenants/{tenant_id}/onboarding", response_model=OnboardingOut)
def submit_onboarding(
    body: OnboardingIn, response: Response, context: RequestContext = Depends(_onboard)
) -> OnboardingOut:
    user_id = _require_user(context)
    try:
        created = complete_onboarding(
            user_id,
            context.tenant_id,
            display_name=body.display_name,
            consulate=body.consulate,
            locale=body.locale,
            age_confirmed=body.age_confirmed,
            privacy_notice_version=body.privacy_notice_version,
            product_emails=body.product_emails,
        )
    except (OnboardingRefusedError, ConsentRefusedError) as exc:
        raise _unprocessable("onboarding_refused") from exc
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return OnboardingOut(onboarded=True, created=created)


# --- Profile ---------------------------------------------------------------------------------


@router.get("/tenants/{tenant_id}/profile", response_model=ProfileOut)
def get_profile(context: RequestContext = Depends(_read_profile)) -> ProfileOut:
    profile = read_profile(context.tenant_id)
    if profile is None:
        raise _conflict("not_onboarded")
    return ProfileOut(**profile.__dict__)


@router.put("/tenants/{tenant_id}/profile", response_model=ProfileOut)
def put_profile(body: ProfileIn, context: RequestContext = Depends(_update_profile)) -> ProfileOut:
    user_id = _require_user(context)
    try:
        profile = update_profile(
            user_id, context.tenant_id, display_name=body.display_name, consulate=body.consulate
        )
    except OnboardingRefusedError as exc:
        raise _unprocessable("invalid_consulate") from exc
    except NotOnboardedError as exc:
        raise _conflict("not_onboarded") from exc
    return ProfileOut(**profile.__dict__)


# --- Consents --------------------------------------------------------------------------------


@router.get("/tenants/{tenant_id}/consents", response_model=list[ConsentOut])
def get_consents(context: RequestContext = Depends(_read_consents)) -> list[ConsentOut]:
    return [ConsentOut(**consent.__dict__) for consent in read_consents(context.tenant_id)]


@router.put("/tenants/{tenant_id}/consents/{purpose}", response_model=list[ConsentOut])
def put_consent(
    purpose: ConsentPurpose, body: ConsentIn, context: RequestContext = Depends(_update_consents)
) -> list[ConsentOut]:
    user_id = _require_user(context)
    if purpose not in CONSENT_VERSIONS:  # pragma: no cover -- the path type already limits it
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="purpose not found.")
    try:
        set_consent(user_id, context.tenant_id, purpose, granted=body.granted, version=body.version)
    except ConsentRefusedError as exc:
        raise _conflict("consent_refused") from exc
    except NotOnboardedError as exc:
        raise _conflict("not_onboarded") from exc
    return [ConsentOut(**consent.__dict__) for consent in read_consents(context.tenant_id)]
