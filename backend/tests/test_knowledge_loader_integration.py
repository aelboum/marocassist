"""Integration tests for the publishing loader (Phase 3 WP B), against a real
PostgreSQL 16 (see test_integration.py for the setup).

The loader replaces all global knowledge, so every test starts and ends with
an empty knowledge store. Only publications the loader made (content
version `sha256:...`) are removed; other fixtures use other versions.
"""

from __future__ import annotations

import json
import os
import shutil
import uuid
from collections.abc import Iterator
from datetime import date
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError

pytestmark = pytest.mark.integration

VALID = Path(__file__).parent / "fixtures" / "knowledge" / "valid"
TODAY = date(2026, 11, 21)


@pytest.fixture(scope="module", autouse=True)
def _migrated() -> None:
    from marocassist.migrate import migrate

    migrate()


@pytest.fixture(scope="module")
def admin() -> Iterator[Engine]:
    engine = sa.create_engine(os.environ["MIGRATIONS_DATABASE_URL"])
    yield engine
    engine.dispose()


@pytest.fixture(scope="module")
def app_engine() -> Iterator[Engine]:
    engine = sa.create_engine(os.environ["DATABASE_URL"])
    yield engine
    engine.dispose()


@pytest.fixture(scope="module")
def migrations_factory() -> Iterator[object]:
    from saas_os.infra.db import build_engine, build_session_factory, get_migrations_database_config

    engine = build_engine(get_migrations_database_config())
    yield build_session_factory(engine)
    engine.dispose()


@pytest.fixture(scope="module")
def editorial() -> uuid.UUID:
    from saas_os.core.identity import get_or_create_user_for_external_identity

    from marocassist.accounts.provisioning import ensure_personal_workspace

    user = get_or_create_user_for_external_identity(
        "http://zitadel.localhost:8081", f"test-editorial-{uuid.uuid4().hex}"
    )
    tenant_id, _created = ensure_personal_workspace(user.id)
    return tenant_id


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


@pytest.fixture(autouse=True)
def _empty_store(admin: Engine) -> Iterator[None]:
    _clear(admin)
    yield
    _clear(admin)


def _bundle(root: Path = VALID) -> object:
    from marocassist.knowledge.loader import check

    return check(root, today=TODAY)


def _publish(bundle: object, tenant: uuid.UUID, factory: object) -> object:
    from marocassist.knowledge.loader import publish

    return publish(bundle, tenant_id=tenant, session_factory=factory)  # type: ignore[arg-type]


def _count(engine: Engine, table: str) -> int:
    with engine.connect() as conn:
        return int(conn.execute(sa.text(f"SELECT count(*) FROM marocassist.{table}")).scalar_one())


def _audit(tenant: uuid.UUID) -> list[object]:
    from saas_os.core import audit_log

    return [
        e
        for e in audit_log.list(tenant, resource_type="marocassist.knowledge_publication")
        if e.action == "marocassist.knowledge.publish"
    ]


def test_publish_loads_every_table(
    admin: Engine, editorial: uuid.UUID, migrations_factory: object
) -> None:
    result = _publish(_bundle(), editorial, migrations_factory)
    assert result.changed  # type: ignore[attr-defined]
    expected = {
        "knowledge_sources": 2,
        "knowledge_items": 3,
        "knowledge_item_texts": 5,
        "knowledge_facts": 1,
        "knowledge_citations": 4,
        "knowledge_terms": 3,
        "consulates": 1,
        "consulate_attributes": 3,
        "consulate_jurisdictions": 0,
    }
    for table, count in expected.items():
        assert _count(admin, table) == count, table
    assert _count(admin, "knowledge_chunks") >= 5
    with admin.connect() as conn:
        version = conn.execute(
            sa.text(
                "SELECT DISTINCT p.content_version FROM marocassist.knowledge_items i"
                " JOIN marocassist.knowledge_publications p USING (publication_id)"
            )
        ).scalar_one()
    assert version == result.content_version  # type: ignore[attr-defined]


def test_published_content_is_searchable_by_the_app_role(
    app_engine: Engine, editorial: uuid.UUID, migrations_factory: object
) -> None:
    _publish(_bundle(), editorial, migrations_factory)

    def search(query: str, langs: list[str]) -> list[str]:
        with app_engine.connect() as conn:
            rows = conn.execute(
                sa.text("SELECT item_id FROM marocassist.knowledge_search(:q, :l, 'NL')"),
                {"q": query, "l": langs},
            )
            return [r.item_id for r in rows]

    assert "fixture.passport-renewal" in search("paspoort afspraak", ["nl"])
    assert "fixture.passport-renewal" in search("rendez-vous passeport", ["fr"])
    # The Arabic text is pending review, the old procedure withdrawn: neither is found.
    arabic = "".join(chr(c) for c in (0x062A, 0x062C, 0x062F, 0x064A, 0x062F))
    assert search(arabic, ["ar"]) == []
    assert "fixture.old-passport-procedure" not in search("procedure paspoort", ["nl"])


