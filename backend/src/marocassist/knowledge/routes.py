"""HTTP routes of the knowledge module (Phase 3 WP D; search architecture
section 7).

Every route is tenant-scoped (`/v1/tenants/{tenant_id}/knowledge/...`)
although the knowledge is global: SaaS-OS `require_permission` then does
authentication, tenant resolution (member or the same 404), the per-tenant
rate limit and RBAC, so no parallel tenant-less authorisation path exists.
No route accepts API keys yet; the Copilot extension gets knowledge access
in Phase 4, if at all.

- Reads need `marocassist.knowledge:read` and write nothing.
- `POST /reports` needs `marocassist.knowledge:report` and a user session.

Privacy (security review section 4): search queries are neither stored nor
logged. This module never logs a query, and the response does not echo the
query text back.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response, status
from pydantic import BaseModel, ConfigDict, Field
from saas_os.api.context import RequestContext, RequestPrincipal
from saas_os.api.dependencies import require_permission
from saas_os.api.errors import not_found, service_unavailable

from marocassist.knowledge import catalogue, reports
from marocassist.knowledge.fts import SearchTimeout
from marocassist.permissions import KNOWLEDGE, READ, REPORT

router = APIRouter(prefix="/v1/tenants/{tenant_id}/knowledge", tags=["knowledge"])

_read = require_permission(KNOWLEDGE, READ)
_report = require_permission(KNOWLEDGE, REPORT)

Lang = Literal["nl", "fr", "ar", "en"]
Kind = Literal["procedure", "explanation", "faq"]
ITEM_ID = r"^[a-z0-9][a-z0-9.-]{1,79}$"
CONSULATE = r"^[a-z0-9-]{2,32}$"
FACT_KEY = r"^[a-z0-9_]+(\.[a-z0-9_]+)+$"
# The pipeline keeps the first 256 characters; longer input is refused
# rather than silently cut far from what the user typed.
MAX_QUERY_CHARS = 1000
RETRY_AFTER_SECONDS = 2

ConsulateParam = Annotated[str | None, Query(pattern=CONSULATE)]


class ReportIn(BaseModel):
    # Free text is deliberately not accepted (it could hold personal data).
    model_config = ConfigDict(extra="forbid")

    item_id: str = Field(pattern=ITEM_ID)
    reason_code: reports.ReasonCode


class ReportOut(BaseModel):
    report_id: uuid.UUID
    created_at: datetime


def _timeout() -> HTTPException:
    return service_unavailable(RETRY_AFTER_SECONDS)


@router.get("/search", response_model=catalogue.SearchOut)
def search(
    q: Annotated[str, Query(max_length=MAX_QUERY_CHARS)],
    lang: Lang = "nl",
    consulate: ConsulateParam = None,
    kind: Annotated[list[Kind] | None, Query()] = None,
    _context: RequestContext = Depends(_read),
) -> catalogue.SearchOut:
    try:
        return catalogue.search(q, lang=lang, consulate=consulate, kinds=kind)
    except SearchTimeout:
        raise _timeout() from None


@router.get("/items/{item_id}", response_model=catalogue.ItemOut)
def read_item(
    item_id: Annotated[str, Path(pattern=ITEM_ID)],
    lang: Lang | None = None,
    _context: RequestContext = Depends(_read),
) -> catalogue.ItemOut:
    try:
        return catalogue.get_item(item_id, lang=lang)
    except catalogue.ItemNotFoundError:
        raise not_found("item") from None
    except SearchTimeout:
        raise _timeout() from None


@router.get("/facts/{fact_key}", response_model=catalogue.FactOut)
def read_fact(
    fact_key: Annotated[str, Path(pattern=FACT_KEY, max_length=120)],
    consulate: ConsulateParam = None,
    _context: RequestContext = Depends(_read),
) -> catalogue.FactOut:
    try:
        fact = catalogue.get_fact(fact_key, consulate=consulate)
    except SearchTimeout:
        raise _timeout() from None
    if fact is None:
        raise not_found("fact")
    return fact


@router.get("/consulates", response_model=list[catalogue.ConsulateOut])
def read_consulates(
    lang: Lang | None = None,
    _context: RequestContext = Depends(_read),
) -> list[catalogue.ConsulateOut]:
    try:
        return catalogue.list_consulates(lang=lang)
    except SearchTimeout:
        raise _timeout() from None


@router.get("/consulates/{code}", response_model=catalogue.ConsulateOut)
def read_consulate(
    code: Annotated[str, Path(pattern=CONSULATE)],
    lang: Lang | None = None,
    _context: RequestContext = Depends(_read),
) -> catalogue.ConsulateOut:
    try:
        consulate = catalogue.get_consulate(code, lang=lang)
    except SearchTimeout:
        raise _timeout() from None
    if consulate is None:
        raise not_found("consulate")
    return consulate


@router.post("/reports", response_model=ReportOut, status_code=status.HTTP_201_CREATED)
def create_report(
    body: ReportIn,
    response: Response,
    context: RequestContext = Depends(_report),
) -> ReportOut:
    if context.principal is not RequestPrincipal.USER:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
    try:
        reportable = catalogue.item_is_reportable(body.item_id)
    except SearchTimeout:
        raise _timeout() from None
    if not reportable:
        raise not_found("item")
    result = reports.create_report(context.tenant_id, body.item_id, body.reason_code)
    if not result.created:
        response.status_code = status.HTTP_200_OK
    return ReportOut(report_id=result.report_id, created_at=result.created_at)
