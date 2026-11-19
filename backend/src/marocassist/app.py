"""MarocAssist application entrypoint.

    uvicorn marocassist.app:app

`build_platform_app()` (SaaS-OS) contributes the fail-closed startup checks
(every route declares a policy; the database role cannot bypass RLS),
`X-Request-ID` correlation, `/healthz`, `/readyz` and the OIDC `/auth/*`
routes. MarocAssist mounts its own routers on top and adds its exception
handlers. API versioning: every product route lives under `/v1`
(SaaS-OS ADR-0006); a breaking change gets `/v2`, never an edit of `/v1`.
"""

from __future__ import annotations

from fastapi import FastAPI
from saas_os.api.platform import build_platform_app
from saas_os.infra.observability import configure_logging

from marocassist import __version__
from marocassist.accounts.routes import router as accounts_router
from marocassist.api.meta import router as meta_router
from marocassist.copilot.routes import router as copilot_router
from marocassist.errors import install_exception_handlers
from marocassist.purge import register_purge_participants


def create_app() -> FastAPI:
    configure_logging()  # SaaS-OS JSON logs with correlation ids and redaction
    app = build_platform_app(title="MarocAssist", version=__version__)
    install_exception_handlers(app)
    app.include_router(meta_router)
    app.include_router(accounts_router)
    app.include_router(copilot_router)
    register_purge_participants()
    return app


app = create_app()
