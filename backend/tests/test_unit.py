"""Unit tests: no database, no Redis. The app is built but its lifespan
(which checks the database role) is not run."""

from __future__ import annotations

import ast
import re
import tomllib
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

BACKEND = Path(__file__).resolve().parents[1]
SRC = BACKEND / "src" / "marocassist"
PIN = "cdede956dd884fc816b234f1b546ce3b983b4efc"


# --- SaaS-OS pin -------------------------------------------------------------


def test_saas_os_is_pinned_to_the_exact_release_commit() -> None:
    project = tomllib.loads((BACKEND / "pyproject.toml").read_text(encoding="utf-8"))
    deps = [d for d in project["project"]["dependencies"] if d.startswith("saas-os")]
    assert deps == [f"saas-os @ git+https://github.com/aelboum/saas-os@{PIN}"]
    assert re.fullmatch(r"[0-9a-f]{40}", deps[0].rsplit("@", 1)[1])


def test_lockfile_resolves_saas_os_to_the_same_commit() -> None:
    lock = (BACKEND / "uv.lock").read_text(encoding="utf-8")
    assert f"saas-os?rev={PIN}#{PIN}" in lock


def test_installed_saas_os_is_v0_15_0() -> None:
    from importlib.metadata import version

    assert version("saas-os") == "0.15.0"


# --- Architecture --------------------------------------------------------------


def _imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
    return names


def test_no_module_imports_the_saas_os_control_plane() -> None:
    offenders = [
        str(p.relative_to(SRC))
        for p in SRC.rglob("*.py")
        if any(n.startswith("saas_os.control_plane") for n in _imports(p))
    ]
    assert offenders == []


def test_only_migrations_import_sqlalchemy_or_psycopg() -> None:
    offenders = [
        str(p.relative_to(SRC))
        for p in SRC.rglob("*.py")
        if "migrations" not in p.parts
        and any(n.split(".")[0] in {"sqlalchemy", "psycopg"} for n in _imports(p))
    ]
    assert offenders == []


def test_no_raw_sql_helpers_in_product_code() -> None:
    forbidden = re.compile(r"\b(text|literal_column|exec_driver_sql|TextClause)\s*\(")
    offenders = [
        str(p.relative_to(SRC))
        for p in SRC.rglob("*.py")
        if "migrations" not in p.parts and forbidden.search(p.read_text(encoding="utf-8"))
    ]
    assert offenders == []


@pytest.fixture(scope="module")
def app() -> FastAPI:
    from marocassist.app import create_app

    return create_app()


def test_every_route_declares_a_saas_os_route_policy(app: FastAPI) -> None:
    from saas_os.api.route_policy import assert_route_policies

    policies = assert_route_policies(app, production=False)
    assert any("/v1/meta" in label for label in policies)


def test_product_routes_are_versioned(app: FastAPI) -> None:
    # FastAPI nests included routers; the OpenAPI document lists every path.
    platform = {"/healthz", "/readyz"}
    paths = list(app.openapi()["paths"])
    unversioned = [p for p in paths if not (p.startswith(("/v1/", "/auth/")) or p in platform)]
    assert "/v1/me/workspace" in paths
    assert unversioned == []


def test_only_the_copilot_session_route_accepts_api_keys(app: FastAPI) -> None:
    opt_in = re.compile(r"require_permission\([^)]*api_key=True")
    source = (SRC / "copilot" / "routes.py").read_text(encoding="utf-8")
    assert len(opt_in.findall(source)) == 1
    for other in ("accounts/routes.py", "privacy/routes.py"):
        assert "api_key=True" not in (SRC / other).read_text(encoding="utf-8")


# --- HTTP behaviour without services ---------------------------------------------


def test_meta_is_public_and_returns_constants_only(app: FastAPI) -> None:
    response = TestClient(app).get("/v1/meta")
    assert response.status_code == 200
    assert response.json() == {"product": "marocassist", "version": "0.1.0", "api_version": "v1"}
    assert response.headers.get("x-request-id")


def test_request_id_is_propagated(app: FastAPI) -> None:
    response = TestClient(app).get("/v1/meta", headers={"X-Request-ID": "test-correlation-1"})
    assert response.headers["x-request-id"] == "test-correlation-1"


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/v1/me/workspace"),
        ("POST", "/v1/me/workspace"),
    ],
)
def test_authenticated_routes_refuse_missing_credentials(
    app: FastAPI, method: str, path: str
) -> None:
    response = TestClient(app).request(method, path)
    assert response.status_code == 401


