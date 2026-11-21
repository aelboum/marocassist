"""Phase 2 integration tests: onboarding, profile, consents, account rights,
resumable provisioning and the 401/403/404 matrix. Real PostgreSQL 16 and
Redis 7, real SaaS-OS sessions (see test_integration.py).
"""

from __future__ import annotations

import threading
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from test_integration import _new_user, _workspace

pytestmark = pytest.mark.integration

NOTICE = "2026-11-draft"


@pytest.fixture(scope="module")
def app() -> FastAPI:
    from marocassist.migrate import migrate

    migrate()
    from marocassist.app import create_app

    return create_app()


@pytest.fixture(scope="module")
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


def _onboarding(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "display_name": "Canary Person",
        "consulate": "nl-rotterdam",
        "locale": "fr",
        "age_confirmed": True,
        "privacy_notice_version": NOTICE,
        "product_emails": False,
    }
    body.update(overrides)
    return body


def _onboarded_user(client: TestClient) -> tuple[uuid.UUID, str, dict[str, str]]:
    user_id, headers = _new_user()
    tenant = _workspace(client, headers)
    response = client.post(f"/v1/tenants/{tenant}/onboarding", json=_onboarding(), headers=headers)
    assert response.status_code == 201, response.text
    return user_id, tenant, headers


def _actions(tenant: str) -> list[str]:
    from saas_os.core import audit_log

    return [entry.action for entry in audit_log.list(uuid.UUID(tenant))]


def _consents(client: TestClient, tenant: str, headers: dict[str, str]) -> dict[str, Any]:
    rows = client.get(f"/v1/tenants/{tenant}/consents", headers=headers).json()
    return {row["purpose"]: row for row in rows}


# --- Verified email and provisioning ---------------------------------------------------


def test_unverified_email_cannot_create_a_workspace(client: TestClient) -> None:
    _user, headers = _new_user(verified=False)
    response = client.post("/v1/me/workspace", headers=headers)
    assert response.status_code == 403
    assert response.json()["detail"] == "email_not_verified"
    assert client.get("/v1/me/workspace", headers=headers).status_code == 404


def test_half_provisioned_tenant_is_resumed_not_duplicated(client: TestClient) -> None:
    """S-8: a crash after Core created the tenant (and one role) but before
    the mapping committed. The next request finishes that tenant."""
    from saas_os.core.authority import SystemAuthority, SystemCaller
    from saas_os.core.rbac import can, create_role
    from saas_os.core.tenancy import create_tenant, find_tenants_by_name

    from marocassist.accounts.provisioning import personal_tenant_name

    user_id, headers = _new_user()
    caller = SystemCaller(SystemAuthority.PROVISIONING)
    orphan = create_tenant(personal_tenant_name(user_id), caller=caller)  # still PENDING
    create_role(orphan.id, "owner", caller=caller)

    body = client.post("/v1/me/workspace", headers=headers).json()
    assert body == {"tenant_id": str(orphan.id), "created": True}
    assert len(find_tenants_by_name(personal_tenant_name(user_id))) == 1
    assert can(actor_id=user_id, tenant_id=orphan.id, action="read", resource="marocassist.profile")


# --- Onboarding ----------------------------------------------------------------------------


def test_onboarding_creates_profile_and_consents_once(client: TestClient) -> None:
    _user, headers = _new_user()
    tenant = _workspace(client, headers)
    status = client.get(f"/v1/tenants/{tenant}/onboarding", headers=headers).json()
    assert status["onboarded"] is False
    assert status["privacy_notice_version"] == NOTICE
    assert "nl-utrecht" in status["consulates"]
    assert client.get(f"/v1/tenants/{tenant}/profile", headers=headers).status_code == 409

    first = client.post(f"/v1/tenants/{tenant}/onboarding", json=_onboarding(), headers=headers)
    second = client.post(f"/v1/tenants/{tenant}/onboarding", json=_onboarding(), headers=headers)
    assert (first.status_code, second.status_code) == (201, 200)
    assert second.json() == {"onboarded": True, "created": False}

    status = client.get(f"/v1/tenants/{tenant}/onboarding", headers=headers).json()
    assert status["onboarded"] is True
    assert status["privacy_notice_current"] is True
    profile = client.get(f"/v1/tenants/{tenant}/profile", headers=headers).json()
    assert profile["consulate"] == "nl-rotterdam"
    assert profile["residence_country"] == "NL"
    settings = client.get(f"/v1/tenants/{tenant}/workspace/settings", headers=headers).json()
    assert settings == {"locale": "fr"}
    consents = _consents(client, tenant, headers)
    assert consents["privacy_notice"]["granted"] is True
    assert consents["product_emails"]["granted"] is False
    actions = _actions(tenant)
    assert actions.count("marocassist.account.onboard") == 1
    assert actions.count("marocassist.consent.grant") == 1
    assert actions.count("marocassist.consent.withdraw") == 1


