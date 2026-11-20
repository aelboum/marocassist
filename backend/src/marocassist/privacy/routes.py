"""`GET /v1/tenants/{tenant_id}/account/export` -- download a copy of the
account's product data as JSON. Permission `marocassist.account:export`,
user only (no API key). Never cached."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from saas_os.api.context import RequestContext, RequestPrincipal
from saas_os.api.dependencies import require_permission

from marocassist.permissions import ACCOUNT, EXPORT
from marocassist.privacy.export import build_export

router = APIRouter(prefix="/v1/tenants/{tenant_id}/account", tags=["privacy"])

_export = require_permission(ACCOUNT, EXPORT)


@router.get("/export", response_model=dict[str, Any])
def export_account(context: RequestContext = Depends(_export)) -> JSONResponse:
    if context.principal is not RequestPrincipal.USER:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
    return JSONResponse(
        content=build_export(context.actor_id, context.tenant_id),
        headers={
            "Cache-Control": "no-store",
            "Content-Disposition": 'attachment; filename="marocassist-export.json"',
        },
    )
