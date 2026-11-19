"""`GET /v1/meta`: which product and API version is serving.

Public by design: it returns only constants compiled into the build (no
configuration, no environment, no dependency versions), so the web app and
the extension can check compatibility before a user signs in.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from saas_os.api.route_policy import public_route

from marocassist import API_VERSION, __version__

router = APIRouter(prefix="/v1", tags=["meta"])

_public = public_route("product name and API version; constants only, no tenant or user data")


@router.get("/meta")
def meta(_: None = Depends(_public)) -> dict[str, str]:  # noqa: B008
    return {"product": "marocassist", "version": __version__, "api_version": API_VERSION}
