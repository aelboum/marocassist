"""Integration tests against a real PostgreSQL 16 and Redis 7.

    docker compose up -d db redis && docker compose run --rm migrate
    uv run pytest -m integration

Users are created through SaaS-OS's own identity service (as the OIDC
callback does) and authenticated with real SaaS-OS sessions
(`issue_session`), sent as `Authorization: Bearer`. No identity provider is
contacted.
"""

from __future__ import annotations

import threading
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def app() -> FastAPI:
    from marocassist.migrate import migrate

    migrate()  # idempotent: the second run in a session is a no-op
    from marocassist.app import create_app

    return create_app()


@pytest.fixture(scope="module")
def client(app: FastAPI) -> Iterator[TestClient]:
    # `with` runs the lifespan: SaaS-OS's startup checks (route policies,
    # application role cannot bypass RLS) must pass for the app to serve.
    with TestClient(app) as test_client:
        yield test_client


def _new_user() -> tuple[uuid.UUID, dict[str, str]]:
    from saas_os.core.identity import get_or_create_user_for_external_identity
    from saas_os.core.identity.sessions import issue_session

    user = get_or_create_user_for_external_identity(
        "http://zitadel.localhost:8081", f"test-{uuid.uuid4().hex}"
    )
    _session, token = issue_session(user.id)
    return user.id, {"Authorization": f"Bearer {token}"}


def _workspace(client: TestClient, headers: dict[str, str]) -> str:
    response = client.post("/v1/me/workspace", headers=headers)
    assert response.status_code == 200, response.text
    return str(response.json()["tenant_id"])


# --- Startup, health, migrations --------------------------------------------------


def test_health_and_readiness(client: TestClient) -> None:
    assert client.get("/healthz").status_code == 200
    ready = client.get("/readyz")
    assert ready.status_code == 200, ready.text


def test_migrations_are_idempotent() -> None:
    from marocassist.migrate import migrate

    migrate()
    migrate()


def test_application_role_cannot_bypass_rls() -> None:
    from saas_os.infra.db import get_engine, validate_application_role

    validate_application_role(get_engine())  # raises UnsafeDatabaseRoleError otherwise


# --- Personal workspace provisioning -----------------------------------------------


def test_first_request_provisions_exactly_one_personal_workspace(client: TestClient) -> None:
    _user, headers = _new_user()
    assert client.get("/v1/me/workspace", headers=headers).status_code == 404
    first = client.post("/v1/me/workspace", headers=headers).json()
    second = client.post("/v1/me/workspace", headers=headers).json()
    assert first["created"] is True
    assert second["created"] is False
    assert first["tenant_id"] == second["tenant_id"]
    assert client.get("/v1/me/workspace", headers=headers).json()["tenant_id"] == first["tenant_id"]


def test_concurrent_provisioning_creates_one_tenant() -> None:
    from marocassist.accounts.provisioning import ensure_personal_workspace

    user_id, _headers = _new_user()
    results: list[uuid.UUID] = []
    errors: list[BaseException] = []

    def worker() -> None:
        try:
            results.append(ensure_personal_workspace(user_id)[0])
        except BaseException as exc:  # noqa: BLE001 -- collected and asserted below
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(5)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == []
    assert len(set(results)) == 1


def test_owner_role_is_assigned(client: TestClient) -> None:
    from saas_os.core.rbac import can

    user_id, headers = _new_user()
    tenant_id = uuid.UUID(_workspace(client, headers))
    assert can(
        actor_id=user_id, tenant_id=tenant_id, action="read", resource="marocassist.workspace"
    )
    assert can(actor_id=user_id, tenant_id=tenant_id, action="pair", resource="marocassist.copilot")


# --- Tenant isolation: user A never reads user B ---------------------------------------


def test_user_a_cannot_read_or_write_user_b_workspace(client: TestClient) -> None:
    _a, headers_a = _new_user()
    _b, headers_b = _new_user()
    tenant_a = _workspace(client, headers_a)
    tenant_b = _workspace(client, headers_b)
    assert tenant_a != tenant_b

    put = client.put(
        f"/v1/tenants/{tenant_b}/workspace/settings", json={"locale": "fr"}, headers=headers_b
    )
    assert put.status_code == 200
    assert put.json() == {"locale": "fr"}

    # A on B's tenant: the same 404 as a tenant that does not exist.
    read = client.get(f"/v1/tenants/{tenant_b}/workspace/settings", headers=headers_a)
    write = client.put(
        f"/v1/tenants/{tenant_b}/workspace/settings", json={"locale": "ar"}, headers=headers_a
    )
    missing = client.get(f"/v1/tenants/{uuid.uuid4()}/workspace/settings", headers=headers_a)
    assert read.status_code == 404
    assert write.status_code == 404
    assert missing.status_code == 404
    assert read.json() == missing.json()

    # B's value is unchanged and A still sees its own default.
    assert client.get(f"/v1/tenants/{tenant_b}/workspace/settings", headers=headers_b).json() == {
        "locale": "fr"
    }
    assert client.get(f"/v1/tenants/{tenant_a}/workspace/settings", headers=headers_a).json() == {
        "locale": "nl"
    }
    # A cannot pair a device in B's tenant.
    assert (
        client.post(f"/v1/tenants/{tenant_b}/copilot/devices", headers=headers_a).status_code == 404
    )


