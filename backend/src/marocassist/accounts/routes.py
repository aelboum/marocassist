"""HTTP routes of the accounts module.

Route policies (SaaS-OS `assert_route_policies` refuses to start otherwise):

- `/v1/me/workspace`: *authenticated* (`get_current_actor`). It has no
  tenant yet -- it is how the web app finds or creates the personal one.
  The POST is a cookie mutation, so SaaS-OS's same-origin check (ADR-0044)
  applies to it.
- `/v1/tenants/{tenant_id}/workspace/settings`: *permission*
  (`require_permission`): authentication, tenant resolution (member or the
  same 404), per-tenant rate limit, RBAC. The handler reads the tenant from
  the verified `RequestContext`, never from the path.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from saas_os.api.context import RequestContext
from saas_os.api.dependencies import get_current_actor, require_permission

from marocassist.accounts.provisioning import ensure_personal_workspace, get_personal_tenant_id
from marocassist.accounts.workspace_settings import Locale, read_locale, write_locale
from marocassist.permissions import READ, UPDATE, WORKSPACE

router = APIRouter(prefix="/v1", tags=["accounts"])

_read_settings = require_permission(WORKSPACE, READ)
_update_settings = require_permission(WORKSPACE, UPDATE)


class WorkspaceResponse(BaseModel):
    tenant_id: uuid.UUID
    created: bool = False


class SettingsResponse(BaseModel):
    locale: str


class SettingsUpdate(BaseModel):
    locale: Locale


@router.get("/me/workspace", response_model=WorkspaceResponse)
def read_my_workspace(actor_id: uuid.UUID = Depends(get_current_actor)) -> WorkspaceResponse:
    tenant_id = get_personal_tenant_id(actor_id)
    if tenant_id is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="workspace_not_found")
    return WorkspaceResponse(tenant_id=tenant_id)


@router.post("/me/workspace", response_model=WorkspaceResponse)
def provision_my_workspace(
    actor_id: uuid.UUID = Depends(get_current_actor),
) -> WorkspaceResponse:
    tenant_id, created = ensure_personal_workspace(actor_id)
    return WorkspaceResponse(tenant_id=tenant_id, created=created)


@router.get("/tenants/{tenant_id}/workspace/settings", response_model=SettingsResponse)
def read_settings(context: RequestContext = Depends(_read_settings)) -> SettingsResponse:
    return SettingsResponse(locale=read_locale(context.tenant_id))


@router.put("/tenants/{tenant_id}/workspace/settings", response_model=SettingsResponse)
def update_settings(
    body: SettingsUpdate, context: RequestContext = Depends(_update_settings)
) -> SettingsResponse:
    return SettingsResponse(locale=write_locale(context.tenant_id, body.locale))
