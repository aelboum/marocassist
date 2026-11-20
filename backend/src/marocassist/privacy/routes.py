"""Account rights, user only (no API key):

- `GET  .../account/export`: a copy of the account's product data as JSON
  (`marocassist.account:export`). Never cached.
- `GET|POST .../account/deletion-request`: record a deletion request
  (`marocassist.account:delete`). Recording it also unpairs every Copilot
  device at once, so no device credential stays usable while the request
  waits for the operator (ADR-0006). The account itself stays usable until
  the operator carries the request out.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from saas_os.api.context import RequestContext, RequestPrincipal
from saas_os.api.dependencies import require_permission

from marocassist.accounts.profile import read_deletion_request, request_deletion
from marocassist.copilot.devices import list_devices, revoke_device
from marocassist.permissions import ACCOUNT, DELETE, EXPORT
from marocassist.privacy.export import build_export

router = APIRouter(prefix="/v1/tenants/{tenant_id}/account", tags=["privacy"])

_export = require_permission(ACCOUNT, EXPORT)
_delete_account = require_permission(ACCOUNT, DELETE)


class DeletionRequestOut(BaseModel):
    requested: bool
    requested_at: datetime | None


def _require_user(context: RequestContext) -> uuid.UUID:
    if context.principal is not RequestPrincipal.USER:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
    return context.actor_id


@router.get("/export", response_model=dict[str, Any])
def export_account(context: RequestContext = Depends(_export)) -> JSONResponse:
    user_id = _require_user(context)
    return JSONResponse(
        content=build_export(user_id, context.tenant_id),
        headers={
            "Cache-Control": "no-store",
            "Content-Disposition": 'attachment; filename="marocassist-export.json"',
        },
    )


@router.get("/deletion-request", response_model=DeletionRequestOut)
def get_deletion_request(
    context: RequestContext = Depends(_delete_account),
) -> DeletionRequestOut:
    requested_at = read_deletion_request(context.tenant_id)
    return DeletionRequestOut(requested=requested_at is not None, requested_at=requested_at)


@router.post("/deletion-request", response_model=DeletionRequestOut)
def post_deletion_request(
    response: Response, context: RequestContext = Depends(_delete_account)
) -> DeletionRequestOut:
    user_id = _require_user(context)
    requested_at, created = request_deletion(user_id, context.tenant_id)
    # Idempotent: also on a repeat, every still-active device is unpaired.
    for device in list_devices(context.tenant_id):
        revoke_device(user_id, context.tenant_id, device.id)
    response.status_code = status.HTTP_202_ACCEPTED if created else status.HTTP_200_OK
    return DeletionRequestOut(requested=True, requested_at=requested_at)
