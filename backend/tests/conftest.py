"""Test configuration.

Unit tests need no service: SaaS-OS only reads `ENVIRONMENT` and
`REDIS_URL` at import time, so harmless local values are set here before
any `saas_os` import.

Integration tests (`-m integration`) need the Compose `db` and `redis`
services (published on 127.0.0.1:5433 and :6380) and read the generated
local credentials from the repository's `.env` (never committed). See
backend/README.md.
"""

from __future__ import annotations

import os
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _local_env() -> dict[str, str]:
    env_file = _REPO_ROOT / ".env"
    values: dict[str, str] = {}
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                key, _, value = line.partition("=")
                values[key.strip()] = value.strip()
    return values


def _configure_environment() -> None:
    local = _local_env()
    db_port = os.environ.get("TEST_DB_PORT", "5433")
    redis_port = os.environ.get("TEST_REDIS_PORT", "6380")
    db = local.get("POSTGRES_DB", "marocassist")
    app_user = local.get("APP_DB_USER", "marocassist_app")
    owner = local.get("POSTGRES_USER", "marocassist")
    defaults = {
        "ENVIRONMENT": "test",
        "REDIS_URL": f"redis://127.0.0.1:{redis_port}/0",
        "APP_DB_USER": app_user,
        "DATABASE_URL": (
            f"postgresql+psycopg://{app_user}:{local.get('APP_DB_PASSWORD', '')}"
            f"@127.0.0.1:{db_port}/{db}"
        ),
        "MIGRATIONS_DATABASE_URL": (
            f"postgresql+psycopg://{owner}:{local.get('POSTGRES_PASSWORD', '')}"
            f"@127.0.0.1:{db_port}/{db}"
        ),
        "PUBLIC_APP_ORIGIN": "http://localhost:8080",
        "OIDC_ISSUER_URL": "http://zitadel.localhost:8081",
        "OIDC_CLIENT_ID": "test-client",
        "AUTH_COOKIE_NAME": "marocassist_session",
        "AUTH_COOKIE_SECURE": "false",
        "MAROCASSIST_COPILOT_KEY_TTL_SECONDS": "3600",
        "MAROCASSIST_COPILOT_MAX_DEVICES": "2",
    }
    for key, value in defaults.items():
        os.environ.setdefault(key, value)


_configure_environment()
