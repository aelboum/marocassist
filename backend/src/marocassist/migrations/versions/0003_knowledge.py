"""knowledge: global knowledge store, search function and tenant reports (Phase 3)

Revision ID: 0003_marocassist_knowledge
Revises: 0002_marocassist_profile
Create Date: 2026-11-21 00:00:00.000000

Design: docs/phase-3/KNOWLEDGE_SEARCH_ARCHITECTURE.md sections 3, 4 and 6,
docs/phase-3/CONTENT_RIGHTS_AND_PROVENANCE.md sections 2-5, ADR-0007.

Two separate stores:

1. **Global knowledge** (`knowledge_*`, `consulates`, `consulate_*`): no
   `tenant_id`, no user ids, no RLS. The application role gets `SELECT`
   only; rows are written by the publishing loader under the migrations
   role (security review T-1). Editorial-only fields (four-eyes author and
   approver, notes, the publishing editor) are deliberately **not** stored
   here: they stay in the content files and in the audit row the loader
   writes in the editorial tenant (T-3: no user columns in global tables).
2. **Tenant side**: `knowledge_reports` ("report outdated") and
   `knowledge_review_reports` (the daily editor review report, written only
   in the editorial tenant), each with a non-null `tenant_id`, forced RLS
   through `tenant_rls_statements`, and a purge participant. They reference
   knowledge only by id, without a foreign key, so the loader can withdraw
   or remove an item without touching tenant rows.
3. **Anonymous aggregate**: `knowledge_report_counts`, one counter per item,
   reason and day, with no tenant or user column. It is how the daily
   review job learns about user reports without reading across tenants:
   each new report bumps its counter. The application role may insert and
   update it (and nothing else global).

Search: `pg_trgm` and `unaccent` (PostgreSQL contrib, trusted extensions).
`unaccent()` is only STABLE, so generated columns use IMMUTABLE wrappers
that pin the dictionary schema-qualified and fix `search_path` (P3-S5).
`knowledge_search()` takes typed parameters and uses `websearch_to_tsquery`
only (T-5); it caps the query length and the result count itself (T-6).
The per-statement timeout is set by the caller (`knowledge.fts`, with
SaaS-OS `set_local_statement_timeout`), because a `SET` on the function
does not bound the statement that calls it.

Downgrade drops everything this revision created except the two
extensions, which other objects in the database may use.
"""

import os
import re
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from saas_os.infra.db.rls import tenant_rls_statements
from sqlalchemy.dialects import postgresql

revision: str = "0003_marocassist_knowledge"
down_revision: str | Sequence[str] | None = "0002_marocassist_profile"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SCHEMA = "marocassist"
_DEFAULT_APP_ROLE = "saas_os_app"

