"""Integration tests for the Phase 3 knowledge schema (WP A), against a real
PostgreSQL 16 (see test_integration.py for the setup).

Fixture knowledge is written with the migrations role, as the publishing
loader will be; the application role is only ever used to read. Every
fixture row carries a random id prefix and is removed afterwards.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from datetime import date, timedelta
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import DBAPIError, IntegrityError, ProgrammingError

pytestmark = pytest.mark.integration

GLOBAL_TABLES = (
    "knowledge_publications",
    "knowledge_sources",
    "knowledge_items",
    "knowledge_item_texts",
    "knowledge_chunks",
    "knowledge_facts",
    "knowledge_citations",
    "knowledge_terms",
    "consulates",
    "consulate_attributes",
    "consulate_jurisdictions",
)

TODAY = date.today()


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


# --- Fixture content ----------------------------------------------------------------


def _insert(conn: Connection, table: str, row: dict[str, Any]) -> None:
    columns = ", ".join(row)
    values = ", ".join(f":{k}" for k in row)
    conn.execute(sa.text(f"INSERT INTO marocassist.{table} ({columns}) VALUES ({values})"), row)


class Corpus:
    """A small published corpus under a random id prefix."""

    def __init__(self, conn: Connection) -> None:
        self.p = f"t{uuid.uuid4().hex[:8]}"
        self.publication = uuid.uuid4()
        self.source = f"src-{self.p}-official"
        _insert(
            conn,
            "knowledge_publications",
            {
                "publication_id": self.publication,
                "content_version": f"test-{self.p}",
                "item_count": 0,
                "fact_count": 0,
            },
        )
        _insert(
            conn,
            "knowledge_sources",
            {
                "source_id": self.source,
                "title": "Passeport",
                "official_url": "https://www.consulat.ma/fr/passeport",
                "publisher": "MAECAMRE",
                "publisher_key": "maecamre",
                "source_type": "official",
                "country": "MA",
                "geo_scope": "global",
                "language": "fr",
                "consulted_at": TODAY,
                "verified_at": TODAY,
                "review_due_at": TODAY + timedelta(days=180),
                "licence": "unknown",
                "allowed_use": ["link", "cite_fact", "summary"],
                "status": "verified",
            },
        )

    def item(
        self,
        conn: Connection,
        name: str,
        texts: dict[str, tuple[str, list[str]]],
        *,
        status: str = "published",
        review_due: date | None = None,
        consulates: list[str] | None = None,
        country: list[str] | None = None,
        kind: str = "procedure",
        lang_status: str = "published",
    ) -> str:
        item_id = f"{self.p}.{name}"
        _insert(
            conn,
            "knowledge_items",
            {
                "item_id": item_id,
                "kind": kind,
                "rights_class": "R1",
                "country_scope": country or ["NL"],
                "consulate_scope": consulates or [],
                "topic_keys": ["passport"],
                "status": status,
                "version": 1,
                "review_due_at": review_due or TODAY + timedelta(days=180),
                "publication_id": self.publication,
            },
        )
        for lang, (title, chunks) in texts.items():
            _insert(
                conn,
                "knowledge_item_texts",
                {
                    "item_id": item_id,
                    "lang": lang,
                    "title": title,
                    "body": " ".join(chunks),
                    "keywords": [],
                    "lang_status": lang_status,
                    "verified_at": TODAY,
                },
            )
            for ordinal, body in enumerate(chunks):
                _insert(
                    conn,
                    "knowledge_chunks",
                    {
                        "item_id": item_id,
                        "lang": lang,
                        "ordinal": ordinal,
                        "heading": title,
                        "body": body,
                    },
                )
        _insert(conn, "knowledge_citations", {"item_id": item_id, "source_id": self.source})
        return item_id

    def remove(self, conn: Connection) -> None:
        conn.execute(
            sa.text("DELETE FROM marocassist.knowledge_items WHERE item_id LIKE :p"),
            {"p": f"{self.p}.%"},
        )
        conn.execute(
            sa.text("DELETE FROM marocassist.knowledge_sources WHERE source_id = :s"),
            {"s": self.source},
        )
        conn.execute(
            sa.text("DELETE FROM marocassist.knowledge_publications WHERE publication_id = :u"),
            {"u": self.publication},
        )


@pytest.fixture
def corpus(admin: Engine) -> Iterator[tuple[Corpus, Connection]]:
    with admin.begin() as conn:
        c = Corpus(conn)
    with admin.connect() as conn:
        yield c, conn
        conn.rollback()
    with admin.begin() as conn:
        c.remove(conn)


def _search(
    engine: Engine,
    query: str,
    langs: list[str],
    *,
    country: str = "NL",
    consulate: str | None = None,
    kinds: list[str] | None = None,
    limit: int = 6,
) -> list[Any]:
    with engine.connect() as conn:
        return list(
            conn.execute(
                sa.text(
                    "SELECT * FROM marocassist.knowledge_search("
                    ":q, CAST(:langs AS text[]), :country, :consulate,"
                    " CAST(:kinds AS text[]), :limit)"
                ),
                {
                    "q": query,
                    "langs": langs,
                    "country": country,
                    "consulate": consulate,
                    "kinds": kinds,
                    "limit": limit,
                },
            )
        )


def _ids(rows: list[Any], prefix: str) -> list[str]:
    return [r.item_id for r in rows if r.item_id.startswith(prefix)]


# --- Schema, extensions, grants ------------------------------------------------------


def test_search_extensions_are_installed(admin: Engine) -> None:
    with admin.connect() as conn:
        names = set(conn.execute(sa.text("SELECT extname FROM pg_extension")).scalars())
    assert {"pg_trgm", "unaccent"} <= names


def _first_column(engine: Engine, table: str) -> str:
    with engine.connect() as conn:
        return str(
            conn.execute(
                sa.text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema = 'marocassist' AND table_name = :t "
                    "AND is_identity = 'NO' AND is_generated = 'NEVER' "
                    "ORDER BY ordinal_position LIMIT 1"
                ),
                {"t": table},
            ).scalar_one()
        )


@pytest.mark.parametrize("table", GLOBAL_TABLES)
def test_application_role_cannot_write_global_knowledge(app_engine: Engine, table: str) -> None:
    """T-1: the running app can never modify published knowledge."""
    column = _first_column(app_engine, table)
    for statement in (
        f"INSERT INTO marocassist.{table} DEFAULT VALUES",
        f"UPDATE marocassist.{table} SET {column} = {column}",
        f"DELETE FROM marocassist.{table}",
        f"TRUNCATE marocassist.{table}",
    ):
        with app_engine.connect() as conn, pytest.raises(ProgrammingError) as error:
            conn.execute(sa.text(statement))
        assert "permission denied" in str(error.value), statement


def test_application_role_can_read_global_knowledge(app_engine: Engine) -> None:
    with app_engine.connect() as conn:
        for table in GLOBAL_TABLES:
            conn.execute(sa.text(f"SELECT 1 FROM marocassist.{table} LIMIT 1"))


def test_global_knowledge_has_no_tenant_or_user_columns(admin: Engine) -> None:
    """T-3: no tenant or user column in global tables, and no reference to core."""
    with admin.connect() as conn:
        columns = conn.execute(
            sa.text(
                "SELECT table_name, column_name FROM information_schema.columns "
                "WHERE table_schema = 'marocassist' AND table_name = ANY(:t)"
            ),
            {"t": list(GLOBAL_TABLES)},
        ).all()
        core_refs = conn.execute(
            sa.text(
                "SELECT conrelid::regclass::text FROM pg_constraint "
                "WHERE contype = 'f' AND confrelid::regclass::text LIKE 'core.%' "
                "AND conrelid::regclass::text = ANY(:t)"
            ),
            {"t": [f"marocassist.{t}" for t in GLOBAL_TABLES]},
        ).all()
    assert {t for t, _ in columns} == set(GLOBAL_TABLES)
    suspicious = [
        (t, c)
        for t, c in columns
        if c in {"tenant_id", "user_id", "published_by", "author", "approver", "email"}
        or c.endswith("_user_id")
    ]
    assert suspicious == []
    assert core_refs == []


def test_reports_table_has_forced_row_level_security(admin: Engine) -> None:
    with admin.connect() as conn:
        enabled, forced = conn.execute(
            sa.text(
                "SELECT relrowsecurity, relforcerowsecurity FROM pg_class "
                "WHERE oid = 'marocassist.knowledge_reports'::regclass"
            )
        ).one()
    assert enabled
    assert forced


def test_search_function_is_executable_only_by_the_app_role(admin: Engine) -> None:
    app_role = os.environ["APP_DB_USER"]
    with admin.connect() as conn:
        public, app = conn.execute(
            sa.text(
                "SELECT has_function_privilege('public', p.oid, 'EXECUTE'),"
                " has_function_privilege(:role, p.oid, 'EXECUTE')"
                " FROM pg_proc p WHERE p.proname = 'knowledge_search'"
                " AND p.pronamespace = 'marocassist'::regnamespace"
            ),
            {"role": app_role},
        ).one()
    assert app is True
    assert public is False


# --- Normalisation ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("\u00c9tat Civil", "etat civil"),
        ("Overlijdensakte \u00c9\u00c8", "overlijdensakte ee"),
        # Diacritics (fatha, shadda) and tatweel removed.
        ("\u062c\u064e\u0648\u0651\u0627\u0640\u0632", "\u062c\u0648\u0627\u0632"),
        # Alef variants unified; teh marbuta -> heh; alef maksura -> yeh.
        ("\u0623\u0625\u0622\u0671", "\u0627\u0627\u0627\u0627"),
        ("\u0628\u0637\u0627\u0642\u0629", "\u0628\u0637\u0627\u0642\u0647"),
        ("\u0645\u0635\u0637\u0641\u0649", "\u0645\u0635\u0637\u0641\u064a"),
        # Arabic-Indic and Eastern Arabic-Indic digits.
        ("\u0663\u0660\u0660 / \u06f2\u06f0", "300 / 20"),
    ],
)
def test_normaliser(app_engine: Engine, raw: str, expected: str) -> None:
    with app_engine.connect() as conn:
        value = conn.execute(sa.text("SELECT marocassist.kn_normalise(:t)"), {"t": raw})
        assert value.scalar_one() == expected


def test_normaliser_functions_are_immutable_with_a_fixed_search_path(admin: Engine) -> None:
    """P3-S5: generated columns need IMMUTABLE wrappers with a pinned search_path."""
    with admin.connect() as conn:
        rows = conn.execute(
            sa.text(
                "SELECT p.proname, p.provolatile, p.proconfig FROM pg_proc p "
                "WHERE p.pronamespace = 'marocassist'::regnamespace "
                "AND p.proname LIKE 'kn\\_%'"
            )
        ).all()
    assert {r.proname for r in rows} == {
        "kn_unaccent",
        "kn_normalise_arabic",
        "kn_normalise",
        "kn_config",
        "kn_join",
        "kn_tsv",
    }
    for row in rows:
        assert row.provolatile == "i", row.proname
        assert row.proconfig == ["search_path=pg_catalog"], row.proname


# --- knowledge_search() ------------------------------------------------------------------


PASSPORT_NL = (
    "Paspoort aanvragen",
    ["Een nieuw Marokkaans paspoort vraagt u aan bij het consulaat.", "Neem uw CNIE mee."],
)
PASSPORT_FR = (
    "Demande de passeport",
    ["La demande de passeport se fait au consulat.", "Apportez votre acte d'\u00e9tat civil."],
)
# "Passport" in Arabic, in the text with a plain alef and without diacritics.
PASSPORT_AR = (
    "\u062c\u0648\u0627\u0632 \u0627\u0644\u0633\u0641\u0631",
    ["\u0637\u0644\u0628 \u062c\u0648\u0627\u0632 \u0627\u0644\u0633\u0641\u0631"],
)


def test_search_finds_items_per_language(
    corpus: tuple[Corpus, Connection], app_engine: Engine
) -> None:
    c, conn = corpus
    item = c.item(conn, "passport", {"nl": PASSPORT_NL, "fr": PASSPORT_FR, "ar": PASSPORT_AR})
    conn.commit()

    assert _ids(_search(app_engine, "paspoort aanvragen", ["nl"]), c.p)[0] == item
    # Stemming plus unaccent: a query without accents finds the accented text.
    fr = _search(app_engine, "etat civil", ["fr"])
    assert item in _ids(fr, c.p)
    assert {r.lang for r in fr if r.item_id == item} == {"fr"}
    # Arabic: the query has diacritics and a hamza on the alef; the text has neither.
    query_ar = "\u062c\u064e\u0648\u064e\u0627\u0632 \u0623\u0644\u0633\u0651\u0641\u0631"
    assert item in _ids(_search(app_engine, query_ar, ["ar"]), c.p)


def test_search_filters_status_language_country_consulate_and_kind(
    corpus: tuple[Corpus, Connection], app_engine: Engine
) -> None:
    c, conn = corpus
    withdrawn = c.item(conn, "gone", {"nl": PASSPORT_NL}, status="withdrawn")
    pending = c.item(conn, "pending", {"nl": PASSPORT_NL}, lang_status="pending_review")
    utrecht = c.item(conn, "utrecht", {"nl": PASSPORT_NL}, consulates=["nl-utrecht"])
    belgium = c.item(conn, "be", {"nl": PASSPORT_NL}, country=["BE"])
    faq = c.item(conn, "faq", {"nl": PASSPORT_NL}, kind="faq")
    conn.commit()

    found = set(_ids(_search(app_engine, "paspoort", ["nl"]), c.p))
    assert found == {utrecht, faq}
    assert withdrawn not in found
    assert pending not in found
    assert _ids(_search(app_engine, "paspoort", ["fr"]), c.p) == []

    # A consulate filter keeps unscoped items and items for that consulate only.
    rotterdam = set(_ids(_search(app_engine, "paspoort", ["nl"], consulate="nl-rotterdam"), c.p))
    assert rotterdam == {faq}
    in_utrecht = set(_ids(_search(app_engine, "paspoort", ["nl"], consulate="nl-utrecht"), c.p))
    assert in_utrecht == {utrecht, faq}

    assert set(_ids(_search(app_engine, "paspoort", ["nl"], kinds=["faq"]), c.p)) == {faq}
    assert set(_ids(_search(app_engine, "paspoort", ["nl"], country="BE"), c.p)) == {belgium}


def test_expiry_is_computed_at_read_time_and_ranked_lower(
    corpus: tuple[Corpus, Connection], app_engine: Engine
) -> None:
    c, conn = corpus
    fresh = c.item(conn, "fresh", {"nl": PASSPORT_NL})
    stale = c.item(conn, "stale", {"nl": PASSPORT_NL}, review_due=TODAY - timedelta(days=1))
    conn.commit()

    rows = _search(app_engine, "paspoort aanvragen", ["nl"])
    best = {}
    for r in rows:
        if r.item_id in {fresh, stale}:
            best.setdefault(r.item_id, r)
    assert best[stale].status == "expired"
    assert best[fresh].status == "published"
    assert best[stale].rank < best[fresh].rank


def test_search_caps_results_and_chunks_per_item(
    corpus: tuple[Corpus, Connection], app_engine: Engine
) -> None:
    """T-6: at most 6 results and 2 chunks per item, whatever the caller asks."""
    c, conn = corpus
    many_chunks = ("Paspoort", [f"Paspoort stap {n} bij het consulaat." for n in range(5)])
    for n in range(8):
        c.item(conn, f"bulk{n}", {"nl": many_chunks})
    conn.commit()

    rows = _search(app_engine, "paspoort consulaat", ["nl"], limit=1000)
    assert len(rows) == 6
    per_item: dict[str, int] = {}
    for r in rows:
        per_item[r.item_id] = per_item.get(r.item_id, 0) + 1
    assert max(per_item.values()) <= 2
    assert len(_search(app_engine, "paspoort", ["nl"], limit=-5)) == 1


@pytest.mark.parametrize(
    "query",
    [
        "",
        "   ",
        '"',
        "-",
        "or or or",
        "paspoort & | ! ( ) :* <-> \\",
        "'; DROP TABLE marocassist.knowledge_items; --",
        "a" * 10_000,
        "\u202ex\u2066y\u200b",
    ],
)
def test_hostile_or_empty_queries_do_not_error(app_engine: Engine, query: str) -> None:
    """T-5: websearch_to_tsquery never raises on raw input."""
    rows = _search(app_engine, query, ["nl", "fr", "ar", "en"])
    assert len(rows) <= 6


def test_nul_in_a_query_is_refused_by_the_driver(app_engine: Engine) -> None:
    with pytest.raises((DBAPIError, ValueError)):
        _search(app_engine, "pas\u0000poort", ["nl"])


# --- Reports: RLS, grants, purge -------------------------------------------------------


def _tenant() -> uuid.UUID:
    from saas_os.core.identity import get_or_create_user_for_external_identity

    from marocassist.accounts.provisioning import ensure_personal_workspace

    user = get_or_create_user_for_external_identity(
        "http://zitadel.localhost:8081", f"test-{uuid.uuid4().hex}"
    )
    tenant_id, _created = ensure_personal_workspace(user.id)
    return tenant_id


def _report(tenant_id: uuid.UUID, reason: str = "outdated") -> None:
    from saas_os.infra.db import tenant_session_scope

    from marocassist.knowledge.models import KnowledgeReport

    with tenant_session_scope(tenant_id) as session:
        session.add(
            KnowledgeReport(
                report_id=uuid.uuid4(), tenant_id=tenant_id, item_id="test.item", reason_code=reason
            )
        )


def test_reports_are_isolated_per_tenant_and_purged(app_engine: Engine) -> None:
    from saas_os.infra.db import select, tenant_session_scope

    from marocassist.knowledge.models import KnowledgeReport
    from marocassist.purge import KNOWLEDGE_PURGE_PARTICIPANT

    tenant_a, tenant_b = _tenant(), _tenant()
    _report(tenant_a)
    _report(tenant_b)

    # Deliberately no tenant predicate: Row-Level Security alone decides.
    with tenant_session_scope(tenant_a) as session:
        seen = set(session.execute(select(KnowledgeReport.tenant_id)).scalars().all())
    assert seen == {tenant_a}

    with app_engine.connect() as conn, pytest.raises(ProgrammingError):
        conn.execute(sa.text("UPDATE marocassist.knowledge_reports SET reason_code = 'other'"))

    KNOWLEDGE_PURGE_PARTICIPANT.purge_tenant_data(tenant_a)
    KNOWLEDGE_PURGE_PARTICIPANT.purge_tenant_data(tenant_a)  # idempotent
    with tenant_session_scope(tenant_a) as session:
        assert session.execute(select(KnowledgeReport.report_id)).scalars().all() == []
    with tenant_session_scope(tenant_b) as session:
        assert len(session.execute(select(KnowledgeReport.report_id)).scalars().all()) == 1
    KNOWLEDGE_PURGE_PARTICIPANT.purge_tenant_data(tenant_b)


def test_invalid_report_reason_is_rejected() -> None:
    with pytest.raises(IntegrityError):
        _report(_tenant(), reason="spam")


# --- Migration round trip ------------------------------------------------------------


def test_knowledge_migration_downgrades_and_upgrades_again() -> None:
    from pathlib import Path

    from alembic import command
    from alembic.config import Config

    import marocassist.migrate as migrate_module

    config = Config()
    config.set_main_option(
        "script_location", str(Path(migrate_module.__file__).resolve().parent / "migrations")
    )
    command.downgrade(config, "0002_marocassist_profile")
    command.upgrade(config, "head")
