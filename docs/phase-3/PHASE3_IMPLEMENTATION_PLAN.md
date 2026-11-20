# Phase 3 implementation plan (proposal; not started)

Status: design approved by the owner (2026-11-20). **Implementation has not
started and needs separate, explicit owner approval.**

Preconditions:

- PR #1 (Phase 2) is merged, so Phase 3 branches from `main` and not from an
  unmerged branch.
- The conditions in the [architecture report](PHASE3_ARCHITECTURE_REPORT.md) §12–13 are met. In particular, real
  content needs the second reviewer, the editorial tenant and the legal
  answers.

## 1. Scope

**In scope:**

- knowledge schema and the search function;
- the publishing loader with validation;
- search, fact and consulate read APIs;
- a web search UI with source cards and a consulate page;
- an expiry and review job;
- "report outdated";
- the evidence-pack builder, tested without a model;
- the golden-set and red-team harness;
- documentation and ADR-0007.

**Out of scope (Phase 4 and later):**

- assistant answers through `run_inference`;
- conversations;
- the Copilot integration;
- an editor UI;
- automated change detection (P3-D4);
- embeddings.

## 2. Content workflow (recommended, P3-D2)

- **Where content lives.** Content is stored as files in `knowledge/` in this
  repository, in YAML or Markdown with front matter: sources, items (one file
  per item with all languages), facts, terms and consulates.
  - The files hold only R1–R3 content: own explanations, cited facts, short
    summaries and links.
  - Rights evidence and snapshots are **never** stored in the public repo.
  - Until the second reviewer is appointed, only fixture or test content
    exists. No real knowledge content is approved or published (owner
    decision 2026-11-20).
- **Review.** Every change goes through a PR. Required review by a second
  person depends on branch protection (P2-F7) and a second reviewer (P3-D3).
  CI runs:
  - the schema check;
  - rights-class versus `allowed_use`;
  - the PII scan;
  - the sanitiser;
  - link-domain allow-list;
  - date sanity;
  - the golden set.
- **Publishing.** At deploy time,
  `python -m marocassist.knowledge.load --content-version <git sha>` runs after
  migrations, with the migrations role.
  - It is idempotent and upserts by key.
  - It runs in one transaction with an advisory lock.
  - It writes one `knowledge_publications` row and one audit row in the
    editorial tenant.
- **Expiry is computed at read time.** The effective status is `expired`
  whenever `review_due_at < now()` or `valid_until < now()`. It is evaluated
  inside `knowledge_search()` and the catalogue queries, so no write privilege
  is needed and expiry can never be skipped because a job failed. A daily
  system job (`register_system_job`) only produces the editor review report.

## 3. Work packages

| WP | Content | Done when | Estimate |
|---|---|---|---|
| A Schema | Migration `0003_marocassist_knowledge`: `CREATE EXTENSION pg_trgm, unaccent`; immutable wrappers (`unaccent` schema-qualified; Arabic normaliser as SQL function); global tables (§3 of the search architecture document); generated `tsvector` columns; GIN and trigram indexes; `knowledge_search()` function; grants (app role `SELECT` only); tenant tables `knowledge_reports` (and `citations` stub) with `tenant_rls_statements`; purge participant | Migration up and down on a fresh DB in CI; grant test (app role cannot write knowledge); RLS test on reports | 2–3 days |
| B Loader | Content format and JSON-schema; loader with validation (rights, PII, sanitiser, allow-list, dates, four-eyes fields); dry-run mode for CI; audit in the editorial tenant | Fixture content loads idempotently; every validation has a failing fixture; audit row written | 3–4 days |
| C Search | `normalise.py` (language detection, Arabic, French, transliteration); term expansion; `fts.py` (the single exception); rerank; caps; import-linter and AST contracts | Unit tests per language, including the measured gaps (Arabic plural through terms, French accents); contract tests green | 3–4 days |
| D Catalogue and API | Fact lookup with scope and conflict handling; consulate attributes; tenant-scoped routes; permissions `marocassist.knowledge:{read,report}` plus grant migration `0002_*` for existing tenants; OpenAPI regenerated | 401/403/404 matrix extended; conflict and expired behaviour tested | 2–3 days |
| E Web | Search page; item page with source cards (badge, scope, last verified, status notice, outbound link); consulate page showing per-attribute status; NL/FR/AR/EN strings (FR/AR review, P2-F5); RTL | Vitest plus E2E: search, source click-through, expired notice, Rotterdam shows location Schiedam with a pending-review label | 3 days |
| F Freshness | Read-time expiry; "report outdated"; daily editor review report | Fake-clock tests (expired never shown as current); report RLS and purge tests | 2 days |
| G Evaluation and red team | Golden-set harness (recall@6, MRR, fact accuracy, stale leakage) on fixture content; red-team fixtures (visible, hidden, metadata, bidi, AR/FR injections) against the sanitiser and evidence builder | Harness in CI, report per language; red-team suite green | 2–3 days |
| H Evidence pack | `evidence.py` and the source-card builder; output-check library (citations subset, fact equality, URL allow-list, credential requests) ready for Phase 4 | Unit tests with crafted model outputs | 2 days |
| I Docs | ADR-0007 updated with implementation details, content rights policy, editor runbook, Phase 3 report | Reviewed | 1 day |

**Engineering estimate:** about 20–25 developer days, roughly 4–5 weeks for one
developer. **Editorial effort is separate:** registering sources, writing the
first 5–8 services in NL, translations, and a golden set of 150 questions. It
is owner- or editor-driven and probably larger than the engineering work.

## 4. Test strategy

| Level | What |
|---|---|
| Unit | Normalisation (per language, measured cases); term expansion; rerank weights; rights-class matrix; PII and sanitiser rules; evidence escaping; output checks |
| Contract and architecture | Import-linter (single `sqlalchemy` exception; `knowledge` independence; loader not importable by routes); AST test on `fts.py`; OpenAPI drift |
| Integration (PostgreSQL 16 in CI) | Migration on a fresh DB; extensions present; app role cannot write knowledge; `knowledge_search()` filters (status, scope, language) and caps; statement timeout; reports RLS and cross-tenant 404; purge removes reports; loader idempotency and audit row |
| E2E (local, Playwright) | Search to source card to official link (`noopener`); expired notice; consulate page labels; RTL in Arabic |
| Evaluation | Golden set per language; stale-leakage = 0; fact accuracy = 100% on fixture facts |
| Security | Red-team fixtures; XSS fixtures in titles and snippets; SQL meta-characters in queries; oversize queries |
| Privacy | Log scan during E2E (no query text, no PII); schema test (no tenant or user columns in global knowledge tables) |

## 5. Exit criteria (proposed Phase 3 acceptance)

1. Search works in NL, FR, AR and EN on fixture content, with golden-set recall@6
   ≥ 0.85 per language (fixture set).
2. No path lets the running app write knowledge (tested).
3. Every published item and fact is traceable to a verified source; the loader
   refuses anything else (tested).
4. Expired, conflicting and secondary-only content is never shown as current
   (tested; stale leakage 0).
5. Consulate data keeps display name, physical city, address, contact and
   jurisdiction separate. Rotterdam is displayed with location Schiedam;
   unverified attributes are labelled; no opening hours or jurisdiction are
   invented.
6. The red-team suite is green; the output-check library is ready for Phase 4.
7. CI is green on GitHub; there are no new high or critical findings in the
   Phase 3 security review.