def test_publish_is_idempotent(
    admin: Engine, editorial: uuid.UUID, migrations_factory: object
) -> None:
    before = len(_audit(editorial))
    first = _publish(_bundle(), editorial, migrations_factory)
    second = _publish(_bundle(), editorial, migrations_factory)
    assert first.changed and not second.changed  # type: ignore[attr-defined]
    assert second.content_version == first.content_version  # type: ignore[attr-defined]
    assert _count(admin, "knowledge_items") == 3
    with admin.connect() as conn:
        publications = conn.execute(
            sa.text(
                "SELECT count(*) FROM marocassist.knowledge_publications WHERE content_version = :v"
            ),
            {"v": first.content_version},  # type: ignore[attr-defined]
        ).scalar_one()
    assert publications == 1
    assert len(_audit(editorial)) == before + 1


def test_publication_is_audited_without_text(
    editorial: uuid.UUID, migrations_factory: object
) -> None:
    result = _publish(_bundle(), editorial, migrations_factory)
    entries = [
        e
        for e in _audit(editorial)
        if e.resource_id == str(result.publication_id)  # type: ignore[attr-defined]
    ]
    assert len(entries) == 1
    entry = entries[0]
    assert entry.actor_type == "system"  # type: ignore[attr-defined]
    metadata = entry.entry_metadata  # type: ignore[attr-defined]
    assert metadata["content_version"] == result.content_version  # type: ignore[attr-defined]
    assert metadata["counts"]["knowledge_items"] == 3
    serialised = json.dumps(metadata)
    for text in ("Paspoort", "paspoort", "Schiedam", "ed-fixture"):
        assert text not in serialised


def test_republish_replaces_content(
    tmp_path: Path, admin: Engine, editorial: uuid.UUID, migrations_factory: object
) -> None:
    _publish(_bundle(), editorial, migrations_factory)
    root = tmp_path / "bundle"
    shutil.copytree(VALID, root)
    (root / "items" / "fixture.consulate-visit.json").unlink()
    second = _publish(_bundle(root), editorial, migrations_factory)
    assert second.changed  # type: ignore[attr-defined]
    with admin.connect() as conn:
        ids = set(
            conn.execute(sa.text("SELECT item_id FROM marocassist.knowledge_items")).scalars()
        )
        publications = set(
            conn.execute(
                sa.text("SELECT DISTINCT publication_id FROM marocassist.knowledge_items")
            ).scalars()
        )
    assert ids == {"fixture.passport-renewal", "fixture.old-passport-procedure"}
    assert publications == {second.publication_id}  # type: ignore[attr-defined]


def test_failed_publication_leaves_previous_content(
    tmp_path: Path, admin: Engine, editorial: uuid.UUID, migrations_factory: object
) -> None:
    from marocassist.knowledge.loader import PublishError

    first = _publish(_bundle(), editorial, migrations_factory)
    root = tmp_path / "bundle"
    shutil.copytree(VALID, root)
    (root / "items" / "fixture.consulate-visit.json").unlink()
    # No such tenant: the audit row cannot be written, so nothing is.
    with pytest.raises(PublishError):
        _publish(_bundle(root), uuid.uuid4(), migrations_factory)
    assert _count(admin, "knowledge_items") == 3
    with admin.connect() as conn:
        latest = conn.execute(
            sa.text(
                "SELECT content_version FROM marocassist.knowledge_publications"
                " ORDER BY published_at DESC LIMIT 1"
            )
        ).scalar_one()
    assert latest == first.content_version  # type: ignore[attr-defined]


def test_global_tables_hold_no_editorial_fields(
    admin: Engine, editorial: uuid.UUID, migrations_factory: object
) -> None:
    from marocassist.knowledge.loader import WRITE_ORDER

    _publish(_bundle(), editorial, migrations_factory)
    with admin.connect() as conn:
        for table in WRITE_ORDER:
            dump = conn.execute(
                sa.text(f"SELECT coalesce(string_agg(t::text, ' '), '') FROM marocassist.{table} t")
            ).scalar_one()
            assert "ed-fixture" not in dump, table
            assert "Fixture source for tests" not in dump, table


def test_app_role_cannot_publish(editorial: uuid.UUID) -> None:
    from saas_os.infra.db import build_engine, build_session_factory, get_database_config

    engine = build_engine(get_database_config())
    try:
        with pytest.raises(DBAPIError):
            _publish(_bundle(), editorial, build_session_factory(engine))
    finally:
        engine.dispose()
