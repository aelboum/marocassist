# Phase 3 report: curated knowledge and search

Date: 2026-11-22.

**Status:** work packages A–I are complete on branch `phase-3`, which is
open as [PR #3](https://github.com/aelboum/marocassist/pull/3) against
`main` and **not merged**. GitHub Actions CI is green on the pushed
commits (§7). Nothing has been released or deployed. The repository stays
PUBLIC, by owner decision, until MarocAssist is finished.

**Content:** fixture content only. Real content stays blocked until the
owner actions in §9 are done.

Plans and design: [implementation plan](PHASE3_IMPLEMENTATION_PLAN.md),
[architecture report](PHASE3_ARCHITECTURE_REPORT.md),
[ADR-0007](../adr/0007-knowledge-search.md),
[search architecture](KNOWLEDGE_SEARCH_ARCHITECTURE.md),
[content rights policy](CONTENT_RIGHTS_AND_PROVENANCE.md),
[security review](PHASE3_SECURITY_REVIEW.md),
[editor runbook](../runbooks/KNOWLEDGE_EDITING.md) and
[owner actions](OWNER_ACTIONS.md).

## 1. Executive summary

A signed-in user can now:

- search curated consular knowledge in Dutch, French, Arabic or English;
- open an item and follow its source cards to the official page;
- see whether information is current, expired or in conflict;
- see the consulates with a status per attribute;
- report an item as outdated.

The data and its protections:

- **Single writer.** Knowledge lives in global PostgreSQL tables. Only a
  publishing loader writes them, at deploy, under the migrations role. The
  running application can only read them.
- **Loader checks.** The loader refuses the whole bundle on any problem:
  rights, personal data, unsafe text, an unknown domain, four-eyes review,
  review dates or citations.
- **Expiry.** Expiry is computed whenever content is read, so a failed job
  can never make stale content look current.
- **Ready for Phase 4.** The evidence pack and the post-answer checks exist
  for the future assistant, together with a golden-set evaluation and a
  red-team suite.

On fixture content:

- recall@6 is 1.00 in all four languages;
- fact accuracy is 8/8;
- stale leakage is 0;
- all 57 red-team attacks are refused.

An independent code review found no critical or high issues. Its two medium
findings: one is fixed (P3-R1); the other needs branch protection, an owner
action (P3-R4).

## 2. Implemented

| WP | Result | Commit |
|---|---|---|
| A Schema | Migration `0003_knowledge`: `pg_trgm` and `unaccent`; immutable normaliser helpers with a pinned `search_path`; 11 global knowledge and consulate tables with generated `tsvector` columns and GIN and trigram indexes; `knowledge_search()` with read-time expiry and caps; the app role gets `SELECT` only; `knowledge_reports` with RLS and a purge participant | `14b44c6` |
| B Loader | JSON content bundle (pydantic models, generated `content.schema.json`); validation of rights, PII, sanitiser, domain allow-list, four-eyes, review periods, citations and consulate rules; dry run for CI; publishing in one transaction under an advisory lock, with an audit row in the editorial tenant; unchanged content is a no-op | `63aee15` |
| C Search | Query normalisation (cap, NFKC, Arabic folding identical to SQL, language detection, safe `websearch_to_tsquery`); term expansion (`knowledge_expand_terms`); `knowledge.fts` as the one runtime SQLAlchemy exception (`func` only, AST test); two-pass retrieval and reranking | `e31afa6` |
| D Catalogue and API | Item, fact and consulate reads with scope, conflict and needs-consulate handling; tenant-scoped routes behind `marocassist.knowledge:{read,report}`; grant migration `0002_owner_knowledge`; OpenAPI regenerated | `0db9a67` |
| — Fix | Search moved to `POST` with a JSON body, so the question never appears in a URL, log or trace | `f84ee91` |
| E Web | Search page, item page and consulates page; source cards (badge, scope, last verified, status, link with `noopener noreferrer`); NL/FR/AR/EN strings; RTL | `b322f2d` |
| F Freshness | Daily editor review report in the editorial tenant (SaaS-OS system job); anonymous per-day report counter; "report outdated" with 24-hour deduplication | `87b1d39` |
| G Evaluation and red team | Golden-set harness (recall@6, MRR, fact accuracy, stale leakage, p95) on a 9-item fixture corpus with 35 questions and 8 fact lookups, run in CI; 57 red-team attacks and 16 benign texts against the sanitiser and the loader. The suite found 22 sanitiser gaps, all closed. | `1171064` |
| H Evidence pack | `evidence.py` (fenced, escaped pack with sources S1–S6, facts, source cards and a clarifying question); `output_checks.py` (citations, amounts, links, credential, payment and contact requests, hidden characters, language, empty pack, fixed reply); fixed texts in `answer_texts.json` | `46a424f` |
| — Review fixes | Security review findings P3-R1, R2, R3, R5 and R6 fixed; LF line endings restored (P3-R10) | `af2a5f6`, `35bca05` |
| I Docs | ADR-0007 implementation section; the rights document made into the content rights policy, with an enforcement section; editor runbook; security review §6; corrections C-2 to C-4 in the architecture docs; this report | this commit |

## 3. Architecture changes

- **Global knowledge tables** in schema `marocassist`:
  - `knowledge_publications`, `knowledge_sources`, `knowledge_items`,
    `knowledge_item_texts`, `knowledge_chunks`, `knowledge_facts`,
    `knowledge_citations` and `knowledge_terms`;
  - `consulates`, `consulate_attributes` and `consulate_jurisdictions`.

  They have no tenant or user columns, and the app role has `SELECT` only.
- **Tenant tables** `knowledge_reports` and `knowledge_review_reports`:
  forced RLS, purge participants, and no `UPDATE` grant.
- **Global anonymous counter** `knowledge_report_counts`: item, reason, day
  and count, with no tenant column.
- **Six SQL functions:** search, term expansion, three catalogue reads and
  the review snapshot. All are `SECURITY INVOKER` with a pinned
  `search_path`, and are called only through `knowledge.fts`.
- **New module `marocassist.knowledge`.** The import-linter contracts:
  - `fts` is the only runtime SQLAlchemy import;
  - the loader, evaluation, evidence and output checks are never imported
    by the running app.
- **New routes** under `/v1/tenants/{tenant_id}/knowledge`:
  - `POST /search`;
  - `GET /items/{id}`, `/facts/{key}`, `/consulates` and
    `/consulates/{code}`;
  - `POST /reports`.
- **New system job** `marocassist_knowledge_review`.
- **Web pages:** `/dashboard/knowledge`, `/dashboard/knowledge/[itemId]` and
  `/dashboard/consulates`.

## 4. SaaS-OS usage (published interfaces only, no bypass)

The product uses these SaaS-OS functions:

- `require_permission`, `tenant_session_scope`, `session_scope`,
  `tenant_rls_statements` and `select`;
- `acquire_global_advisory_lock` and `acquire_tenant_advisory_lock`;
- `record_system_action_in_transaction` with a `SystemActor`;
- `register_system_job` and `PermissionGrantMigration`;
- `get_migrations_database_config`, `build_engine` and
  `build_session_factory`.

The two SQLAlchemy exceptions (`knowledge.fts` and the loader) are
documented in ADR-0007. SaaS-OS has no full-text-search primitives, and
upstream proposal U-1 would retire the `fts` exception. No knowledge data
goes to an AI provider in Phase 3.

## 5. Security findings

The design-stage review is in [security review](PHASE3_SECURITY_REVIEW.md)
§2–5. An independent code review of `main..phase-3` (2026-11-22, read-only)
found **0 critical and 0 high** issues. Full table: security review §6.

| ID | Sev. | Status |
|---|---|---|
| P3-R1 Output-check link allow-list missed some domains, schemes and homoglyphs | Medium | **Fixed** |
| P3-R4 Four-eyes trusts self-declared handles | Medium | **Open**: owner action (branch protection and `CODEOWNERS`) |
| P3-R2 Grouped numbers misread | Low | **Fixed** |
| P3-R3 Dollars and pounds not recognised | Low | **Fixed** |
| P3-R5 CI dry run skipped without a manifest | Low | **Fixed** |
| P3-R6 Report deduplication race | Low | **Fixed** |
| P3-R7 Term expansion does not use the trigram index | Low | Open: bounded by the 200 ms timeout; revisit at about 10,000 terms |
| P3-R8 Anonymous counter has no RLS | Info | Accepted |
| P3-R9 Any subdomain of an allow-listed domain is accepted | Info | Open: consider exact hosts |
| P3-R10 CRLF line endings | Info | **Fixed** |

Design findings: P3-S5 is closed. P3-S1, P3-S2 and P3-S3 are open owner
items (§9).

## 6. Privacy

- **Search queries:** never stored, never logged and never in a URL. The
  `POST` fix was verified on the local stack: after a search, the backend
  and edge logs contain no query text.
- **Knowledge has no user data.** A schema test shows the global tables have
  no tenant or user columns. The loader's PII scan refuses e-mail
  addresses, phone numbers, BSN, CNIE or passport numbers and IBANs
  outside consulate contact fields.
- **Reports:** "report outdated" stores an item id and a reason code only;
  the request refuses any other field. Reports are tenant-scoped and purged
  with the account. The daily review report holds ids, dates and counts
  only.
- **Audit:** the publication audit row holds the content version and counts,
  and no text.

## 7. Test results (2026-11-22, Windows 11, Docker)

| Suite | Result |
|---|---|
| Backend ruff, format, mypy strict, import-linter (3 contracts) | pass |
| Backend unit, including the red-team suite, evidence pack, output checks and OpenAPI drift | 863 passed |
| Backend integration on PostgreSQL 16: migration, grants, RLS, purge, loader, search, API matrix, review job, golden set | 122 passed |
| Golden set (fixture corpus) | recall@6 1.00 (NL, FR, AR, EN); MRR NL 0.87, FR 0.91, AR 1.00, EN 1.00; facts 8/8; stale leakage 0 |
| Red team | 57 attacks refused by the sanitiser and by the loader in 8 field placements, and inert in the evidence pack; 16 benign texts pass |
| Web Vitest | 31 passed |
| E2E `knowledge.e2e.mjs` (local stack): search, query not in the URL, source link without opener, click-through to the official page, expired notice, report, Rotterdam in Schiedam pending review, missing opening hours, Arabic RTL | 13/13 |
| GitHub Actions CI (5 jobs) | green on `46a424f`; the WP I commits run after push |
| gitleaks (full history) | no leaks |

## 8. Phase 3 acceptance criteria

| # | Criterion | Status | Evidence |
|---|---|---|---|
| 1 | Search in NL, FR, AR, EN with recall@6 ≥ 0.85 per language | PASS (fixture set) | Golden-set integration test, run in CI; 1.00 in every language |
| 2 | No path lets the running app write knowledge | PASS | Integration grant test: `INSERT`, `UPDATE` and `DELETE` denied for the app role; import-linter keeps the loader out of the app |
| 3 | Every item and fact is traceable to a verified source; the loader refuses anything else | PASS | Loader tests: every validation has a failing fixture (rights policy §11) |
| 4 | Expired, conflicting and secondary-only content is never shown as current | PASS | Fake-clock catalogue tests; stale leakage 0, including a "broken expiry" test one year later; E2E expired notice; notices in the evidence pack |
| 5 | Consulate attributes kept separate; Rotterdam shown in Schiedam; unverified attributes labelled; nothing invented | PASS | Catalogue and API tests; E2E: Schiedam pending review, missing opening hours point to the source; the loader refuses unverified opening hours and jurisdiction |
| 6 | Red-team suite green; output checks ready for Phase 4 | PASS | §7; output checks tested with crafted answers |
| 7 | CI green; no new high or critical security findings | PASS | CI green on `46a424f`; code review: 0 critical, 0 high |

Not covered by these criteria:

- The golden set has 35 questions, not the 150 the plan names as an
  editorial target. That needs real content.
- The French and Arabic strings still need a native-speaker review (P2-F5).

## 9. Open issues and owner actions

These block **real content**, not the merge. Details:
[owner actions](OWNER_ACTIONS.md).

1. Branch protection on `main` with required review, and `CODEOWNERS` for
   `knowledge/` (P2-F7, P3-S3, P3-R4).
2. Accept or reject the loader's SQLAlchemy exception (owner actions §2).
3. Appoint the second reviewer (P3-D3, P3-S1).
4. Create the editorial tenant and set `MAROCASSIST_EDITORIAL_TENANT_ID`
   for the loader and the worker (P3-D10).
5. Send the legal questions Q-K1, Q-K2, Q-K5 and Q-K6 (P3-D12, P3-S2).
6. Apply grant migration `0002_owner_knowledge` to existing tenants with
   `saas-os-operator apply-permission-grants` after deploy.

Other open items:

- P3-R7 (term-expansion index) and P3-R9 (exact hosts on the allow-list).
- The editor screen for the daily review report. For now an operator reads
  it from the database.
- Check that the production database host supports `pg_trgm` and
  `unaccent` (decision D-10, hosting).
- Measure the embeddings triggers again on real content. The fixture
  results say the pipeline works, not that recall on real content will be
  this high.
- Native-speaker review of the French and Arabic UI strings and of
  `answer_texts.json` (P2-F5).

## 10. Deviations from the plan

1. **A second SQLAlchemy exception: the loader.** SaaS-OS has no array or
   JSONB support; it awaits owner acceptance.
2. **Six SQL functions instead of one.** Search, term expansion, three
   catalogue reads and the review snapshot, all called through `fts`.
3. **Search is `POST`.** A `GET` query string leaked the question into logs.
4. **The content version is a content hash, not the git SHA.**
5. **The statement timeout is set by the caller** (200 ms).
6. **The tenant `citations` stub moves to Phase 4,** with conversations.
7. **The review job ticks every minute.** SaaS-OS `system_cron` has no daily
   period; after the first run of the day it is a no-op.
8. **An anonymous report counter was added,** so the daily job never reads
   tenant rows across tenants.
9. **Migration `0003` was edited in place during Phase 3.** It has never
   been merged or deployed.

## 11. Advice for Phase 4

- **Order of operations for the assistant:**
  1. build the pack with `build_evidence`;
  2. render the policy in the system message;
  3. send the pack as a `none`-classified user part and the question as
     `tenant_data`;
  4. call `run_inference`;
  5. run `check_answer`;
  6. show the source cards from the pack, never from the model.
- **Use a fake provider in CI.** The crafted-answer tests in
  `test_knowledge_output_checks.py` are the starting set.
- **Expect the output checks to block too often at first,** for example on
  "never share your DigiD code". Tune them on real model answers, and never
  loosen them without a red-team test.
- **Keep the golden set growing with the content.** Add every user report
  that turns out to be a search miss as a golden question.
- **Merge PR #3 before Phase 4 branches,** with owner permission.
