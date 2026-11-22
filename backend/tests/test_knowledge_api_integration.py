"""Integration tests for the knowledge API (Phase 3 WP D) against a real
PostgreSQL 16 and Redis 7: the routes, their 401/403/404 behaviour, fact
scope and conflict, consulate attributes, read-time expiry and reports.

The fixture bundle is published with the loader, plus three facts: two
different Rotterdam values for the passport fee (a conflict) and a fee that
exists only per consulate.
"""

from __future__ import annotations

import json
import os
import shutil
import uuid
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine

pytestmark = pytest.mark.integration

VALID = Path(__file__).parent / "fixtures" / "knowledge" / "valid"
TODAY = date(2026, 11, 21)
PASSPORT = "fixture.passport-renewal"
WITHDRAWN = "fixture.old-passport-procedure"
FEE = "fee.passport_renewal.adult"
CARD_FEE = "fee.consular_card.adult"


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


@pytest.fixture(scope="module")
def admin() -> Iterator[Engine]:
    engine = sa.create_engine(os.environ["MIGRATIONS_DATABASE_URL"])
    yield engine
    engine.dispose()


def _clear(admin: Engine) -> None:
    from marocassist.knowledge.loader import WRITE_ORDER

    with admin.begin() as conn:
        for table in reversed(WRITE_ORDER):
            conn.execute(sa.text(f"DELETE FROM marocassist.{table}"))
        conn.execute(
            sa.text(
                "DELETE FROM marocassist.knowledge_publications"
                " WHERE content_version LIKE 'sha256:%'"
            )
        )


def _extra_fact(base: dict[str, Any], fact_id: str, key: str, scope: str, value: int) -> Any:
    fact = json.loads(json.dumps(base))
    fact.update({"fact_id": fact_id, "fact_key": key, "scope": scope, "value": value})
    return fact


def _bundle_root(tmp: Path) -> Path:
    root = tmp / "bundle"
    shutil.copytree(VALID, root)
    facts_path = root / "facts.json"
    facts = json.loads(facts_path.read_text(encoding="utf-8"))
    base = facts[0]
    facts += [
        _extra_fact(base, "fixture.fee.passport.rdam-a", FEE, "consulate:nl-rotterdam", 300),
        _extra_fact(base, "fixture.fee.passport.rdam-b", FEE, "consulate:nl-rotterdam", 350),
        _extra_fact(base, "fixture.fee.card.rdam", CARD_FEE, "consulate:nl-rotterdam", 120),
    ]
    facts_path.write_bytes(json.dumps(facts, ensure_ascii=False, indent=2).encode("utf-8"))
    return root


@pytest.fixture(scope="module")
def published(
    app: FastAPI, admin: Engine, tmp_path_factory: pytest.TempPathFactory
) -> Iterator[None]:
    from saas_os.core.identity import get_or_create_user_for_external_identity
    from saas_os.infra.db import build_engine, build_session_factory, get_migrations_database_config

    from marocassist.accounts.provisioning import ensure_personal_workspace
    from marocassist.knowledge.loader import check, publish

    editor = get_or_create_user_for_external_identity(
        "http://zitadel.localhost:8081", f"test-kn-api-{uuid.uuid4().hex}"
    )
    tenant_id, _created = ensure_personal_workspace(editor.id)
    _clear(admin)
    bundle = check(_bundle_root(tmp_path_factory.mktemp("api")), today=TODAY)
    engine = build_engine(get_migrations_database_config())
    try:
        publish(bundle, tenant_id=tenant_id, session_factory=build_session_factory(engine))
    finally:
        engine.dispose()
    yield
    _clear(admin)


def _new_user() -> dict[str, str]:
    from saas_os.core.identity import get_or_create_user_for_external_identity
    from saas_os.core.identity.sessions import issue_session

    subject = f"test-{uuid.uuid4().hex}"
    user = get_or_create_user_for_external_identity("http://zitadel.localhost:8081", subject)
    _session, token = issue_session(user.id, verified_email=f"{subject}@example.test")
    return {"Authorization": f"Bearer {token}"}


def _workspace(client: TestClient, headers: dict[str, str]) -> str:
    response = client.post("/v1/me/workspace", headers=headers)
    assert response.status_code == 200, response.text
    return str(response.json()["tenant_id"])


@pytest.fixture
def owner(client: TestClient) -> tuple[str, dict[str, str]]:
    headers = _new_user()
    return _workspace(client, headers), headers


def _base(tenant: str) -> str:
    return f"/v1/tenants/{tenant}/knowledge"


READ_PATHS = (
    "/search?q=paspoort",
    f"/items/{PASSPORT}",
    f"/facts/{FEE}",
    "/consulates",
    "/consulates/nl-rotterdam",
)


# --- Reads -------------------------------------------------------------------------