def test_rls_hides_other_tenants_rows_without_a_predicate(client: TestClient) -> None:
    from saas_os.infra.db import select, tenant_session_scope

    from marocassist.accounts.models import WorkspaceSettings

    _a, headers_a = _new_user()
    _b, headers_b = _new_user()
    tenant_a = uuid.UUID(_workspace(client, headers_a))
    tenant_b = uuid.UUID(_workspace(client, headers_b))
    client.put(
        f"/v1/tenants/{tenant_a}/workspace/settings", json={"locale": "en"}, headers=headers_a
    )
    client.put(
        f"/v1/tenants/{tenant_b}/workspace/settings", json={"locale": "ar"}, headers=headers_b
    )

    # Deliberately no tenant predicate: Row-Level Security alone decides.
    with tenant_session_scope(tenant_a) as session:
        seen = set(session.execute(select(WorkspaceSettings.tenant_id)).scalars().all())
    assert seen == {tenant_a}


def test_invalid_locale_is_rejected(client: TestClient) -> None:
    _a, headers = _new_user()
    tenant = _workspace(client, headers)
    response = client.put(
        f"/v1/tenants/{tenant}/workspace/settings", json={"locale": "xx"}, headers=headers
    )
    assert response.status_code == 422
    assert "xx" not in response.text


def test_purge_participant_removes_only_the_purged_tenant(client: TestClient) -> None:
    from saas_os.infra.db import select, session_scope, tenant_session_scope

    from marocassist.accounts.models import PersonalWorkspace, WorkspaceSettings
    from marocassist.purge import ACCOUNTS_PURGE_PARTICIPANT

    _a, headers_a = _new_user()
    _b, headers_b = _new_user()
    tenant_a = uuid.UUID(_workspace(client, headers_a))
    tenant_b = uuid.UUID(_workspace(client, headers_b))
    client.put(
        f"/v1/tenants/{tenant_a}/workspace/settings", json={"locale": "en"}, headers=headers_a
    )
    client.put(
        f"/v1/tenants/{tenant_b}/workspace/settings", json={"locale": "fr"}, headers=headers_b
    )

    ACCOUNTS_PURGE_PARTICIPANT.purge_tenant_data(tenant_a)
    ACCOUNTS_PURGE_PARTICIPANT.purge_tenant_data(tenant_a)  # idempotent

    with tenant_session_scope(tenant_a) as session:
        assert session.execute(select(WorkspaceSettings.tenant_id)).scalars().all() == []
    with tenant_session_scope(tenant_b) as session:
        assert session.execute(select(WorkspaceSettings.tenant_id)).scalars().all() == [tenant_b]
    with session_scope() as session:
        mapped = set(session.execute(select(PersonalWorkspace.tenant_id)).scalars().all())
    assert tenant_a not in mapped
    assert tenant_b in mapped


# --- Cookie mutation from a foreign origin (ADR-0044) -------------------------------------


def test_cookie_mutation_from_extension_origin_is_refused(client: TestClient) -> None:
    from saas_os.core.identity import get_or_create_user_for_external_identity
    from saas_os.core.identity.sessions import issue_session

    user = get_or_create_user_for_external_identity(
        "http://zitadel.localhost:8081", f"test-{uuid.uuid4().hex}"
    )
    _session, token = issue_session(user.id)
    response = client.post(
        "/v1/me/workspace",
        cookies={"marocassist_session": token},
        headers={"Origin": "chrome-extension://abcdefghijklmnopabcdefghijklmnop"},
    )
    assert response.status_code == 403
    client.cookies.clear()


# --- Copilot device pairing (work package E) --------------------------------------------


@pytest.fixture
def paired(client: TestClient) -> tuple[str, dict[str, str], dict[str, object]]:
    _user, headers = _new_user()
    tenant = _workspace(client, headers)
    response = client.post(f"/v1/tenants/{tenant}/copilot/devices", headers=headers)
    assert response.status_code == 201, response.text
    assert response.headers["cache-control"] == "no-store"
    return tenant, headers, response.json()


