"""Golden-set evaluation against a real PostgreSQL 16 (Phase 3 WP G; exit
criteria 1 and 4).

Publishes the evaluation corpus (tests/fixtures/knowledge/eval, fixture
content only) with the loader, then runs the golden set
(tests/fixtures/knowledge/golden.json) through the catalogue functions the
API uses, under the application role. The test fails when any language
falls below recall@6 0.85, a fact is wrong, or anything stale leaks.

The report, per language, goes to the path in `KNOWLEDGE_EVAL_REPORT` when
set, and to the GitHub job summary in CI.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from datetime import date
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import Engine

pytestmark = pytest.mark.integration

FIXTURES = Path(__file__).parent / "fixtures" / "knowledge"
CORPUS = FIXTURES / "eval"
GOLDEN = FIXTURES / "golden.json"


@pytest.fixture(scope="module", autouse=True)
def _migrated() -> None:
    from marocassist.migrate import migrate

    migrate()


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


def _tenant() -> uuid.UUID:
    from saas_os.core.identity import get_or_create_user_for_external_identity

    from marocassist.accounts.provisioning import ensure_personal_workspace

    user = get_or_create_user_for_external_identity(
        "http://zitadel.localhost:8081", f"test-eval-{uuid.uuid4().hex}"
    )
    tenant_id, _created = ensure_personal_workspace(user.id)
    return tenant_id


@pytest.fixture(scope="module")
def published(admin: Engine) -> Iterator[None]:
    from saas_os.infra.db import build_engine, build_session_factory, get_migrations_database_config

    from marocassist.knowledge.evaluation import load_golden
    from marocassist.knowledge.loader import check, publish

    golden = load_golden(GOLDEN)
    _clear(admin)
    engine = build_engine(get_migrations_database_config())
    try:
        publish(
            check(CORPUS, today=golden.today),
            tenant_id=_tenant(),
            session_factory=build_session_factory(engine),
        )
    finally:
        engine.dispose()
    yield
    _clear(admin)


def _write_report(markdown: str) -> None:
    target = os.environ.get("KNOWLEDGE_EVAL_REPORT")
    if target:
        Path(target).write_text(markdown, encoding="utf-8")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with Path(summary).open("a", encoding="utf-8") as handle:
            handle.write(markdown)


@pytest.mark.usefixtures("published")
def test_the_golden_set_meets_the_phase_3_thresholds() -> None:
    from marocassist.knowledge import catalogue
    from marocassist.knowledge.content import read_bundle
    from marocassist.knowledge.evaluation import (
        FactCase,
        Freshness,
        SearchCase,
        evaluate,
        load_golden,
        render_markdown,
    )

    golden = load_golden(GOLDEN)
    today = golden.today

    def search(case: SearchCase) -> catalogue.SearchOut:
        return catalogue.search(case.query, lang=case.lang, consulate=case.consulate, today=today)

    def fact(case: FactCase) -> catalogue.FactOut | None:
        return catalogue.get_fact(case.fact_key, consulate=case.consulate, today=today)

    report = evaluate(
        golden,
        search=search,
        fact=fact,
        freshness=Freshness.from_bundle(read_bundle(CORPUS), today),
    )
    markdown = render_markdown(report)
    _write_report(markdown)
    print(markdown)  # noqa: T201 - visible with `pytest -s`
    assert report.failures() == [], markdown


@pytest.mark.usefixtures("published")
def test_a_broken_expiry_would_be_caught() -> None:
    """The leakage metric does not trust the code under test: evaluated one
    year later, every item and fact is stale, and the harness must still
    find no leak, because the catalogue marks them all expired."""
    from datetime import timedelta

    from marocassist.knowledge import catalogue
    from marocassist.knowledge.content import read_bundle
    from marocassist.knowledge.evaluation import Freshness, search_leaks

    later = _today() + timedelta(days=365)
    freshness = Freshness.from_bundle(read_bundle(CORPUS), later)
    assert len(freshness.stale_items) >= 7
    out = catalogue.search("paspoort", lang="nl", today=later)
    assert out.results
    assert search_leaks("later", out, freshness) == []
    # The same results, judged as of the earlier date, would be a leak.
    relabelled = out.model_copy(
        update={"results": [r.model_copy(update={"status": "current"}) for r in out.results]}
    )
    assert search_leaks("later", relabelled, freshness)


def _today() -> date:
    from marocassist.knowledge.evaluation import load_golden

    return load_golden(GOLDEN).today