@pytest.mark.usefixtures("published")
def test_search_returns_titles_snippets_and_source_cards(
    client: TestClient, owner: tuple[str, dict[str, str]]
) -> None:
    tenant, headers = owner
    response = client.get(
        f"{_base(tenant)}/search", params={"q": "paspoort verlengen"}, headers=headers
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == {"langs", "detected_lang", "results"}  # the query is not echoed
    best = body["results"][0]
    assert best["item_id"] == PASSPORT
    assert best["title"] and best["snippet"]
    assert not best["partial"]
    assert best["status"] == "current"
    assert best["sources"][0]["url"].startswith("https://")
    assert best["sources"][0]["badge"] == "official"
    assert WITHDRAWN not in [r["item_id"] for r in body["results"]]


@pytest.mark.usefixtures("published")
def test_search_validates_its_parameters(
    client: TestClient, owner: tuple[str, dict[str, str]]
) -> None:
    tenant, headers = owner
    for params in (
        {},
        {"q": "x" * 1001},
        {"q": "paspoort", "lang": "de"},
        {"q": "paspoort", "consulate": "NL_Rotterdam"},
        {"q": "paspoort", "kind": "secret"},
    ):
        response = client.get(f"{_base(tenant)}/search", params=params, headers=headers)
        assert response.status_code == 422, (params, response.status_code)
    empty = client.get(f"{_base(tenant)}/search", params={"q": "   "}, headers=headers)
    assert empty.status_code == 200
    assert empty.json()["results"] == []


@pytest.mark.usefixtures("published")
def test_items_current_withdrawn_and_missing(
    client: TestClient, owner: tuple[str, dict[str, str]]
) -> None:
    tenant, headers = owner
    item = client.get(f"{_base(tenant)}/items/{PASSPORT}?lang=fr", headers=headers)
    assert item.status_code == 200, item.text
    body = item.json()
    assert (body["lang"], body["status"]) == ("fr", "current")
    assert body["body"] and body["sources"]

    withdrawn = client.get(f"{_base(tenant)}/items/{WITHDRAWN}", headers=headers).json()
    assert withdrawn["status"] == "withdrawn"
    assert withdrawn["superseded_by"] == PASSPORT
    assert withdrawn["body"] is None and withdrawn["title"] is None

    missing = client.get(f"{_base(tenant)}/items/fixture.nothing-here", headers=headers)
    assert missing.status_code == 404
    bad = client.get(f"{_base(tenant)}/items/Not_An_Id", headers=headers)
    assert bad.status_code == 422


@pytest.mark.usefixtures("published")
def test_facts_scope_conflict_and_clarification(
    client: TestClient, owner: tuple[str, dict[str, str]]
) -> None:
    tenant, headers = owner
    base = _base(tenant)

    general = client.get(f"{base}/facts/{FEE}", headers=headers).json()
    assert (general["scope"], general["status"]) == ("global", "current")
    assert [v["value"] for v in general["values"]] == [300]

    rotterdam = client.get(f"{base}/facts/{FEE}?consulate=nl-rotterdam", headers=headers).json()
    assert rotterdam["scope"] == "consulate:nl-rotterdam"
    assert rotterdam["status"] == "conflict"
    assert sorted(v["value"] for v in rotterdam["values"]) == [300, 350]
    assert all(v["sources"] for v in rotterdam["values"])

    utrecht = client.get(f"{base}/facts/{FEE}?consulate=nl-utrecht", headers=headers).json()
    assert utrecht["scope"] == "global"

    card = client.get(f"{base}/facts/{CARD_FEE}", headers=headers).json()
    assert card["needs_consulate"] and card["values"] == []
    assert card["consulates"] == ["nl-rotterdam"]

    assert client.get(f"{base}/facts/fee.nothing.here", headers=headers).status_code == 404
    assert client.get(f"{base}/facts/nodots", headers=headers).status_code == 422


@pytest.mark.usefixtures("published")
def test_rotterdam_is_located_in_schiedam_pending_review(
    client: TestClient, owner: tuple[str, dict[str, str]]
) -> None:
    tenant, headers = owner
    listing = client.get(f"{_base(tenant)}/consulates", headers=headers)
    assert listing.status_code == 200
    assert [c["code"] for c in listing.json()] == ["nl-rotterdam"]

    detail = client.get(f"{_base(tenant)}/consulates/nl-rotterdam?lang=fr", headers=headers)
    assert detail.status_code == 200
    body = detail.json()
    assert body["display_name"] == "Consulaat-generaal Rotterdam"  # NL fallback
    city = next(a for a in body["attributes"] if a["attribute"] == "physical_city")
    assert (city["value"], city["status"], city["independently_confirmed"]) == (
        "Schiedam",
        "pending_review",
        False,
    )
    assert city["source"]["url"].startswith("https://")
    assert "opening_hours" in body["missing"]
    assert client.get(f"{_base(tenant)}/consulates/nl-nowhere", headers=headers).status_code == 404


@pytest.mark.usefixtures("published")
def test_expired_content_is_never_presented_as_current() -> None:
    from marocassist.knowledge import catalogue

    later = date(2027, 6, 1)
    item = catalogue.get_item(PASSPORT, lang="nl", today=later)
    assert item.status == "expired"
    fact = catalogue.get_fact(FEE, consulate=None, today=later)
    assert fact is not None
    assert fact.status == "expired"
    assert {v.status for v in fact.values} == {"expired"}
    assert {s.status for v in fact.values for s in v.sources} == {"expired"}
    results = catalogue.search("paspoort verlengen", lang="nl", today=later).results
    assert results
    assert {r.status for r in results} == {"expired"}


# --- Reports -----------------------------------------------------------------------


@pytest.mark.usefixtures("published")
def test_reports_are_stored_once_per_day_per_tenant(
    client: TestClient, owner: tuple[str, dict[str, str]], admin: Engine
) -> None:
    tenant, headers = owner
    url = f"{_base(tenant)}/reports"
    first = client.post(url, json={"item_id": PASSPORT, "reason_code": "outdated"}, headers=headers)
    assert first.status_code == 201, first.text
    again = client.post(url, json={"item_id": PASSPORT, "reason_code": "outdated"}, headers=headers)
    assert again.status_code == 200
    assert again.json()["report_id"] == first.json()["report_id"]
    other = client.post(
        url, json={"item_id": PASSPORT, "reason_code": "broken_link"}, headers=headers
    )
    assert other.status_code == 201

    for body in (
        {"item_id": WITHDRAWN, "reason_code": "outdated"},
        {"item_id": "fixture.nothing-here", "reason_code": "outdated"},
    ):
        assert client.post(url, json=body, headers=headers).status_code == 404
    for body in (
        {"item_id": PASSPORT, "reason_code": "spam"},
        {"item_id": PASSPORT, "reason_code": "outdated", "note": "free text"},
        {"item_id": "../etc", "reason_code": "outdated"},
    ):
        assert client.post(url, json=body, headers=headers).status_code == 422, body

    with admin.connect() as conn:
        rows = conn.execute(
            sa.text(
                "SELECT item_id, reason_code FROM marocassist.knowledge_reports"
                " WHERE tenant_id = :t ORDER BY reason_code"
            ),
            {"t": tenant},
        ).all()
    assert [tuple(r) for r in rows] == [(PASSPORT, "broken_link"), (PASSPORT, "outdated")]


# --- 401 / 403 / 404 ---------------------------------------------------------------


@pytest.mark.usefixtures("published")
def test_another_users_tenant_is_the_same_404_as_a_missing_one(
    client: TestClient, owner: tuple[str, dict[str, str]]
) -> None:
    tenant_b, _headers_b = owner
    headers_a = _new_user()
    _workspace(client, headers_a)
    for path in READ_PATHS:
        foreign = client.get(f"{_base(tenant_b)}{path}", headers=headers_a)
        missing = client.get(f"{_base(str(uuid.uuid4()))}{path}", headers=headers_a)
        assert foreign.status_code == missing.status_code == 404, path
        assert foreign.json() == missing.json()
    report = client.post(
        f"{_base(tenant_b)}/reports",
        json={"item_id": PASSPORT, "reason_code": "outdated"},
        headers=headers_a,
    )
    assert report.status_code == 404


def _revoke(admin: Engine, tenant: str, action: str) -> None:
    """Simulate a tenant provisioned before Phase 3: its owner role lacks
    the knowledge permission until grant migration 0002 is applied."""
    with admin.begin() as conn:
        conn.execute(
            sa.text(
                "DELETE FROM core.role_permissions rp USING core.permissions p"
                " WHERE rp.permission_id = p.id AND rp.tenant_id = :t"
                " AND p.resource = 'marocassist.knowledge' AND p.action = :a"
            ),
            {"t": tenant, "a": action},
        )


@pytest.mark.usefixtures("published")
def test_without_the_knowledge_permissions_every_route_is_403(
    client: TestClient, owner: tuple[str, dict[str, str]], admin: Engine
) -> None:
    tenant, headers = owner
    assert client.get(f"{_base(tenant)}/consulates", headers=headers).status_code == 200
    _revoke(admin, tenant, "read")
    for path in READ_PATHS:
        response = client.get(f"{_base(tenant)}{path}", headers=headers)
        assert response.status_code == 403, (path, response.status_code)
    report = {"item_id": PASSPORT, "reason_code": "outdated"}
    url = f"{_base(tenant)}/reports"
    assert client.post(url, json=report, headers=headers).status_code == 201
    _revoke(admin, tenant, "report")
    assert client.post(url, json=report, headers=headers).status_code == 403


def test_the_knowledge_functions_are_not_executable_by_public(admin: Engine) -> None:
    from marocassist.knowledge.fts import STATEMENT_TIMEOUT_MS

    assert STATEMENT_TIMEOUT_MS == 200
    with admin.connect() as conn:
        rows = conn.execute(
            sa.text(
                "SELECT p.proname,"
                " has_function_privilege('public', p.oid, 'EXECUTE') AS public_exec"
                " FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace"
                " WHERE n.nspname = 'marocassist' AND p.proname LIKE 'knowledge\\_%'"
            )
        ).all()
    names = {r.proname: r.public_exec for r in rows}
    assert set(names) == {
        "knowledge_search",
        "knowledge_expand_terms",
        "knowledge_items",
        "knowledge_facts",
        "knowledge_consulates",
    }
    assert not any(names.values())