# Global tables, in dependency order (created in this order, dropped in reverse).
GLOBAL_TABLES: tuple[str, ...] = (
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
TENANT_TABLES: tuple[str, ...] = ("knowledge_reports", "knowledge_review_reports")
AGGREGATE_TABLES: tuple[str, ...] = ("knowledge_report_counts",)

# Hard caps enforced inside knowledge_search() (security review T-6).
# The query is the user's text (capped at 256 characters by
# knowledge.normalise) plus its term expansions.
MAX_QUERY_CHARS = 1024
MAX_RESULTS = 6
MAX_CHUNKS_PER_ITEM = 2
MAX_EXPANSION_WORDS = 12
MAX_EXPANSIONS = 64

_LANGS = ("nl", "fr", "ar", "en")
_SCOPE_RE = r"^(global|country:[A-Z]{2}|consulate:[a-z0-9-]{2,32}|region:[a-z0-9-]{2,32})$"
_ID_RE = r"^[a-z0-9][a-z0-9.-]{1,79}$"
_CONSULATE_RE = r"^[a-z0-9-]{2,32}$"
_SEARCH_SIGNATURE = "text, text[], text, text, text[], integer"
_EXPAND_SIGNATURE = "text[], text[]"
# Catalogue reads (WP D) return JSON documents, so the application reads
# text arrays and JSONB without ORM column types SaaS-OS does not provide.
MAX_CATALOGUE_ITEMS = 20
MAX_FACT_ROWS = 50
CATALOGUE_FUNCTIONS: tuple[str, ...] = (
    "knowledge_items(text[])",
    "knowledge_facts(text)",
    "knowledge_consulates(text)",
    "knowledge_review_snapshot(date)",
)
MAX_REVIEW_ROWS = 2000


def arabic_translate_args() -> tuple[str, str]:
    """`translate(text, from, to)` arguments for the Arabic normaliser
    (search architecture section 4.1). Built from code points so this file
    stays ASCII and no bidi character hides in the source.

    Mapped: alef with hamza above/below, alef with madda, alef wasla -> alef;
    teh marbuta -> heh; alef maksura -> yeh; Arabic-Indic and Eastern
    Arabic-Indic digits -> ASCII. Deleted (characters past the end of `to`):
    tashkeel U+064B-U+0652, superscript alef U+0670, tatweel U+0640.
    """
    alef, heh, yeh = chr(0x0627), chr(0x0647), chr(0x064A)
    mapped_from = "".join(chr(c) for c in (0x0623, 0x0625, 0x0622, 0x0671, 0x0629, 0x0649))
    mapped_to = alef * 4 + heh + yeh
    digits_from = "".join(chr(c) for c in range(0x0660, 0x066A)) + "".join(
        chr(c) for c in range(0x06F0, 0x06FA)
    )
    digits_to = "0123456789" * 2
    deleted = "".join(chr(c) for c in range(0x064B, 0x0653)) + chr(0x0670) + chr(0x0640)
    return mapped_from + digits_from + deleted, mapped_to + digits_to


def _app_role() -> str:
    role = os.environ.get("APP_DB_USER", _DEFAULT_APP_ROLE)
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", role):
        raise ValueError("APP_DB_USER must be a plain SQL identifier")
    return role


def _in(column: str, values: Sequence[str]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def _functions() -> list[str]:
    from_chars, to_chars = arabic_translate_args()
    s = _SCHEMA
    return [
        f"""
        CREATE FUNCTION {s}.kn_unaccent(t text) RETURNS text
        LANGUAGE sql IMMUTABLE PARALLEL SAFE STRICT
        SET search_path = pg_catalog
        RETURN public.unaccent('public.unaccent'::regdictionary, t)
        """,
        f"""
        CREATE FUNCTION {s}.kn_normalise_arabic(t text) RETURNS text
        LANGUAGE sql IMMUTABLE PARALLEL SAFE STRICT
        SET search_path = pg_catalog
        RETURN pg_catalog.translate(t, '{from_chars}', '{to_chars}')
        """,
        # The one normaliser, used on both sides (index and query).
        f"""
        CREATE FUNCTION {s}.kn_normalise(t text) RETURNS text
        LANGUAGE sql IMMUTABLE PARALLEL SAFE STRICT
        SET search_path = pg_catalog
        RETURN pg_catalog.lower({s}.kn_unaccent({s}.kn_normalise_arabic(t)))
        """,
        f"""
        CREATE FUNCTION {s}.kn_config(lang text) RETURNS regconfig
        LANGUAGE sql IMMUTABLE PARALLEL SAFE STRICT
        SET search_path = pg_catalog
        RETURN CASE lang
            WHEN 'nl' THEN 'pg_catalog.dutch'::regconfig
            WHEN 'fr' THEN 'pg_catalog.french'::regconfig
            WHEN 'en' THEN 'pg_catalog.english'::regconfig
            WHEN 'ar' THEN 'pg_catalog.arabic'::regconfig
            ELSE 'pg_catalog.simple'::regconfig
        END
        """,
        f"""
        CREATE FUNCTION {s}.kn_join(words text[]) RETURNS text
        LANGUAGE sql IMMUTABLE PARALLEL SAFE
        SET search_path = pg_catalog
        RETURN coalesce(pg_catalog.array_to_string(words, ' '), '')
        """,
        # Weighted document vector: title and keywords A, body D.
        f"""
        CREATE FUNCTION {s}.kn_tsv(
            cfg regconfig, title text, keywords text[], body text
        ) RETURNS tsvector
        LANGUAGE sql IMMUTABLE PARALLEL SAFE
        SET search_path = pg_catalog
        RETURN
            pg_catalog.setweight(pg_catalog.to_tsvector(
                cfg, {s}.kn_normalise(coalesce(title, ''))), 'A')
            || pg_catalog.setweight(pg_catalog.to_tsvector(
                cfg, {s}.kn_normalise({s}.kn_join(keywords))), 'A')
            || pg_catalog.setweight(pg_catalog.to_tsvector(
                cfg, {s}.kn_normalise(coalesce(body, ''))), 'D')
        """,
    ]


def _search_function() -> str:
    """Chunks match on their own heading and body, or through their item's
    title and keywords (`knowledge_item_texts.match_text`), so a query that
    only names the item still finds it. `source_rank` is the best rank of the
    item's cited sources: 1 official or consulate, 2 government, 3 anything
    else or uncited."""
    s = _SCHEMA
    return f"""
    CREATE FUNCTION {s}.knowledge_search(
        p_query text,
        p_langs text[],
        p_country text,
        p_consulate text DEFAULT NULL,
        p_kinds text[] DEFAULT NULL,
        p_limit integer DEFAULT {MAX_RESULTS}
    )
    RETURNS TABLE (
        item_id text,
        lang text,
        ordinal integer,
        heading text,
        kind text,
        status text,
        review_due_at date,
        source_rank integer,
        rank real,
        body text
    )
    LANGUAGE sql STABLE PARALLEL SAFE
    SET search_path = pg_catalog
    AS $fn$
        WITH q AS (
            SELECT {s}.kn_normalise(pg_catalog.left(p_query, {MAX_QUERY_CHARS})) AS text
        ),
        candidates AS (
            SELECT
                c.item_id, c.lang, c.ordinal, c.heading, c.body, i.kind,
                CASE WHEN i.status = 'published' AND i.review_due_at < CURRENT_DATE
                     THEN 'expired' ELSE i.status END AS status,
                i.review_due_at,
                c.tsv, c.tsv_simple,
                pg_catalog.to_tsvector({s}.kn_config(c.lang), t.match_text) AS title_tsv,
                pg_catalog.to_tsvector('pg_catalog.simple', t.match_text) AS title_simple,
                pg_catalog.websearch_to_tsquery({s}.kn_config(c.lang), q.text) AS tq,
                pg_catalog.websearch_to_tsquery('pg_catalog.simple', q.text) AS sq
            FROM {s}.knowledge_chunks c
            JOIN {s}.knowledge_item_texts t ON t.item_id = c.item_id AND t.lang = c.lang
            JOIN {s}.knowledge_items i ON i.item_id = c.item_id
            CROSS JOIN q
            WHERE pg_catalog.length(q.text) > 0
              AND c.lang = ANY (p_langs)
              AND t.lang_status = 'published'
              AND i.status IN ('published', 'expired')
              AND p_country = ANY (i.country_scope)
              AND (p_consulate IS NULL
                   OR pg_catalog.cardinality(i.consulate_scope) = 0
                   OR p_consulate = ANY (i.consulate_scope))
              AND (p_kinds IS NULL OR i.kind = ANY (p_kinds))
        ),
        hits AS (
            SELECT x.item_id, x.lang, x.ordinal, x.heading, x.body, x.kind, x.status,
                   x.review_due_at,
                   (pg_catalog.ts_rank_cd(x.tsv, x.tq)
                    + 0.5 * pg_catalog.ts_rank_cd(x.tsv_simple, x.sq))::real AS chunk_rank,
                   (pg_catalog.ts_rank_cd(x.title_tsv, x.tq)
                    + 0.5 * pg_catalog.ts_rank_cd(x.title_simple, x.sq))::real AS title_rank
            FROM candidates x
            WHERE x.tsv @@ x.tq OR x.tsv_simple @@ x.sq
               OR x.title_tsv @@ x.tq OR x.title_simple @@ x.sq
        ),
        ranked AS (
            SELECT h.*,
                   coalesce((
                       SELECT pg_catalog.min(CASE
                           WHEN src.source_type IN ('official', 'consulate') THEN 1
                           WHEN src.source_type = 'government' THEN 2
                           ELSE 3 END)
                       FROM {s}.knowledge_citations ci
                       JOIN {s}.knowledge_sources src ON src.source_id = ci.source_id
                       WHERE ci.item_id = h.item_id
                   ), 3) AS source_rank,
                   ((h.chunk_rank + h.title_rank)
                    * CASE WHEN h.status = 'published' THEN 1.0 ELSE 0.5 END)::real
                       AS weighted_rank,
                   pg_catalog.row_number() OVER (
                       PARTITION BY h.item_id
                       ORDER BY h.chunk_rank DESC, h.lang, h.ordinal) AS per_item
            FROM hits h
        )
        SELECT r.item_id, r.lang, r.ordinal, r.heading, r.kind, r.status,
               r.review_due_at, r.source_rank, r.weighted_rank, r.body
        FROM ranked r
        WHERE r.per_item <= {MAX_CHUNKS_PER_ITEM}
        ORDER BY r.weighted_rank DESC, r.item_id, r.lang, r.ordinal
        LIMIT least(greatest(coalesce(p_limit, 1), 1), {MAX_RESULTS})
    $fn$
    """


def _expand_terms_function() -> str:
    """Term expansion (search architecture section 4): for each query word,
    the other terms sharing a `canonical_key` with a term that matches the
    word exactly, or by trigram similarity of at least 0.4 for words of four
    or more characters. Only terms in the query languages or Darija (`ary`)
    are returned. Input and output are capped like the search itself."""
    s = _SCHEMA
    return f"""
    CREATE FUNCTION {s}.knowledge_expand_terms(p_words text[], p_langs text[])
    RETURNS TABLE (word text, term text)
    LANGUAGE sql STABLE PARALLEL SAFE
    SET search_path = pg_catalog
    AS $fn$
        WITH w AS (
            SELECT DISTINCT x AS word, {s}.kn_normalise(x) AS norm
            FROM pg_catalog.unnest(p_words[1:{MAX_EXPANSION_WORDS}]) AS x
            WHERE pg_catalog.length(x) BETWEEN 2 AND 60
        ),
        seeds AS (
            SELECT DISTINCT w.word, w.norm, t.canonical_key
            FROM w
            JOIN {s}.knowledge_terms t
              ON t.normalised = w.norm
              OR (pg_catalog.length(w.norm) >= 4
                  AND public.similarity(t.normalised, w.norm) >= 0.4)
        )
        SELECT DISTINCT e.word, t.normalised
        FROM seeds e
        JOIN {s}.knowledge_terms t ON t.canonical_key = e.canonical_key
        WHERE (t.lang = ANY (p_langs) OR t.lang = 'ary')
          AND t.normalised <> e.norm
        ORDER BY e.word, t.normalised
        LIMIT {MAX_EXPANSIONS}
    $fn$
    """


def _source_json(alias: str) -> str:
    """The source-card fields of a `knowledge_sources` row. Editorial-only
    fields (licence evidence, content hash) are not returned."""
    return f"""jsonb_build_object(
        'source_id', {alias}.source_id, 'title', {alias}.title,
        'publisher', {alias}.publisher, 'source_type', {alias}.source_type,
        'official_url', {alias}.official_url, 'geo_scope', {alias}.geo_scope,
        'language', {alias}.language, 'verified_at', {alias}.verified_at,
        'review_due_at', {alias}.review_due_at, 'valid_until', {alias}.valid_until,
        'status', {alias}.status, 'allowed_use', to_jsonb({alias}.allowed_use))"""


def _cited_sources(target: str, key: str) -> str:
    """The sources cited by one item or fact, in citation order, each with
    its locator."""
    s = _SCHEMA
    return f"""coalesce((
        SELECT jsonb_agg({_source_json("src")} || jsonb_build_object('locator', ci.locator)
                         ORDER BY ci.citation_id)
        FROM {s}.knowledge_citations ci
        JOIN {s}.knowledge_sources src ON src.source_id = ci.source_id
        WHERE ci.{target}_id = {key}
    ), '[]'::jsonb)"""


def _catalogue_functions() -> list[str]:
    """Read-only catalogue functions (WP D). Each returns one JSON document
    and caps its own output. Status at read time (expired, conflict) is
    computed by `knowledge.catalogue`, which is unit-tested with a fixed
    date. Withdrawn content comes back only as a stub: a withdrawn item has
    no text, and withdrawn facts and consulate attributes are left out."""
    s = _SCHEMA
    header = "RETURNS jsonb LANGUAGE sql STABLE PARALLEL SAFE SET search_path = pg_catalog"
    return [
        f"""
        CREATE FUNCTION {s}.knowledge_items(p_item_ids text[]) {header}
        AS $fn$
            SELECT coalesce(jsonb_agg(jsonb_build_object(
                'item_id', i.item_id, 'kind', i.kind, 'status', i.status,
                'version', i.version, 'review_due_at', i.review_due_at,
                'superseded_by', i.superseded_by,
                'country_scope', to_jsonb(i.country_scope),
                'consulate_scope', to_jsonb(i.consulate_scope),
                'texts', CASE WHEN i.status = 'withdrawn' THEN '[]'::jsonb ELSE coalesce((
                    SELECT jsonb_agg(jsonb_build_object(
                        'lang', t.lang, 'title', t.title, 'body', t.body,
                        'verified_at', t.verified_at) ORDER BY t.lang)
                    FROM {s}.knowledge_item_texts t
                    WHERE t.item_id = i.item_id AND t.lang_status = 'published'
                ), '[]'::jsonb) END,
                'sources', {_cited_sources("item", "i.item_id")}
            ) ORDER BY i.item_id), '[]'::jsonb)
            FROM {s}.knowledge_items i
            WHERE i.item_id = ANY (p_item_ids[1:{MAX_CATALOGUE_ITEMS}])
        $fn$
        """,
        f"""
        CREATE FUNCTION {s}.knowledge_facts(p_fact_key text) {header}
        AS $fn$
            SELECT coalesce(jsonb_agg(x.doc ORDER BY x.scope, x.fact_id), '[]'::jsonb)
            FROM (
                SELECT f.fact_id, f.scope, jsonb_build_object(
                    'fact_id', f.fact_id, 'fact_key', f.fact_key, 'scope', f.scope,
                    'value', f.value, 'unit', f.unit, 'valid_from', f.valid_from,
                    'valid_until', f.valid_until, 'status', f.status,
                    'verified_at', f.verified_at, 'review_due_at', f.review_due_at,
                    'sources', {_cited_sources("fact", "f.fact_id")}
                ) AS doc
                FROM {s}.knowledge_facts f
                WHERE f.fact_key = p_fact_key AND f.status <> 'withdrawn'
                ORDER BY f.scope, f.fact_id
                LIMIT {MAX_FACT_ROWS}
            ) x
        $fn$
        """,
        # WP F: what the daily editor review report needs. Items, sources and
        # consulate attributes due for review by `p_until` (expired or due
        # soon), and every non-withdrawn fact (conflicts are found in
        # Python). Ids, statuses and dates only; no text.
        f"""
        CREATE FUNCTION {s}.knowledge_review_snapshot(p_until date) {header}
        AS $fn$
            SELECT jsonb_build_object(
                'items', coalesce((
                    SELECT jsonb_agg(x.doc ORDER BY x.due, x.id) FROM (
                        SELECT i.review_due_at AS due, i.item_id AS id, jsonb_build_object(
                            'item_id', i.item_id, 'status', i.status,
                            'review_due_at', i.review_due_at) AS doc
                        FROM {s}.knowledge_items i
                        WHERE i.status <> 'withdrawn' AND i.review_due_at <= p_until
                        ORDER BY i.review_due_at, i.item_id LIMIT {MAX_REVIEW_ROWS}) x
                ), '[]'::jsonb),
                'sources', coalesce((
                    SELECT jsonb_agg(x.doc ORDER BY x.due, x.id) FROM (
                        SELECT src.review_due_at AS due, src.source_id AS id, jsonb_build_object(
                            'source_id', src.source_id, 'status', src.status,
                            'review_due_at', src.review_due_at,
                            'valid_until', src.valid_until) AS doc
                        FROM {s}.knowledge_sources src
                        WHERE src.status <> 'withdrawn'
                          AND (src.review_due_at <= p_until OR src.valid_until <= p_until)
                        ORDER BY src.review_due_at, src.source_id LIMIT {MAX_REVIEW_ROWS}) x
                ), '[]'::jsonb),
                'attributes', coalesce((
                    SELECT jsonb_agg(x.doc ORDER BY x.due, x.id) FROM (
                        SELECT a.review_due_at AS due,
                            a.code || '/' || a.attribute || '/' || a.lang AS id,
                            jsonb_build_object(
                                'code', a.code, 'attribute', a.attribute, 'lang', a.lang,
                                'status', a.status, 'review_due_at', a.review_due_at) AS doc
                        FROM {s}.consulate_attributes a
                        WHERE a.status <> 'withdrawn' AND a.review_due_at <= p_until
                        ORDER BY a.review_due_at, a.code, a.attribute, a.lang
                        LIMIT {MAX_REVIEW_ROWS}) x
                ), '[]'::jsonb),
                'facts', coalesce((
                    SELECT jsonb_agg(x.doc ORDER BY x.id) FROM (
                        SELECT f.fact_id AS id, jsonb_build_object(
                            'fact_id', f.fact_id, 'fact_key', f.fact_key, 'scope', f.scope,
                            'value', f.value, 'unit', f.unit, 'valid_from', f.valid_from,
                            'valid_until', f.valid_until, 'status', f.status,
                            'review_due_at', f.review_due_at) AS doc
                        FROM {s}.knowledge_facts f
                        WHERE f.status <> 'withdrawn'
                        ORDER BY f.fact_id LIMIT {MAX_REVIEW_ROWS}) x
                ), '[]'::jsonb)
            )
        $fn$
        """,
        f"""
        CREATE FUNCTION {s}.knowledge_consulates(p_code text DEFAULT NULL) {header}
        AS $fn$
            SELECT coalesce(jsonb_agg(jsonb_build_object(
                'code', c.code, 'country', c.country, 'kind', c.kind, 'active', c.active,
                'attributes', coalesce((
                    SELECT jsonb_agg(jsonb_build_object(
                        'attribute', a.attribute, 'lang', a.lang, 'value', a.value,
                        'verified_at', a.verified_at, 'review_due_at', a.review_due_at,
                        'status', a.status, 'source', {_source_json("src")}
                    ) ORDER BY a.attribute, a.lang)
                    FROM {s}.consulate_attributes a
                    JOIN {s}.knowledge_sources src ON src.source_id = a.source_id
                    WHERE a.code = c.code AND a.status <> 'withdrawn'
                ), '[]'::jsonb)
            ) ORDER BY c.code), '[]'::jsonb)
            FROM {s}.consulates c
            WHERE p_code IS NULL OR c.code = p_code
        $fn$
        """,
    ]


def _date(name: str, *, nullable: bool = True) -> sa.Column:  # type: ignore[type-arg]
    return sa.Column(name, sa.Date(), nullable=nullable)


def _text_array(name: str, default: str = "{}") -> sa.Column:  # type: ignore[type-arg]
    return sa.Column(
        name,
        postgresql.ARRAY(sa.Text()),
        nullable=False,
        server_default=sa.text(f"'{default}'::text[]"),
    )


def _publication_fk() -> sa.Column:  # type: ignore[type-arg]
    return sa.Column(
        "publication_id",
        sa.Uuid(),
        sa.ForeignKey(f"{_SCHEMA}.knowledge_publications.publication_id"),
        nullable=False,
    )


def _source_fk() -> sa.Column:  # type: ignore[type-arg]
    return sa.Column(
        "source_id",
        sa.String(80),
        sa.ForeignKey(f"{_SCHEMA}.knowledge_sources.source_id"),
        nullable=False,
    )


def _generated(
    name: str,
    type_: sa.types.TypeEngine,  # type: ignore[type-arg]
    expression: str,
) -> sa.Column:  # type: ignore[type-arg]
    return sa.Column(name, type_, sa.Computed(expression, persisted=True))


def _create_publications_and_sources() -> None:
    s = _SCHEMA
    op.create_table(
        "knowledge_publications",
        sa.Column("publication_id", sa.Uuid(), primary_key=True),
        sa.Column("content_version", sa.String(80), nullable=False),
        sa.Column(
            "published_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("item_count", sa.Integer(), nullable=False),
        sa.Column("fact_count", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "content_version ~ '^[A-Za-z0-9._:-]{7,80}$'", name="ck_kn_publications_version"
        ),
        sa.CheckConstraint("item_count >= 0 AND fact_count >= 0", name="ck_kn_publications_counts"),
        schema=s,
    )

    op.create_table(
        "knowledge_sources",
        sa.Column("source_id", sa.String(80), primary_key=True),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("official_url", sa.String(2000), nullable=False),
        sa.Column("publisher", sa.String(200), nullable=False),
        sa.Column("publisher_key", sa.String(40), nullable=False),
        sa.Column("source_type", sa.String(16), nullable=False),
        sa.Column("country", sa.String(2), nullable=False),
        sa.Column("geo_scope", sa.String(64), nullable=False),
        _text_array("consulate_codes"),
        sa.Column("language", sa.String(2), nullable=False),
        _date("consulted_at", nullable=False),
        _date("verified_at"),
        _date("review_due_at", nullable=False),
        _date("valid_until"),
        sa.Column("licence", sa.String(120), nullable=False),
        _text_array("allowed_use"),
        sa.Column("rights_evidence_ref", sa.String(200), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=True),
        sa.CheckConstraint("source_id ~ '^src-[a-z0-9-]{2,76}$'", name="ck_kn_sources_id"),
        sa.CheckConstraint(
            "official_url ~ '^https://[A-Za-z0-9.-]+(/[^[:space:]]*)?$'", name="ck_kn_sources_url"
        ),
        sa.CheckConstraint(
            "publisher_key ~ '^[a-z0-9-]{2,40}$'", name="ck_kn_sources_publisher_key"
        ),
        sa.CheckConstraint(
            _in("source_type", ("official", "government", "consulate", "secondary", "internal")),
            name="ck_kn_sources_type",
        ),
        sa.CheckConstraint("country ~ '^[A-Z]{2}$'", name="ck_kn_sources_country"),
        sa.CheckConstraint(f"geo_scope ~ '{_SCOPE_RE}'", name="ck_kn_sources_scope"),
        sa.CheckConstraint(_in("language", _LANGS), name="ck_kn_sources_language"),
        sa.CheckConstraint(
            "licence ~ '^(unknown|all_rights_reserved|open_licence:[A-Za-z0-9.-]{1,80}"
            "|written_permission:[A-Za-z0-9._/-]{1,80})$'",
            name="ck_kn_sources_licence",
        ),
        # Evidence reference required for anything other than `unknown` (rights doc 2).
        sa.CheckConstraint(
            "licence = 'unknown' OR rights_evidence_ref IS NOT NULL",
            name="ck_kn_sources_rights_evidence",
        ),
        sa.CheckConstraint(
            "allowed_use <@ ARRAY['link', 'cite_fact', 'summary', 'short_quote', 'verbatim',"
            " 'redistribute_document']::text[]",
            name="ck_kn_sources_allowed_use",
        ),
        sa.CheckConstraint(
            _in("status", ("draft", "pending_review", "verified", "expired", "withdrawn")),
            name="ck_kn_sources_status",
        ),
        sa.CheckConstraint(
            "content_hash IS NULL OR content_hash ~ '^[0-9a-f]{64}$'", name="ck_kn_sources_hash"
        ),
        schema=s,
    )


def _create_items() -> None:
    s = _SCHEMA
    op.create_table(
        "knowledge_items",
        sa.Column("item_id", sa.String(80), primary_key=True),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("rights_class", sa.String(2), nullable=False),
        _text_array("country_scope", default="{NL}"),
        _text_array("consulate_scope"),
        _text_array("topic_keys"),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        _date("review_due_at", nullable=False),
        sa.Column(
            "superseded_by",
            sa.String(80),
            sa.ForeignKey(f"{s}.knowledge_items.item_id"),
            nullable=True,
        ),
        _publication_fk(),
        sa.CheckConstraint(f"item_id ~ '{_ID_RE}'", name="ck_kn_items_id"),
        sa.CheckConstraint(
            _in("kind", ("procedure", "explanation", "faq")), name="ck_kn_items_kind"
        ),
        sa.CheckConstraint(
            _in("rights_class", ("R1", "R2", "R3", "R4", "R5", "R6")), name="ck_kn_items_rights"
        ),
        sa.CheckConstraint("cardinality(country_scope) > 0", name="ck_kn_items_country_scope"),
        # `expired` is normally computed at read time; the loader may also set it.
        sa.CheckConstraint(
            _in("status", ("published", "expired", "withdrawn")), name="ck_kn_items_status"
        ),
        sa.CheckConstraint("version >= 1", name="ck_kn_items_version"),
        sa.CheckConstraint(
            "superseded_by IS NULL OR status = 'withdrawn'", name="ck_kn_items_superseded"
        ),
        schema=s,
    )

    op.create_table(
        "knowledge_item_texts",
        sa.Column(
            "item_id",
            sa.String(80),
            sa.ForeignKey(f"{s}.knowledge_items.item_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("lang", sa.String(2), primary_key=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        _text_array("keywords"),
        sa.Column("lang_status", sa.String(16), nullable=False),
        _date("verified_at", nullable=False),
        _generated(
            "tsv",
            postgresql.TSVECTOR(),
            f"{s}.kn_tsv({s}.kn_config(lang), title, keywords, body)",
        ),
        _generated(
            "tsv_simple",
            postgresql.TSVECTOR(),
            f"{s}.kn_tsv('pg_catalog.simple'::regconfig, title, keywords, body)",
        ),
        _generated(
            "match_text", sa.Text(), f"{s}.kn_normalise(title || ' ' || {s}.kn_join(keywords))"
        ),
        sa.CheckConstraint(_in("lang", _LANGS), name="ck_kn_item_texts_lang"),
        sa.CheckConstraint("length(body) BETWEEN 1 AND 20000", name="ck_kn_item_texts_body"),
        sa.CheckConstraint(
            _in("lang_status", ("published", "pending_review")), name="ck_kn_item_texts_status"
        ),
        schema=s,
    )

    op.create_table(
        "knowledge_chunks",
        sa.Column("item_id", sa.String(80), primary_key=True),
        sa.Column("lang", sa.String(2), primary_key=True),
        sa.Column("ordinal", sa.Integer(), primary_key=True),
        sa.Column("heading", sa.String(200), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        _generated(
            "tsv",
            postgresql.TSVECTOR(),
            f"{s}.kn_tsv({s}.kn_config(lang), heading, ARRAY[]::text[], body)",
        ),
        _generated(
            "tsv_simple",
            postgresql.TSVECTOR(),
            f"{s}.kn_tsv('pg_catalog.simple'::regconfig, heading, ARRAY[]::text[], body)",
        ),
        sa.ForeignKeyConstraint(
            ["item_id", "lang"],
            [f"{s}.knowledge_item_texts.item_id", f"{s}.knowledge_item_texts.lang"],
            ondelete="CASCADE",
            name="fk_kn_chunks_text",
        ),
        sa.CheckConstraint("ordinal >= 0", name="ck_kn_chunks_ordinal"),
        # Retrieval unit: 300-800 characters is the loader's target; 1200 is the hard cap.
        sa.CheckConstraint("length(body) BETWEEN 1 AND 1200", name="ck_kn_chunks_body"),
        schema=s,
    )


def _create_facts_citations_terms() -> None:
    s = _SCHEMA
    op.create_table(
        "knowledge_facts",
        sa.Column("fact_id", sa.String(120), primary_key=True),
        sa.Column("fact_key", sa.String(120), nullable=False),
        sa.Column("scope", sa.String(64), nullable=False),
        sa.Column("value", postgresql.JSONB(), nullable=False),
        sa.Column("unit", sa.String(16), nullable=True),
        _date("valid_from", nullable=False),
        _date("valid_until"),
        sa.Column("status", sa.String(16), nullable=False),
        _date("verified_at", nullable=False),
        _date("review_due_at", nullable=False),
        _publication_fk(),
        sa.CheckConstraint("fact_id ~ '^[a-z0-9][a-z0-9._-]{1,119}$'", name="ck_kn_facts_id"),
        sa.CheckConstraint("fact_key ~ '^[a-z0-9_]+(\\.[a-z0-9_]+)+$'", name="ck_kn_facts_key"),
        sa.CheckConstraint(f"scope ~ '{_SCOPE_RE}'", name="ck_kn_facts_scope"),
        sa.CheckConstraint("unit IS NULL OR unit ~ '^[A-Za-z]{1,16}$'", name="ck_kn_facts_unit"),
        sa.CheckConstraint(
            "valid_until IS NULL OR valid_until >= valid_from", name="ck_kn_facts_validity"
        ),
        # `conflict` and `expired` are computed when read (rights doc 5.3).
        sa.CheckConstraint(
            _in("status", ("published", "under_review", "withdrawn")), name="ck_kn_facts_status"
        ),
        schema=s,
    )
    op.create_index("ix_kn_facts_key_scope", "knowledge_facts", ["fact_key", "scope"], schema=s)

    op.create_table(
        "knowledge_citations",
        sa.Column("citation_id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column(
            "item_id",
            sa.String(80),
            sa.ForeignKey(f"{s}.knowledge_items.item_id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "fact_id",
            sa.String(120),
            sa.ForeignKey(f"{s}.knowledge_facts.fact_id", ondelete="CASCADE"),
            nullable=True,
        ),
        _source_fk(),
        sa.Column("locator", sa.String(200), nullable=True),
        sa.CheckConstraint("num_nonnulls(item_id, fact_id) = 1", name="ck_kn_citations_target"),
        schema=s,
    )
    for target in ("item", "fact"):
        op.create_index(
            f"ux_kn_citations_{target}",
            "knowledge_citations",
            [f"{target}_id", "source_id"],
            unique=True,
            schema=s,
            postgresql_where=sa.text(f"{target}_id IS NOT NULL"),
        )

    op.create_table(
        "knowledge_terms",
        sa.Column("term_id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("term", sa.String(120), nullable=False),
        # `ary` = Darija (Moroccan Arabic, ISO 639-3), in Latin or Arabic script.
        sa.Column("lang", sa.String(3), nullable=False),
        _generated("normalised", sa.Text(), f"{s}.kn_normalise(term)"),
        sa.Column("canonical_key", sa.String(120), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.CheckConstraint(_in("lang", (*_LANGS, "ary")), name="ck_kn_terms_lang"),
        sa.CheckConstraint(
            "canonical_key ~ '^[a-z0-9_]+(\\.[a-z0-9_]+)*$'", name="ck_kn_terms_canonical"
        ),
        sa.CheckConstraint(
            _in("kind", ("synonym", "transliteration", "plural", "alias", "abbreviation")),
            name="ck_kn_terms_kind",
        ),
        sa.UniqueConstraint("lang", "term", "canonical_key", "kind", name="uq_kn_terms"),
        schema=s,
    )
    op.create_index("ix_kn_terms_canonical", "knowledge_terms", ["canonical_key"], schema=s)


def _create_consulates() -> None:
    s = _SCHEMA
    attribute_status = _in("status", ("pending_review", "verified", "withdrawn"))
    op.create_table(
        "consulates",
        sa.Column("code", sa.String(32), primary_key=True),
        sa.Column("country", sa.String(2), nullable=False),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.CheckConstraint(f"code ~ '{_CONSULATE_RE}'", name="ck_consulates_code"),
        sa.CheckConstraint("country ~ '^[A-Z]{2}$'", name="ck_consulates_country"),
        sa.CheckConstraint(
            _in("kind", ("consulate_general", "consulate", "embassy")), name="ck_consulates_kind"
        ),
        schema=s,
    )

    op.create_table(
        "consulate_attributes",
        sa.Column(
            "code",
            sa.String(32),
            sa.ForeignKey(f"{s}.consulates.code", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("attribute", sa.String(24), primary_key=True),
        # `und` for attributes that are not language-specific (only names are).
        sa.Column("lang", sa.String(3), primary_key=True, server_default="und"),
        sa.Column("value", postgresql.JSONB(), nullable=False),
        _source_fk(),
        _date("verified_at", nullable=False),
        _date("review_due_at", nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.CheckConstraint(
            _in(
                "attribute",
                ("display_name", "physical_city", "address", "contact", "opening_hours"),
            ),
            name="ck_consulate_attributes_attribute",
        ),
        sa.CheckConstraint(_in("lang", (*_LANGS, "und")), name="ck_consulate_attributes_lang"),
        sa.CheckConstraint(
            "(attribute = 'display_name') = (lang <> 'und')",
            name="ck_consulate_attributes_lang_use",
        ),
        sa.CheckConstraint(attribute_status, name="ck_consulate_attributes_status"),
        schema=s,
    )

    # Empty until an official source is found; never derived (search doc 6).
    op.create_table(
        "consulate_jurisdictions",
        sa.Column(
            "code",
            sa.String(32),
            sa.ForeignKey(f"{s}.consulates.code", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("municipality_code", sa.String(6), primary_key=True),
        _source_fk(),
        _date("verified_at", nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.CheckConstraint(
            "municipality_code ~ '^GM[0-9]{4}$'", name="ck_consulate_jurisdictions_cbs"
        ),
        sa.CheckConstraint(attribute_status, name="ck_consulate_jurisdictions_status"),
        schema=s,
    )


def _create_search_indexes() -> None:
    s = _SCHEMA
    for table in ("knowledge_item_texts", "knowledge_chunks"):
        for column in ("tsv", "tsv_simple"):
            op.execute(f"CREATE INDEX ix_{table}_{column} ON {s}.{table} USING gin ({column})")
    op.execute(
        f"CREATE INDEX ix_knowledge_item_texts_trgm ON {s}.knowledge_item_texts "
        "USING gin (match_text public.gin_trgm_ops)"
    )
    op.execute(
        f"CREATE INDEX ix_knowledge_terms_trgm ON {s}.knowledge_terms "
        "USING gin (normalised public.gin_trgm_ops)"
    )


def _create_tenant_tables() -> None:
    op.create_table(
        "knowledge_reports",
        sa.Column("report_id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("core.tenants.id"), nullable=False),
        # By id only, no foreign key: knowledge never depends on tenant rows.
        sa.Column("item_id", sa.String(80), nullable=False),
        sa.Column("reason_code", sa.String(16), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(f"item_id ~ '{_ID_RE}'", name="ck_kn_reports_item"),
        sa.CheckConstraint(
            _in("reason_code", ("outdated", "incorrect", "broken_link", "other")),
            name="ck_kn_reports_reason",
        ),
        schema=_SCHEMA,
    )
    op.create_index(
        "ix_kn_reports_tenant", "knowledge_reports", ["tenant_id", "created_at"], schema=_SCHEMA
    )
    for statement in tenant_rls_statements("knowledge_reports", schema=_SCHEMA):
        op.execute(statement)


def _create_review_tables() -> None:
    """WP F: the anonymous report counter and the editor review report."""
    op.create_table(
        "knowledge_report_counts",
        sa.Column("item_id", sa.String(80), nullable=False),
        sa.Column("reason_code", sa.String(16), nullable=False),
        _date("day", nullable=False),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("item_id", "reason_code", "day", name="pk_kn_report_counts"),
        sa.CheckConstraint(f"item_id ~ '{_ID_RE}'", name="ck_kn_report_counts_item"),
        sa.CheckConstraint(
            _in("reason_code", ("outdated", "incorrect", "broken_link", "other")),
            name="ck_kn_report_counts_reason",
        ),
        sa.CheckConstraint("count >= 1", name="ck_kn_report_counts_count"),
        schema=_SCHEMA,
    )
    op.create_table(
        "knowledge_review_reports",
        sa.Column("report_id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("core.tenants.id"), nullable=False),
        _date("report_date", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("summary", postgresql.JSONB(), nullable=False),
        sa.UniqueConstraint("tenant_id", "report_date", name="uq_kn_review_reports_day"),
        schema=_SCHEMA,
    )
    for statement in tenant_rls_statements("knowledge_review_reports", schema=_SCHEMA):
        op.execute(statement)


def upgrade() -> None:
    app_role = _app_role()
    # Trusted contrib extensions, pinned to schema `public` so the wrappers
    # can reference them schema-qualified (P3-S5).
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm WITH SCHEMA public")
    op.execute("CREATE EXTENSION IF NOT EXISTS unaccent WITH SCHEMA public")

    for statement in _functions():
        op.execute(statement)
    _create_publications_and_sources()
    _create_items()
    _create_facts_citations_terms()
    _create_consulates()
    _create_search_indexes()
    _create_tenant_tables()
    _create_review_tables()
    op.execute(_search_function())
    op.execute(_expand_terms_function())
    for statement in _catalogue_functions():
        op.execute(statement)

    # T-1: SELECT only on global knowledge, for the application role.
    for table in GLOBAL_TABLES:
        op.execute(f'GRANT SELECT ON {_SCHEMA}.{table} TO "{app_role}"')
    # Reports: created and purged, never edited.
    op.execute(f'GRANT SELECT, INSERT, DELETE ON {_SCHEMA}.knowledge_reports TO "{app_role}"')
    # One review report per day, written once; deleted only by the purge.
    op.execute(
        f'GRANT SELECT, INSERT, DELETE ON {_SCHEMA}.knowledge_review_reports TO "{app_role}"'
    )
    # Anonymous counters: created and incremented, never deleted by the app.
    op.execute(f'GRANT SELECT, INSERT, UPDATE ON {_SCHEMA}.knowledge_report_counts TO "{app_role}"')
    for function in (
        f"{_SCHEMA}.knowledge_search({_SEARCH_SIGNATURE})",
        f"{_SCHEMA}.knowledge_expand_terms({_EXPAND_SIGNATURE})",
        *(f"{_SCHEMA}.{signature}" for signature in CATALOGUE_FUNCTIONS),
    ):
        op.execute(f"REVOKE ALL ON FUNCTION {function} FROM PUBLIC")
        op.execute(f'GRANT EXECUTE ON FUNCTION {function} TO "{app_role}"')


def downgrade() -> None:
    app_role = _app_role()
    s = _SCHEMA
    op.execute(f"DROP FUNCTION IF EXISTS {s}.knowledge_search({_SEARCH_SIGNATURE})")
    op.execute(f"DROP FUNCTION IF EXISTS {s}.knowledge_expand_terms({_EXPAND_SIGNATURE})")
    for signature in CATALOGUE_FUNCTIONS:
        op.execute(f"DROP FUNCTION IF EXISTS {s}.{signature}")
    for table in (*AGGREGATE_TABLES, *TENANT_TABLES, *reversed(GLOBAL_TABLES)):
        op.execute(f'REVOKE ALL ON {s}.{table} FROM "{app_role}"')
        op.drop_table(table, schema=s)
    for function in (
        "kn_tsv(regconfig, text, text[], text)",
        "kn_join(text[])",
        "kn_config(text)",
        "kn_normalise(text)",
        "kn_normalise_arabic(text)",
        "kn_unaccent(text)",
    ):
        op.execute(f"DROP FUNCTION IF EXISTS {s}.{function}")
