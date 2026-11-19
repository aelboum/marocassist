"""Central exception handling.

SaaS-OS raises `HTTPException`s with fixed, non-enumerating bodies
(`saas_os.api.errors`); those are left to FastAPI's own handler. This
module adds the cases SaaS-OS leaves to the product:

- request validation failures: one stable shape, without echoing the
  submitted values back (they may contain personal data);
- any unhandled exception: `500` with a fixed body and the request id, and
  a log line carrying only the exception *type* (never its message, which
  can contain data), via SaaS-OS's `safe_exception_type`.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from saas_os.infra.observability import get_correlation_context, safe_exception_type

logger = logging.getLogger(__name__)


def _request_id() -> str | None:
    return get_correlation_context().request_id


async def _validation_error(_request: Request, exc: Exception) -> JSONResponse:
    errors = exc.errors() if isinstance(exc, RequestValidationError) else []
    # Field locations and error types only -- never the submitted input.
    fields = [
        {"loc": [str(part) for part in error.get("loc", ())], "type": error.get("type")}
        for error in errors
    ]
    return JSONResponse(
        status_code=422,
        content={"error": "invalid_request", "fields": fields, "request_id": _request_id()},
    )


async def _permission_error(request: Request, exc: Exception) -> JSONResponse:
    # SaaS-OS Core refusals (`AuthorityNotAuthorizedError` and the
    # operation-specific ones) subclass `PermissionError` and never say why
    # (ADR-0031). Answer the same plain refusal. A `PermissionError` raised
    # anywhere else (an OS-level file or socket error) is an infrastructure
    # fault, not an authorization decision: it stays a 500.
    if not type(exc).__module__.startswith("saas_os."):
        return await _unhandled_error(request, exc)
    logger.info("core_authority_refused", extra={"error_type": safe_exception_type(exc)})
    return JSONResponse(
        status_code=403, content={"error": "forbidden", "request_id": _request_id()}
    )


async def _unhandled_error(_request: Request, exc: Exception) -> JSONResponse:
    logger.error("unhandled_exception", extra={"error_type": safe_exception_type(exc)})
    return JSONResponse(
        status_code=500,
        content={"error": "internal_error", "request_id": _request_id()},
    )


def install_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(PermissionError, _permission_error)
    app.add_exception_handler(Exception, _unhandled_error)