def test_concurrent_onboarding_records_exactly_once() -> None:
    from marocassist.accounts.profile import complete_onboarding
    from marocassist.accounts.provisioning import ensure_personal_workspace

    user_id, _headers = _new_user()
    tenant_id, _ = ensure_personal_workspace(user_id)
    outcomes: list[bool] = []
    errors: list[BaseException] = []

    def worker() -> None:
        try:
            outcomes.append(
                complete_onboarding(
                    user_id,
                    tenant_id,
                    display_name=None,
                    consulate=None,
                    locale="nl",
                    age_confirmed=True,
                    privacy_notice_version=NOTICE,
                    product_emails=True,
                )
            )
        except BaseException as exc:  # noqa: BLE001 -- asserted below
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(5)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == []
    assert sorted(outcomes) == [False, False, False, False, True]
    assert _actions(str(tenant_id)).count("marocassist.account.onboard") == 1


@pytest.mark.parametrize(
    "override",
    [
        {"age_confirmed": False},
        {"privacy_notice_version": "2020-01"},
        {"consulate": "ma-rabat"},
        {"locale": "de"},
    ],
)
def test_onboarding_refuses_invalid_input(client: TestClient, override: dict[str, Any]) -> None:
    _user, headers = _new_user()
    tenant = _workspace(client, headers)
    response = client.post(
        f"/v1/tenants/{tenant}/onboarding", json=_onboarding(**override), headers=headers
    )
    assert response.status_code == 422
    assert "Canary" not in response.text
    status = client.get(f"/v1/tenants/{tenant}/onboarding", headers=headers).json()
    assert status["onboarded"] is False


# --- Profile ----------------------------------------------------------------------------------