def test_paired_key_is_short_lived_and_reaches_only_the_copilot_route(
    client: TestClient, paired: tuple[str, dict[str, str], dict[str, object]]
) -> None:
    tenant, _headers, pairing = paired
    key = {"X-API-Key": str(pairing["api_key"])}
    assert str(pairing["api_key"]).startswith("sok_")

    expires_at = datetime.fromisoformat(str(pairing["expires_at"]))
    remaining = expires_at - datetime.now(UTC)
    assert timedelta(minutes=55) < remaining <= timedelta(hours=1)  # TTL 3600 s in tests

    session = client.get(f"/v1/tenants/{tenant}/copilot/session", headers=key)
    assert session.status_code == 200, session.text
    body = session.json()
    assert body["principal"] == "service_account"
    assert body["device_id"] == pairing["device_id"]
    assert body["tenant_id"] == tenant

    # Every other product route refuses the device key.
    for method, path in [
        ("GET", f"/v1/tenants/{tenant}/workspace/settings"),
        ("PUT", f"/v1/tenants/{tenant}/workspace/settings"),
        ("GET", f"/v1/tenants/{tenant}/copilot/devices"),
        ("POST", f"/v1/tenants/{tenant}/copilot/devices"),
        ("GET", "/v1/me/workspace"),
        ("POST", "/v1/me/workspace"),
    ]:
        response = client.request(method, path, headers=key, json={"locale": "fr"})
        assert response.status_code in (401, 403), (method, path, response.status_code)


def test_device_key_is_bound_to_its_tenant(
    client: TestClient, paired: tuple[str, dict[str, str], dict[str, object]]
) -> None:
    _tenant, _headers, pairing = paired
    _other, other_headers = _new_user()
    other_tenant = _workspace(client, other_headers)
    response = client.get(
        f"/v1/tenants/{other_tenant}/copilot/session",
        headers={"X-API-Key": str(pairing["api_key"])},
    )
    assert response.status_code in (401, 404)


def test_revoked_device_key_stops_working_immediately(
    client: TestClient, paired: tuple[str, dict[str, str], dict[str, object]]
) -> None:
    tenant, headers, pairing = paired
    key = {"X-API-Key": str(pairing["api_key"])}
    assert client.get(f"/v1/tenants/{tenant}/copilot/session", headers=key).status_code == 200

    revoke = client.delete(
        f"/v1/tenants/{tenant}/copilot/devices/{pairing['device_id']}", headers=headers
    )
    assert revoke.status_code == 204
    assert client.get(f"/v1/tenants/{tenant}/copilot/session", headers=key).status_code == 401

    devices = client.get(f"/v1/tenants/{tenant}/copilot/devices", headers=headers).json()
    assert [d["status"] for d in devices if d["id"] == pairing["device_id"]] == ["disabled"]
    # Revoking again is harmless; an unknown device is 404.
    again = client.delete(
        f"/v1/tenants/{tenant}/copilot/devices/{pairing['device_id']}", headers=headers
    )
    assert again.status_code == 204
    unknown = client.delete(f"/v1/tenants/{tenant}/copilot/devices/{uuid.uuid4()}", headers=headers)
    assert unknown.status_code == 404


def test_expired_device_key_is_refused(client: TestClient) -> None:
    from saas_os.core.api_keys import create_service_account_api_key
    from saas_os.core.authority import UserCaller

    user_id, headers = _new_user()
    tenant = _workspace(client, headers)
    pairing = client.post(f"/v1/tenants/{tenant}/copilot/devices", headers=headers).json()
    _key, raw = create_service_account_api_key(
        caller=UserCaller(user_id),
        tenant_id=uuid.UUID(tenant),
        service_account_id=uuid.UUID(pairing["device_id"]),
        name="copilot",
        expires_at=datetime.now(UTC) - timedelta(seconds=1),
    )
    response = client.get(f"/v1/tenants/{tenant}/copilot/session", headers={"X-API-Key": raw})
    assert response.status_code == 401


def test_device_limit_is_enforced(client: TestClient) -> None:
    _user, headers = _new_user()
    tenant = _workspace(client, headers)
    statuses = [
        client.post(f"/v1/tenants/{tenant}/copilot/devices", headers=headers).status_code
        for _ in range(3)
    ]
    assert statuses == [201, 201, 409]  # MAROCASSIST_COPILOT_MAX_DEVICES=2 in tests


def test_pairing_and_revocation_are_audited(
    client: TestClient, paired: tuple[str, dict[str, str], dict[str, object]]
) -> None:
    from saas_os.core import audit_log

    tenant, headers, pairing = paired
    client.delete(f"/v1/tenants/{tenant}/copilot/devices/{pairing['device_id']}", headers=headers)
    actions = {entry.action for entry in audit_log.list(uuid.UUID(tenant))}
    assert {"service_account.create", "api_key.create"} <= actions
    assert "service_account.disable" in actions


def test_concurrent_pairing_cannot_exceed_the_device_limit(client: TestClient) -> None:
    from marocassist.copilot.devices import DeviceLimitReachedError, pair_device

    user_id, headers = _new_user()
    tenant = uuid.UUID(_workspace(client, headers))
    outcomes: list[str] = []

    def worker() -> None:
        try:
            pair_device(user_id, tenant)
            outcomes.append("paired")
        except DeviceLimitReachedError:
            outcomes.append("limit")

    threads = [threading.Thread(target=worker) for _ in range(5)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert outcomes.count("paired") == 2  # MAROCASSIST_COPILOT_MAX_DEVICES=2 in tests
    assert outcomes.count("limit") == 3
