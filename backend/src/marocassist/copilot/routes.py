"""HTTP routes of the Copilot module.

Device management (`/copilot/devices`) needs `marocassist.copilot:pair` and
is user-only: those routes do not opt in to API keys, so a paired
extension can never pair, list or revoke devices.

`/copilot/session` is the one route a paired extension may call in
Phase 1 (`api_key=True`, `marocassist.copilot:use`). It returns only ids
and the credential's expiry -- enough for the side panel to show
"connected until ..." -- and is the template for every later Copilot
route.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel
from saas_os.api.context import RequestContext, RequestPrincipal
from saas_os.api.dependencies import require_permission
from saas_os.api.errors import not_found
from saas_os.core.api_keys import get_api_key

from marocassist.copilot.devices import (
    DeviceHistoryFullError,
    DeviceLimitReachedError,
    DeviceNotFoundError,
    list_devices,
    pair_device,
    revoke_device,
)
from marocassist.permissions import COPILOT, PAIR, USE

router = APIRouter(prefix="/v1/tenants/{tenant_id}/copilot", tags=["copilot"])

_pair = require_permission(COPILOT, PAIR)
_use = require_permission(COPILOT, USE, api_key=True)


class DeviceOut(BaseModel):
    id: uuid.UUID
    status: str
    created_at: datetime
    key_expires_at: datetime | None


class PairingOut(BaseModel):
    device_id: uuid.UUID
    api_key: str
    expires_at: datetime


class CopilotSessionOut(BaseModel):
    tenant_id: uuid.UUID
    principal: str
    device_id: uuid.UUID | None
    expires_at: datetime | None


def _require_user(context: RequestContext) -> uuid.UUID:
    if context.principal is not RequestPrincipal.USER:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
    return context.actor_id


@router.post("/devices", response_model=PairingOut, status_code=status.HTTP_201_CREATED)
def create_device(response: Response, context: RequestContext = Depends(_pair)) -> PairingOut:
    user_id = _require_user(context)
    try:
        result = pair_device(user_id, context.tenant_id)
    except DeviceLimitReachedError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="device_limit_reached"
        ) from exc
    except DeviceHistoryFullError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="device_history_full"
        ) from exc
    # The raw key is in this response only; no cache may keep it.
    response.headers["Cache-Control"] = "no-store"
    return PairingOut(
        device_id=result.device_id, api_key=result.api_key, expires_at=result.expires_at
    )


@router.get("/devices", response_model=list[DeviceOut])
def read_devices(context: RequestContext = Depends(_pair)) -> list[DeviceOut]:
    _require_user(context)
    return [
        DeviceOut(
            id=d.id, status=d.status, created_at=d.created_at, key_expires_at=d.key_expires_at
        )
        for d in list_devices(context.tenant_id)
    ]


@router.delete("/devices/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_device(device_id: uuid.UUID, context: RequestContext = Depends(_pair)) -> Response:
    user_id = _require_user(context)
    try:
        revoke_device(user_id, context.tenant_id, device_id)
    except DeviceNotFoundError as exc:
        raise not_found("device") from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/session", response_model=CopilotSessionOut)
def read_copilot_session(context: RequestContext = Depends(_use)) -> CopilotSessionOut:
    expires_at = None
    device_id = None
    if context.principal is RequestPrincipal.SERVICE_ACCOUNT and context.api_key_id is not None:
        device_id = context.actor_id
        expires_at = get_api_key(context.tenant_id, context.api_key_id).expires_at
    return CopilotSessionOut(
        tenant_id=context.tenant_id,
        principal=context.principal.value,
        device_id=device_id,
        expires_at=expires_at,
    )
