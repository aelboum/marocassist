"""Integration tests for freshness and the daily editor review report
(Phase 3 WP F) against a real PostgreSQL 16: the anonymous report counter,
the once-per-day report in the editorial tenant, its isolation and purge,
and the worker schedule."""

from __future__ import annotations

import os
import shutil
import uuid
from collections.abc import Iterator
from datetime import date, timedelta
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import Engine

pytestmark = pytest.mark.integration

VALID = Path(__file__).parent / "fixtures" / "knowledge" / "valid"
TODAY = date(2026, 11, 21)
PASSPORT = "fixture.passport-renewal"


@pytest.fixture(scope="module", autouse=True)
def _migrated() -> None:
    from marocassist.migrate import migrate

    migrate()


@pytest.fixture(scope="module")
def admin() -> Iterator[Engine]:
    engine = sa.create_engine(os.environ["MIGRATIONS_DATABASE_URL"])
    yield engine
    engine.dispose()


def _tenant() -> uuid.UUID:
    from saas_os.core.identity import get_or_create_user_for_external_identity

    from marocassist.accounts.provisioning import ensure_personal_workspace

    user = get_or_create_user_for_external_identity(
        "http://zitadel.localhost:8081", f"test-review-{uuid.uuid4().hex}"
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
        conn.execute(sa.text("DELETE FROM marocassist.knowledge_report_counts"))


@pytest.fixture(scope="module")
def editorial(admin: Engine, tmp_path_factory: pytest.TempPathFactory) -> Iterator[uuid.UUID]:
    from saas_os.infra.db import build_engine, build_session_factory, get_migrations_database_config

    from marocassist.knowledge.loader import check, publish

    tenant_id = _tenant()
    _clear(admin)
    root = tmp_path_factory.mktemp("review") / "bundle"
    shutil.copytree(VALID, root)
    engine = build_engine(get_migrations_database_config())
    try:
        publish(
            check(root, today=TODAY),
            tenant_id=tenant_id,
            session_factory=build_session_factory(engine),
        )
    finally:
        engine.dispose()
    yield tenant_id
    _clear(admin)


def _counts(admin: Engine) -> list[tuple[str, str, int]]:
    with admin.connect() as conn:
        rows = conn.execute(
            sa.text(
                "SELECT item_id, reason_code, count FROM marocassist.knowledge_report_counts"
                " ORDER BY item_id, reason_code"
            )
        ).all()
    return [tuple(r) for r in rows]  # type: ignore[misc]


@pytest.mark.usefixtures("editorial")
def test_each_new_report_bumps_the_anonymous_counter_once(admin: Engine) -> None:
    from marocassist.knowledge.reports import create_report

    first, second = _tenant(), _tenant()
    assert create_report(first, PASSPORT, "outdated").created
    assert not create_report(first, PASSPORT, "outdated").created  # deduplicated
    assert create_report(second, PASSPORT, "outdated").created
    assert create_report(second, PASSPORT, "incorrect").created
    assert _counts(admin) == [(PASSPORT, "incorrect", 1), (PASSPORT, "outdated", 2)]
    with admin.connect() as conn:
        columns = {
            r[0]
            for r in conn.execute(
                sa.text(
                    "SELECT column_name FROM information_schema.columns"
                    " WHERE table_schema = 'marocassist'"
                    " AND table_name = 'knowledge_report_counts'"
                )
            )
        }
    assert columns == {"item_id", "reason_code", "day", "count"}


def test_the_app_role_may_count_but_not_delete_or_write_knowledge() -> None:
    from saas_os.infra.db import get_engine

    with get_engine().connect() as conn:
        grants = {
            r[0]
            for r in conn.execute(
                sa.text(
                    "SELECT privilege_type FROM information_schema.table_privileges"
                    " WHERE table_schema = 'marocassist'"
                    " AND table_name = 'knowledge_report_counts' AND grantee = current_user"
                )
            )
        }
        review_grants = {
            r[0]
            for r in conn.execute(
                sa.text(
                    "SELECT privilege_type FROM information_schema.table_privileges"
                    " WHERE table_schema = 'marocassist'"
                    " AND table_name = 'knowledge_review_reports' AND grantee = current_user"
                )
            )
        }
    assert grants == {"SELECT", "INSERT", "UPDATE"}
    assert review_grants == {"SELECT", "INSERT", "DELETE"}


def test_the_review_report_is_written_once_per_day(editorial: uuid.UUID, admin: Engine) -> None:
    from marocassist.knowledge.review import run_daily_review

    later = date(2027, 6, 1)
    with admin.begin() as conn:
        conn.execute(
            sa.text(
                "INSERT INTO marocassist.knowledge_report_counts (item_id, reason_code, day, count)"
                " VALUES (:i, 'broken_link', :d, 4)"
            ),
            {"i": PASSPORT, "d": later - timedelta(days=1)},
        )
    first = run_daily_review(today=later, tenant_id=editorial)
    again = run_daily_review(today=later, tenant_id=editorial)
    assert first is not None and first == again

    with admin.connect() as conn:
        rows = conn.execute(
            sa.text(
                "SELECT report_date, summary FROM marocassist.knowledge_review_reports"
                " WHERE tenant_id = :t"
            ),
            {"t": editorial},
        ).all()
    assert len(rows) == 1
    summary = rows[0].summary
    assert rows[0].report_date == later
    assert PASSPORT in [i["id"] for i in summary["items"]["expired"]]
    assert "fixture.old-passport-procedure" not in repr(summary)  # withdrawn
    assert summary["user_reports_yesterday"] == [
        {"item_id": PASSPORT, "reason_code": "broken_link", "count": 4}
    ]
    assert summary["needs_attention"] >= 2


@pytest.mark.usefixtures("editorial")
def test_the_review_report_is_isolated_and_purged_with_its_tenant(
    editorial: uuid.UUID,
) -> None:
    from saas_os.infra.db import select, tenant_session_scope

    from marocassist.knowledge.models import KnowledgeReviewReport
    from marocassist.knowledge.review import run_daily_review
    from marocassist.purge import KNOWLEDGE_PURGE_PARTICIPANT

    run_daily_review(today=TODAY, tenant_id=editorial)
    other = _tenant()

    def visible(tenant_id: uuid.UUID) -> int:
        with tenant_session_scope(tenant_id) as session:
            return len(session.execute(select(KnowledgeReviewReport)).scalars().all())

    assert visible(editorial) >= 1
    assert visible(other) == 0
    KNOWLEDGE_PURGE_PARTICIPANT.purge_tenant_data(editorial)
    KNOWLEDGE_PURGE_PARTICIPANT.purge_tenant_data(editorial)  # idempotent
    assert visible(editorial) == 0


def test_without_an_editorial_tenant_the_job_does_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from marocassist.knowledge.review import run_daily_review

    monkeypatch.delenv("MAROCASSIST_EDITORIAL_TENANT_ID", raising=False)
    assert run_daily_review(today=TODAY) is None


def test_the_worker_schedules_the_review_job() -> None:
    """Builds the real worker the way `marocassist.worker` does (without
    starting it), so SaaS-OS's startup checks on our jobs run here."""
    from saas_os.api.worker import build_production_worker

    from marocassist.jobs import CRON_JOBS, JOB_FUNCTIONS

    assert [c.name for c in CRON_JOBS] == ["marocassist_knowledge_review"]
    worker = build_production_worker(extra_functions=JOB_FUNCTIONS, extra_cron_jobs=CRON_JOBS)
    assert "marocassist_knowledge_review" in worker.functions