_PUBLIC_PATHS = {"/healthz", "/readyz", "/v1/meta", "/auth/login", "/auth/callback"}


def test_every_product_route_refuses_missing_credentials(app: FastAPI) -> None:
    """401 matrix, generated from the OpenAPI document so a new route is
    covered without editing this test."""
    import uuid

    client = TestClient(app)
    checked = 0
    for path, operations in app.openapi()["paths"].items():
        if path in _PUBLIC_PATHS or not path.startswith("/v1/"):
            continue
        concrete = path.replace("{tenant_id}", str(uuid.uuid4()))
        concrete = concrete.replace("{device_id}", str(uuid.uuid4()))
        concrete = concrete.replace("{purpose}", "product_emails")
        for method in operations:
            response = client.request(method.upper(), concrete, json={})
            assert response.status_code == 401, (method, path, response.status_code)
            checked += 1
    assert checked >= 17


def _handler_app() -> FastAPI:
    from marocassist.errors import install_exception_handlers

    probe = FastAPI()
    install_exception_handlers(probe)

    class Body(BaseModel):
        locale: int

    @probe.post("/probe")
    def _probe(body: Body) -> dict[str, int]:
        return {"locale": body.locale}

    @probe.get("/refused")
    def _refused() -> None:
        from saas_os.core.rbac import AuthorityNotAuthorizedError

        raise AuthorityNotAuthorizedError("probe", None)

    @probe.get("/os-permission")
    def _os_permission() -> None:
        raise PermissionError("disk permission denied")

    @probe.get("/boom")
    def _boom() -> None:
        raise RuntimeError("secret-detail-must-not-leak")

    return probe


def test_validation_errors_do_not_echo_input() -> None:
    response = TestClient(_handler_app()).post("/probe", json={"locale": "PERSONAL-DATA-123"})
    assert response.status_code == 422
    assert response.json()["error"] == "invalid_request"
    assert "PERSONAL-DATA-123" not in response.text


def test_core_authority_refusal_is_a_plain_403() -> None:
    client = TestClient(_handler_app(), raise_server_exceptions=False)
    response = client.get("/refused")
    assert response.status_code == 403
    assert response.json()["error"] == "forbidden"


def test_os_permission_error_is_a_500_not_a_403() -> None:
    client = TestClient(_handler_app(), raise_server_exceptions=False)
    response = client.get("/os-permission")
    assert response.status_code == 500
    assert "disk" not in response.text


def test_unhandled_errors_return_a_fixed_body() -> None:
    client = TestClient(_handler_app(), raise_server_exceptions=False)
    response = client.get("/boom")
    assert response.status_code == 500
    assert response.json()["error"] == "internal_error"
    assert "secret-detail" not in response.text


# --- Configuration ---------------------------------------------------------------


def test_copilot_key_ttl_is_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    from marocassist import config

    config.get_settings.cache_clear()
    monkeypatch.setenv("MAROCASSIST_COPILOT_KEY_TTL_SECONDS", "999999")
    with pytest.raises(config.ConfigurationError, match="MAROCASSIST_COPILOT_KEY_TTL_SECONDS"):
        config.get_settings()
    monkeypatch.setenv("MAROCASSIST_COPILOT_KEY_TTL_SECONDS", "abc")
    with pytest.raises(config.ConfigurationError):
        config.get_settings()
    monkeypatch.setenv("MAROCASSIST_COPILOT_KEY_TTL_SECONDS", "600")
    config.get_settings.cache_clear()
    assert config.get_settings().copilot_key_ttl_seconds == 600
    config.get_settings.cache_clear()


def test_copilot_client_role_holds_only_copilot_use() -> None:
    from marocassist.permissions import COPILOT, COPILOT_CLIENT_ROLE, ROLE_PERMISSIONS, USE

    assert ROLE_PERMISSIONS[COPILOT_CLIENT_ROLE] == ((COPILOT, USE),)


