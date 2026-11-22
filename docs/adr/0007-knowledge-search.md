# ADR-0007: Knowledge search with PostgreSQL full-text search (D-07)

Status: Accepted as design (owner decision, 2026-11-20), under the conditions in
[Phase 3 architecture report](../phase-3/PHASE3_ARCHITECTURE_REPORT.md) §12–13.
**Implemented** on branch `phase-3` (2026-11-21/22, not yet merged); see
[Implementation](#implementation-phase-3) below and the
[Phase 3 report](../phase-3/PHASE3_REPORT.md).
**Decides:** D-07 in `docs/roadmap/RISKS_AND_DECISIONS.md`.
**Pinned SaaS-OS version:** v0.15.0, `cdede956dd884fc816b234f1b546ce3b983b4efc`.

## Context

MarocAssist needs to search a curated knowledge base: procedures, explanations,
consulate facts and source references. The search must work in NL, FR, AR and
EN. The constraints are: no embeddings, no vector database and no external
search service in the MVP. SaaS-OS tenant isolation, RLS and governance must not
be bypassed.

### What was checked in the pinned SaaS-OS version

| Area | What the pin offers |
|---|---|
| Search | Nothing. `saas_os.infra.db.__all__` has no `func`, no `text` and no `TSVECTOR`. A source grep for `tsvector`, `to_tsquery`, `pg_trgm` and "full text" finds nothing. |
| Database primitives | `select`, `update`, `delete`, `Index`, `JSON`, `Text`, `tenant_session_scope`, `session_scope`, `tenant_rls_statements`, `tenant_context_exclusion_statements`, advisory locks, statement timeout. |
| Tenant exclusion | `tenant_context_exclusion_statements` hides rows from **every** tenant-scoped transaction (ADR-0045 §9b). That is wrong for knowledge, which tenant requests must read. |
| Audit | `record_in_transaction` and `record_system_action_in_transaction`. Both require a `tenant_id`; there is no tenant-less audit table. |
| Jobs | `register_system_job` and `register_tenant_job`. |
| Outbound HTTP | `StrictEgressClient` (public HTTPS only, pinned address, no redirects, bounded). |
| AI | `run_inference` only: text parts with a classification of `none`, `tenant_data` or `sensitive`; roles system, user and assistant; no tools; `response_format` text only. `stream_inference` always refuses. There is no embeddings API. |
| MarocAssist rule | The import-linter contract forbids `sqlalchemy` and `psycopg` outside migrations. |

### What was measured in PostgreSQL 16.15

Measured on the CI image `postgres:16-alpine@sha256:7218…`, 2026-11-20:

- **Text-search configurations:** `arabic`, `dutch`, `english`, `french` and
  `simple` are present.
- **Extensions:** `pg_trgm` 1.6, `unaccent` 1.1, `fuzzystrmatch` and
  `dict_xsyn` are available but not installed. `vector` is **not** available.
- **Dutch:** stems as expected (`paspoorten` → `paspoort`); a plural query
  matches the singular.
- **French:** stems as expected. Accents do **not** match without `unaccent`
  (`état` vs `etat` returns false); with `unaccent` they match.
- **Arabic:**
  - The article ال, diacritics and alef variants (إ/ا) are normalised.
  - Broken plurals are **not** stemmed: جوازات does not match جواز.
  - The stop word في is kept.
- **Trigram (`pg_trgm`):**
  - Transliteration spelling variants score medium (`kafala`/`kefala` 0.40;
    a French typo 0.59).
  - A different name scores 0 (`Casablanca` vs `Dar el Beida`).
  - Arabic with ة vs ه scores low (0.23).

## Options

| Option | Summary | Pros | Cons |
|---|---|---|---|
| 1. SaaS-OS only | Use only what SaaS-OS offers today | No product exception | **Not possible**: SaaS-OS has no FTS. Searching in Python (D-07 option c) does not scale, loses ranking, and loads the whole corpus. |
| 2. Product module, free SQLAlchemy | A product knowledge module imports SQLAlchemy as it likes | Fast | Breaks the database chokepoint and invites drift from SaaS-OS patterns |
| 3. **Combination** | SaaS-OS for sessions, RLS, audit, jobs, egress, inference and permissions. One narrow product module calls one database function defined in a migration. Upstream proposal U-1 retires the exception later. | Reuses SaaS-OS everywhere it can. The exception is one module and one function, and is testable. Ranking logic is versioned SQL that is reviewed. | One documented import-linter exception until U-1 lands |

## Decision

**Option 3.**

1. **Knowledge lives in global tables** in schema `marocassist`. They have no
   `tenant_id` and no RLS. The app role gets `SELECT` only.
   - `tenant_context_exclusion_statements` is not used, because tenant
     requests must read knowledge.
   - Writes happen only through the publishing loader, which runs with the
     migrations role at deploy time (see [implementation plan](../phase-3/PHASE3_IMPLEMENTATION_PLAN.md)). The
     running app therefore has no write privilege on knowledge.
2. **Generated `tsvector` columns** are stored per language, with GIN indexes:
   - `dutch`, `french` and `english`: `unaccent` is applied before stemming.
     That needs an `IMMUTABLE` wrapper function, because `unaccent` itself is
     only `STABLE`.
   - `arabic`: an Arabic normaliser is applied first (unify alef forms, map ة
     to ه and ى to ي, remove tatweel and diacritics), then the `arabic`
     configuration.
   - `simple`: a language-neutral fallback, used for codes, form numbers and
     names.
3. **Trigram indexes** (`gin_trgm_ops`) cover titles, keywords and alias terms
   only, not full bodies. They handle transliteration and typo variants.
4. **A synonym and alias table**, maintained by editors, covers what stemming
   and trigrams cannot: Arabic broken plurals, transliterations,
   French/Dutch/Darija variants and city aliases. Queries are expanded with
   these terms before searching. `dict_xsyn` is not used, because a table is
   reviewable, versioned and audited.
5. **One SQL function** created in a migration,
   `marocassist.knowledge_search(query text, lang text, filters jsonb, k int)`.
   - It is `SECURITY INVOKER` and `STABLE`, sets its own statement timeout,
     uses `websearch_to_tsquery`, and caps `k`.
   - It returns ids and scores only, never full text.
6. **One product module, `marocassist.knowledge.fts`**, is the only non-migration
   code allowed to import `sqlalchemy`, and only `sqlalchemy.func` to call that
   function.
   - An import-linter contract and an AST test enforce this. Every other
     knowledge read uses `saas_os.infra.db.select`.
   - Queries are always parameterised; there is no string-built SQL.
7. **Upstream:** proposal U-1 (export FTS primitives from `saas_os.infra.db`)
   goes to SaaS-OS. When it lands, the exception in point 6 is removed.

## Consequences

- No new infrastructure: same PostgreSQL, with two extensions (`pg_trgm`,
  `unaccent`) created in a migration. The migrations role can create them on the
  Compose and CI images. **In production this must be checked against the
  hosting provider.**
- Recall depends on editor-maintained synonyms and keywords. The golden-set
  evaluation ([search architecture](../phase-3/KNOWLEDGE_SEARCH_ARCHITECTURE.md) §8) measures it.
- The exception is explicit, small and has a planned exit (U-1).

## Implementation (Phase 3)

What was built, and where it differs from the decision above. Everything
runs on fixture content only.

### Database (migration `0003_knowledge`)

- Extensions `pg_trgm` and `unaccent`, created by the migration.
- Immutable helper functions `kn_unaccent`, `kn_normalise_arabic`,
  `kn_normalise`, `kn_config` and `kn_tsv`. Each sets
  `search_path = pg_catalog` and calls schema-qualified names such as
  `public.unaccent`, which closes P3-S5.
- Global tables:
  - `knowledge_publications`, `knowledge_sources`, `knowledge_items`,
    `knowledge_item_texts`, `knowledge_chunks`, `knowledge_facts`,
    `knowledge_citations` and `knowledge_terms`;
  - `consulates`, `consulate_attributes` and `consulate_jurisdictions`.

  They have no tenant or user columns (schema test, T-3), and editorial fields (`review`,
  `notes`, `owner_reviewer`) are never written to them.
- Per-language generated `tsvector` columns with GIN indexes, and trigram
  indexes on titles, keywords and terms.
- **Six SQL functions instead of one.** All are `SECURITY INVOKER`, `STABLE`,
  and have a pinned `search_path`. `EXECUTE` is revoked from `PUBLIC`.
  - `knowledge_search(query, lang, filters, k)`: ids, scores, chunk body
    and source rank. It also matches item titles and keywords, and caps `k`
    at 6.
  - `knowledge_expand_terms(words, langs)`: synonyms, plurals and
    transliterations that share a canonical key, by exact match or trigram
    similarity ≥ 0.4.
  - `knowledge_items`, `knowledge_facts` and `knowledge_consulates`: JSON
    documents for the catalogue reads.
  - `knowledge_review_snapshot()`: ids and dates for the editors' daily
    report.
- Tenant tables:
  - `knowledge_reports` ("report outdated");
  - `knowledge_review_reports` (the daily report, stored in the editorial
    tenant).

  Both use forced RLS through `tenant_rls_statements` and have a purge
  participant.
- A global anonymous counter, `knowledge_report_counts` (item, reason, day,
  count; no tenant column). It lets the daily job read report totals without
  reading tenant rows.
- Grants: the app role has `SELECT` on global knowledge. Its only global
  write is `INSERT` and `UPDATE` on the counter.

### Python modules (`marocassist.knowledge`)

| Module | Role |
|---|---|
| `fts` | The one runtime `sqlalchemy` import (`func` only, AST test); calls the SQL functions under the app role with a 200 ms statement timeout |
| `normalise` | Query cap (256 characters), NFKC, removal of control and bidi characters, Arabic folding identical to the SQL normaliser (tested), language detection, and a safe `websearch_to_tsquery` string |
| `retrieval` | Two passes: first all words, then any word ranked after full matches. Score = rank × status × freshness × source rank. At most 2 chunks per item and 6 in all. |
| `catalogue` | Item, fact and consulate reads. Status (current, expired, conflict, under review, withdrawn) is computed at read time with an injectable date. |
| `routes` | `/v1/tenants/{tenant_id}/knowledge/...` behind `require_permission` (`marocassist.knowledge:read`, `:report`) |
| `content`, `validate`, `sanitise`, `pii`, `domains` | Bundle format and every publishing check (see the [rights policy](../phase-3/CONTENT_RIGHTS_AND_PROVENANCE.md) §11) |
| `loader` | The only writer of knowledge (see below) |
| `review`, `reports` | Daily editor report (SaaS-OS system job) and "report outdated" |
| `evaluation` | Golden-set harness: recall@6, MRR, fact accuracy, stale leakage |
| `evidence`, `output_checks` | Evidence pack and post-inference checks, ready for Phase 4 |

### Deviations from the decision

1. **A second SQLAlchemy exception: the loader.** The knowledge tables use
   PostgreSQL text arrays and JSONB, which the SaaS-OS ORM primitives do not
   cover.
   - `marocassist.knowledge.loader` uses SQLAlchemy Core on reflected
     tables, with no string-built SQL.
   - It runs only under the migrations role.
   - An import-linter contract forbids importing it from the app, the API,
     the worker or any other runtime module.
   - **The owner still has to accept this exception** ([owner actions](../phase-3/OWNER_ACTIONS.md) §2).
2. **Search is `POST /search` with a JSON body, not `GET ?q=`.** A query
   string put the user's question into the access log, the trace span and
   the edge log. That went against the owner's decision that individual
   searches are never logged. It was found in the WP E end-to-end run.
3. **The content version is a hash of the parsed content, not the git SHA.**
   Unchanged content is therefore a no-op on every deploy, whatever the
   commit.
4. **The statement timeout is set by the caller** (`fts`, 200 ms), not
   inside the SQL function.
5. **The tenant `citations` stub moves to Phase 4,** with the conversations
   that would use it.

### Measured results (fixture content, 2026-11-21)

- Golden set: 35 search questions and 8 fact lookups.
  - recall@6 is 1.00 in NL, FR, AR and EN.
  - MRR: NL 0.87, FR 0.91, AR 1.00, EN 1.00.
  - Facts 8/8, stale leakage 0.
- These numbers come from a small fixture corpus of 9 items. **They say the
  pipeline works, not that recall on real content will be this high.** The
  embeddings triggers below must be measured again on real content.

## When embeddings would be justified (not now)

Revisit this decision only if at least one of these holds after synonym tuning
and over two consecutive evaluation cycles:

| Trigger | Threshold |
|---|---|
| Golden-set recall@6 (the right source among the top 6) | below 0.85 for any language |
| Zero-result rate (aggregated totals only, at least 10 searches per reported cell; no search terms stored, no individual searches logged) | above 10% of searches for 30 days |
| Corpus size | above 20,000 published chunks, or more than 3 countries |
| Cross-lingual need | more than 20% of the golden set needs a match across languages that synonyms cannot cover |

Even then, the route is a governed SaaS-OS capability (upstream proposal U-8,
"Governed embeddings"; owner decision 2026-11-20: no embeddings or vector
database in the MVP)
plus `pgvector` in the same PostgreSQL. Never a direct embeddings API and never
an external vector service.