def test_profile_update_audits_field_names_only(client: TestClient) -> None:
    from saas_os.core import audit_log

    _user, tenant, headers = _onboarded_user(client)
    response = client.put(
        f"/v1/tenants/{tenant}/profile",
        json={"display_name": "  Another   Canary ", "consulate": "nl-amsterdam"},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["display_name"] == "Another Canary"
    updates = [
        entry
        for entry in audit_log.list(uuid.UUID(tenant))
        if entry.action == "marocassist.profile.update"
    ]
    assert len(updates) == 1
    assert sorted((updates[0].entry_metadata or {})["fields"]) == ["consulate", "display_name"]
    assert "Canary" not in str(updates[0].entry_metadata)

    invalid = client.put(
        f"/v1/tenants/{tenant}/profile", json={"consulate": "xx-unknown"}, headers=headers
    )
    assert invalid.status_code == 422


# --- Consents ---------------------------------------------------------------------------------


def test_consent_change_writes_its_audit_row_in_the_same_transaction(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If the audit row cannot be written, the consent change is rolled back."""
    import marocassist.accounts.profile as profile_module

    _user, tenant, headers = _onboarded_user(client)
    url = f"/v1/tenants/{tenant}/consents/product_emails"

    def failing_audit(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("audit store unavailable")

    monkeypatch.setattr(profile_module, "record_in_transaction", failing_audit)
    failed = client.put(url, json={"granted": True, "version": NOTICE}, headers=headers)
    assert failed.status_code == 500
    monkeypatch.undo()

    assert _consents(client, tenant, headers)["product_emails"]["granted"] is False

    ok = client.put(url, json={"granted": True, "version": NOTICE}, headers=headers)
    assert ok.status_code == 200
    assert _actions(tenant).count("marocassist.consent.grant") == 2  # notice + emails
    same = client.put(url, json={"granted": True, "version": NOTICE}, headers=headers)
    assert same.status_code == 200
    assert _actions(tenant).count("marocassist.consent.grant") == 2  # a no-op is not audited


def test_required_consent_cannot_be_withdrawn_and_versions_must_be_current(
    client: TestClient,
) -> None:
    _user, tenant, headers = _onboarded_user(client)
    withdraw = client.put(
        f"/v1/tenants/{tenant}/consents/privacy_notice",
        json={"granted": False, "version": NOTICE},
        headers=headers,
    )
    stale = client.put(
        f"/v1/tenants/{tenant}/consents/product_emails",
        json={"granted": True, "version": "2020-01"},
        headers=headers,
    )
    unknown = client.put(
        f"/v1/tenants/{tenant}/consents/marketing",
        json={"granted": True, "version": NOTICE},
        headers=headers,
    )
    assert (withdraw.status_code, stale.status_code, unknown.status_code) == (409, 409, 422)


# --- Deletion request and export ---------------------------------------------------------


def test_deletion_request_is_recorded_once_audited_and_unpairs_devices(
    client: TestClient,
) -> None:
    _user, tenant, headers = _onboarded_user(client)
    pairing = client.post(f"/v1/tenants/{tenant}/copilot/devices", headers=headers).json()
    key = {"X-API-Key": pairing["api_key"]}
    assert client.get(f"/v1/tenants/{tenant}/copilot/session", headers=key).status_code == 200
    url = f"/v1/tenants/{tenant}/account/deletion-request"
    assert client.get(url, headers=headers).json() == {"requested": False, "requested_at": None}
    first = client.post(url, headers=headers)
    second = client.post(url, headers=headers)
    assert (first.status_code, second.status_code) == (202, 200)
    assert first.json()["requested_at"] == second.json()["requested_at"]
    assert _actions(tenant).count("marocassist.account.deletion_request") == 1
    # No device credential stays usable while the request waits.
    assert client.get(f"/v1/tenants/{tenant}/copilot/session", headers=key).status_code == 401
    assert client.get(f"/v1/tenants/{tenant}/copilot/devices", headers=headers).json() == []


def test_export_contains_the_accounts_product_data_and_is_audited(client: TestClient) -> None:
    user_id, tenant, headers = _onboarded_user(client)
    client.post(f"/v1/tenants/{tenant}/copilot/devices", headers=headers)
    response = client.get(f"/v1/tenants/{tenant}/account/export", headers=headers)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert "attachment" in response.headers["content-disposition"]
    body = response.json()
    assert body["user_id"] == str(user_id)
    assert body["workspace_id"] == tenant
    assert body["profile"]["display_name"] == "Canary Person"
    assert {c["purpose"] for c in body["consents"]} == {"privacy_notice", "product_emails"}
    assert len(body["copilot_devices"]) == 1
    assert "sok_" not in response.text
    assert body["settings"] == {"locale": "fr"}
    assert "marocassist.account.export" in _actions(tenant)


# --- 403 and 404 matrix -----------------------------------------------------------------------

_TENANT_ROUTES: list[tuple[str, str, dict[str, Any] | None]] = [
    ("GET", "workspace/settings", None),
    ("PUT", "workspace/settings", {"locale": "fr"}),
    ("GET", "onboarding", None),
    ("POST", "onboarding", _onboarding()),
    ("GET", "profile", None),
    ("PUT", "profile", {"display_name": "x"}),
    ("GET", "consents", None),
    ("PUT", "consents/product_emails", {"granted": True, "version": NOTICE}),
    ("GET", "account/deletion-request", None),
    ("POST", "account/deletion-request", None),
    ("GET", "account/export", None),
    ("GET", "copilot/devices", None),
    ("POST", "copilot/devices", None),
    ("DELETE", f"copilot/devices/{uuid.uuid4()}", None),
]


def test_another_users_tenant_is_404_on_every_route(client: TestClient) -> None:
    _a, _tenant_a, headers_a = _onboarded_user(client)
    _b, tenant_b, _headers_b = _onboarded_user(client)
    for method, suffix, body in _TENANT_ROUTES:
        response = client.request(
            method, f"/v1/tenants/{tenant_b}/{suffix}", json=body, headers=headers_a
        )
        assert response.status_code == 404, (method, suffix, response.status_code)


def test_member_without_a_role_is_403_on_every_route(client: TestClient) -> None:
    """A member of the tenant who holds no role: authenticated, resolved to
    the tenant, refused by RBAC. (Personal tenants have one member; this
    proves the permission check, not a product flow.)"""
    from saas_os.core.authority import SystemAuthority, SystemCaller
    from saas_os.core.identity import add_tenant_membership

    _owner, tenant, _headers = _onboarded_user(client)
    stranger, stranger_headers = _new_user()
    add_tenant_membership(
        uuid.UUID(tenant), stranger, caller=SystemCaller(SystemAuthority.PROVISIONING)
    )
    for method, suffix, body in _TENANT_ROUTES:
        response = client.request(
            method, f"/v1/tenants/{tenant}/{suffix}", json=body, headers=stranger_headers
        )
        assert response.status_code == 403, (method, suffix, response.status_code)


# --- Isolation without a tenant predicate, per table -------------------------------------


def test_rls_isolates_every_phase_2_table_without_a_predicate(client: TestClient) -> None:
    from saas_os.infra.db import select, tenant_session_scope

    from marocassist.accounts.models import Consent, DeletionRequest, Profile

    _a, tenant_a, headers_a = _onboarded_user(client)
    _b, tenant_b, headers_b = _onboarded_user(client)
    for tenant, headers in ((tenant_a, headers_a), (tenant_b, headers_b)):
        client.post(f"/v1/tenants/{tenant}/account/deletion-request", headers=headers)

    for model in (Profile, Consent, DeletionRequest):
        # Deliberately no tenant predicate: Row-Level Security alone decides.
        with tenant_session_scope(uuid.UUID(tenant_a)) as session:
            seen = set(session.execute(select(model.tenant_id)).scalars().all())
        assert seen == {uuid.UUID(tenant_a)}, model.__tablename__


# --- Purge ------------------------------------------------------------------------------------


def test_purge_removes_every_product_row_of_the_tenant_only(client: TestClient) -> None:
    from saas_os.core.tenancy import registered_purge_participant_names
    from saas_os.infra.db import select, session_scope, tenant_session_scope

    from marocassist.accounts.models import (
        Consent,
        DeletionRequest,
        PersonalWorkspace,
        Profile,
        WorkspaceSettings,
    )
    from marocassist.purge import ACCOUNTS_PURGE_PARTICIPANT

    assert registered_purge_participant_names() == (
        "marocassist.accounts",
        "marocassist.knowledge",
    )
    _a, tenant_a, headers_a = _onboarded_user(client)
    _b, tenant_b, headers_b = _onboarded_user(client)
    for tenant, headers in ((tenant_a, headers_a), (tenant_b, headers_b)):
        client.post(f"/v1/tenants/{tenant}/account/deletion-request", headers=headers)

    ACCOUNTS_PURGE_PARTICIPANT.purge_tenant_data(uuid.UUID(tenant_a))
    ACCOUNTS_PURGE_PARTICIPANT.purge_tenant_data(uuid.UUID(tenant_a))  # idempotent

    for model in (Profile, Consent, DeletionRequest, WorkspaceSettings):
        with tenant_session_scope(uuid.UUID(tenant_a)) as session:
            assert session.execute(select(model.tenant_id)).scalars().all() == []
        with tenant_session_scope(uuid.UUID(tenant_b)) as session:
            assert session.execute(select(model.tenant_id)).scalars().all() != []
    with session_scope() as session:
        mapped = set(session.execute(select(PersonalWorkspace.tenant_id)).scalars().all())
    assert uuid.UUID(tenant_a) not in mapped
    assert uuid.UUID(tenant_b) in mapped


# --- Logout -----------------------------------------------------------------------------------


def test_logout_revokes_the_session(client: TestClient) -> None:
    _user, headers = _new_user()
    assert client.get("/auth/me", headers=headers).status_code == 200
    assert client.post("/auth/logout", headers=headers).status_code == 204
    assert client.get("/auth/me", headers=headers).status_code == 401
    assert client.get("/v1/me/workspace", headers=headers).status_code == 401


# --- Copilot device history (S-9) ----------------------------------------------------------


def test_device_history_is_bounded(client: TestClient) -> None:
    _user, tenant, headers = _onboarded_user(client)
    devices_url = f"/v1/tenants/{tenant}/copilot/devices"
    for _ in range(4):  # MAROCASSIST_COPILOT_MAX_DEVICE_HISTORY=4 in tests
        pairing = client.post(devices_url, headers=headers)
        assert pairing.status_code == 201
        device = pairing.json()["device_id"]
        assert client.delete(f"{devices_url}/{device}", headers=headers).status_code == 204
    assert client.get(devices_url, headers=headers).json() == []
    refused = client.post(devices_url, headers=headers)
    assert refused.status_code == 409
    assert refused.json()["detail"] == "device_history_full"


def test_workspace_provisioning_is_rate_limited_per_user(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Before a tenant exists `require_permission`'s per-tenant limit cannot
    apply; the workspace call has its own per-user limit."""
    import dataclasses

    from marocassist.accounts import routes

    tight = dataclasses.replace(routes.get_ratelimit_config(), requests_per_window=3)
    monkeypatch.setattr(routes, "get_ratelimit_config", lambda: tight)
    _user, headers = _new_user()
    statuses = [client.post("/v1/me/workspace", headers=headers).status_code for _ in range(5)]
    assert statuses[:3] == [200, 200, 200]
    assert statuses[3:] == [429, 429]
    _other, other_headers = _new_user()
    assert client.post("/v1/me/workspace", headers=other_headers).status_code == 200