def test_owner_role_holds_every_product_permission_but_not_device_use() -> None:
    from marocassist.permissions import (
        COPILOT,
        OWNER_ROLE,
        PRODUCT_PERMISSIONS,
        ROLE_PERMISSIONS,
        USE,
    )

    owner = set(ROLE_PERMISSIONS[OWNER_ROLE])
    assert set(PRODUCT_PERMISSIONS) - owner == set()
    assert (COPILOT, USE) in owner  # the owner may test the session route


def test_phase_2_permissions_reach_existing_tenants_through_a_grant_migration() -> None:
    from saas_os.core.permission_grants import validate_permission_grant_migrations

    from marocassist.permissions import (
        GRANT_NAMESPACE,
        OWNER_ROLE,
        PERMISSION_GRANT_MIGRATIONS,
        PHASE_2_PERMISSIONS,
    )

    validate_permission_grant_migrations(PERMISSION_GRANT_MIGRATIONS, namespace=GRANT_NAMESPACE)
    granted = {
        permission
        for migration in PERMISSION_GRANT_MIGRATIONS
        if migration.role_name == OWNER_ROLE
        for permission in migration.permissions
    }
    assert set(PHASE_2_PERMISSIONS) <= granted


def test_personal_tenant_name_is_stable_and_opaque() -> None:
    import uuid

    from marocassist.accounts.provisioning import personal_tenant_name

    user = uuid.uuid4()
    name = personal_tenant_name(user)
    assert name == personal_tenant_name(user)
    assert name != personal_tenant_name(uuid.uuid4())
    assert str(user) not in name
    assert re.fullmatch(r"personal-[0-9a-f]{32}", name)


def test_phase_2_migration_enables_forced_rls_and_minimal_grants() -> None:
    migration = (SRC / "migrations" / "versions" / "0002_profile_consents.py").read_text(
        encoding="utf-8"
    )
    assert '("profiles", "consents", "deletion_requests")' in migration
    assert "tenant_rls_statements(table" in migration
    assert "GRANT ALL" not in migration.upper()
    assert "INSERT, DELETE ON {_SCHEMA}.deletion_requests" in migration
    assert "UPDATE, DELETE ON {_SCHEMA}.deletion_requests" not in migration


def test_audit_metadata_of_product_actions_holds_no_personal_values() -> None:
    """Profile changes audit field names only, never the new values."""
    source = (SRC / "accounts" / "profile.py").read_text(encoding="utf-8")
    assert 'metadata={"fields": changed}' in source
    assert "display_name" not in source.split("def _audit", 1)[1].split("def ", 1)[0]


def test_migration_enables_forced_rls_on_tenant_tables() -> None:
    migration = (SRC / "migrations" / "versions" / "0001_accounts.py").read_text(encoding="utf-8")
    assert 'tenant_rls_statements("workspace_settings"' in migration
    assert "GRANT ALL" not in migration.upper()
    assert "UPDATE ON {_SCHEMA}.personal_workspaces" not in migration


# --- API contract (packages/contracts/openapi.json) ------------------------------------

CONTRACT = BACKEND.parent / "packages" / "contracts" / "openapi.json"


def _current_contract(app: FastAPI) -> str:
    import json

    return json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n"


def test_openapi_contract_is_up_to_date(app: FastAPI) -> None:
    """The committed contract must match the running app. Regenerate with
    `uv run python -m tests.export_openapi` after an intended API change."""
    assert CONTRACT.read_text(encoding="utf-8") == _current_contract(app)


def test_provisioning_waits_for_a_free_slot_and_then_gives_up(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """S-8: concurrent provisionings are bounded, so they cannot hold every
    pooled connection; a request that finds no slot fails fast (503)."""
    import uuid

    from marocassist.accounts import provisioning

    monkeypatch.setattr(provisioning, "get_personal_tenant_id", lambda _user: None)
    monkeypatch.setattr(provisioning, "_PROVISIONING_WAIT_SECONDS", 0.05)
    held = [
        provisioning._provisioning_slots.acquire(blocking=False)
        for _ in range(provisioning.MAX_CONCURRENT_PROVISIONINGS)
    ]
    assert all(held)
    try:
        with pytest.raises(provisioning.ProvisioningBusyError):
            provisioning.ensure_personal_workspace(uuid.uuid4())
    finally:
        for _ in held:
            provisioning._provisioning_slots.release()
