# Phase 3 architecture report: knowledge and content

Date: 2026-11-20. Status: **the owner approved the design on 2026-11-20,
subject to the conditions in §12–13. It is not implemented.**
Repository `aelboum/marocassist` (PUBLIC). PR #1 (Phase 2) is open and not
merged. SaaS-OS v0.15.0 is pinned at `cdede956dd884fc816b234f1b546ce3b983b4efc`.

Companion documents:

- [Content rights and provenance](CONTENT_RIGHTS_AND_PROVENANCE.md)
- [Knowledge search architecture](KNOWLEDGE_SEARCH_ARCHITECTURE.md)
- [ADR-0007: knowledge search (D-07)](../adr/0007-knowledge-search.md)
- [Phase 3 security review](PHASE3_SECURITY_REVIEW.md)
- [Phase 3 implementation plan](PHASE3_IMPLEMENTATION_PLAN.md)

## 1. Summary

MarocAssist can build a trustworthy multilingual knowledge base with what it
already has: PostgreSQL 16 and SaaS-OS. No vector database and no new
infrastructure are needed.

The design rests on six points:

1. **Content is curated, not copied.** Content is the editors' own explanations
   and cited facts. Each fact links to a registered source that has a rights
   status, a verification date and a review date.
2. **Global knowledge is separate from tenant data.** Knowledge tables are
   global and read-only for the running app. Only a deploy-time loader writes
   to them, and every publication is audited.
3. **Search uses PostgreSQL full-text search plus trigram and an editor-run
   term table.** Facts come from structured rows, not free text.
4. **Only approved knowledge reaches the model.** It is passed as a fenced,
   labelled evidence pack, and deterministic output checks enforce citations,
   fact equality and freshness.
5. **SaaS-OS is reused for everything except full-text search**, where it
   exports nothing. A single, narrow, tested exception covers that gap, with an
   upstream exit (U-1).
6. **Consulate data is split per attribute**, each with its own source and
   status. Rotterdam is shown with location Schiedam. Opening hours and
   jurisdiction are not invented.

**Verdict: CONDITIONAL GO** (§12).

## 2. Current situation (verified in the repository)

| Item | State |
|---|---|
| Product modules | `accounts`, `copilot`, `privacy`, `purge`, `jobs`, `worker`. **There is no knowledge, search or assistant code.** |
| Database | Product schema `marocassist`; migrations `0001`, `0002_marocassist_profile` (on the PR); tenant tables with forced RLS |
| Consulates | Codes only (`profiles.consulate_code`; `CONSULATES` in `accounts/profile.py`; i18n names). The physical location, address and jurisdiction model exists only as a document (`docs/product/CONSULATES.md`, on the PR). |
| Architecture rules | The import-linter forbids `sqlalchemy` and `psycopg` outside migrations; `accounts` and `copilot` are independent; there is no `saas_os.control_plane` import (test) |
| Earlier design | Phase 0 sketches in `docs/architecture/DATA_ARCHITECTURE.md` (sources, snapshots, chunks) and `AI_ARCHITECTURE.md` (pipeline, grounding, injection). This proposal refines and partly replaces them (§11). |
| Legal research | `docs/research/OFFICIAL_DATA_SOURCES.md`. No official Moroccan source has a verified reuse licence. idarati.ma reserves reproduction. Q-K1 to Q-K4 are open. |

## 3. Reusable SaaS-OS functionality (pinned version, read in source)

| Need | SaaS-OS at the pin | Use |
|---|---|---|
| Sessions, permissions, membership | `require_permission`, `get_current_actor`, RBAC, permission grant migrations | Knowledge routes are tenant-scoped and permission-checked |
| Tenant isolation | `tenant_rls_statements`, `tenant_session_scope` | Reports and citations (tenant side) |
| Global tables | Plain tables plus grants (no helper). `tenant_context_exclusion_statements` exists but hides rows from tenant transactions, so it is **not** suitable for knowledge. | Knowledge tables without RLS; app role `SELECT` only |
| Audit | `record_in_transaction`, `record_system_action_in_transaction`. A tenant is required. | Publications audited in an **editorial tenant** |
| Jobs | `register_system_job` | Daily editor review report |
| Rate limit, statement timeout | `enforce_rate_limit`, `set_local_statement_timeout` | Search protection |
| Outbound HTTP | `StrictEgressClient` | Only if change detection is approved later |
| AI | `run_inference`: text only, classification per part (`none`/`tenant_data`/`sensitive`), roles system/user/assistant, no tools, no JSON mode, no streaming, no embeddings | Evidence pack (`none`) plus question (`tenant_data`) in Phase 4 |
| Purge | Purge participants | Tenant-side knowledge rows |

## 4. Missing functionality

| Gap | Response |
|---|---|
| No full-text search primitives in `saas_os.infra.db` | D-07 option 3: one product function and one module exception; upstream U-1 |
| No tenant-less audit | Use an editorial tenant (no parallel audit table) |
| No embeddings or vector search | Not needed for the MVP; measurable triggers in the ADR |
| No structured (JSON) model output | Constrained plain-text citations plus strict parsing (Phase 4) |
| No editor tooling | File-based content plus PR review first (P3-D2) |
| PostgreSQL Arabic stemmer misses broken plurals; no Darija configuration | Normaliser plus editor term table (measured, §5) |

## 5. Measured facts behind the search design

Measured on 2026-11-20 on the CI PostgreSQL image (16.15, pinned digest), in a
throwaway local container:

- `arabic`, `dutch`, `english`, `french` and `simple` configurations exist.
- `pg_trgm` and `unaccent` are available; **pgvector is not**.
- Dutch and French stemming work. French needs `unaccent` for accent-free
  queries.
- Arabic handles ال, diacritics and alef variants, but **not broken plurals**.
- Trigram helps with transliteration variants (0.40) and typos (0.59), but not
  with different names (0.00) or Arabic ة/ه (0.23).

Each gap has a designed mitigation (`KNOWLEDGE_SEARCH_ARCHITECTURE.md` §4.1).

## 6. Proposed architecture

```mermaid
flowchart TB
  subgraph Editorial["Editorial (PR-reviewed files in knowledge/)"]
    SRC[Source register] --- ITM[Items NL/FR/AR/EN] --- FCT[Facts] --- TRM[Terms] --- CON[Consulate attributes]
  end
  Editorial -->|CI validation: rights, PII, sanitiser, allow-list| LOAD[Loader at deploy<br/>migrations role, audited in editorial tenant]
  LOAD --> KDB[(Global knowledge tables<br/>app role SELECT only)]
  subgraph App["MarocAssist app (app role)"]
    API[Tenant-scoped knowledge routes<br/>require_permission + rate limit] --> RET[retrieval.py]
    RET --> FTS[fts.py → knowledge_search()]
    RET --> CAT[catalogue.py facts / consulates]
    RET --> EV[evidence.py<br/>evidence pack + source cards]
  end
  FTS --> KDB
  CAT --> KDB
  EV -->|Phase 4| INF[saas_os.inference.run_inference]
  API --> TDB[(Tenant tables with RLS<br/>reports, citations)]
```

## 7. Conceptual data model and API

- **Data model:** search architecture document §3 (global tables) and §6
  (consulates); rights document §2 (source register) and §4 (items, facts,
  citations).
- **API:** search architecture document §7. Every route is under
  `/v1/tenants/{tenant_id}/knowledge/...` and uses the existing SaaS-OS
  permission and rate-limit chain.

## 8. Security analysis (summary)

There are no design-level critical or high findings. The medium items are:

- four-eyes review needs a second reviewer (P3-S1);
- rights questions are unanswered (P3-S2);
- PR-based review needs branch protection (P3-S3);
- prompt injection through editor-approved text (T-9; layered controls).
  Owner decision 2026-11-20: editor-approved documents are also untrusted
  input, never instructions for the AI.

Full analysis: `PHASE3_SECURITY_REVIEW.md`.

## 9. Privacy and rights analysis (summary)

- **Rights:**
  - Default use is link plus own explanation.
  - Verbatim text, hosted documents and permission-only content are refused
    without recorded evidence.
  - No scraping or bulk import; change detection is off until the owner and a
    lawyer decide.
- **Privacy:**
  - No user data in knowledge (schema test plus loader PII scan).
  - Queries are not stored or logged.
  - Tenant-side rows are under RLS and included in the purge.
  - The AI gets evidence parts classified `none` and the question classified
    `tenant_data`.
  - Moroccan law 09-08 applicability remains an open legal question.

## 10. Test strategy

See the [implementation plan](PHASE3_IMPLEMENTATION_PLAN.md) §4: unit, contract and architecture,
integration on PostgreSQL 16, E2E, golden-set evaluation, red-team and privacy
log scan.

## 11. Corrections to earlier documents (found during this audit)

| # | Finding | Proposed fix |
|---|---|---|
| C-1 | **Proposal ID collision.** The Phase 0 upstream register (`RISKS_AND_DECISIONS.md` §3) used U-4 = "Governed embeddings" and U-5 = "Governed image input". The Phase 2 work (PR #1) used **U-4 for RP-initiated logout** and named back-channel logout "U-5". | **Resolved (final owner decision 2026-11-20).** U-4 RP-initiated logout; U-5 stays governed image input; U-8 governed embeddings; U-9 unused; U-10 back-channel logout. See the register in `RISKS_AND_DECISIONS.md` §3. |
| C-2 | `DATA_ARCHITECTURE.md` lists a `licence_status{unknown,link_only,authorised}` and `source_snapshots` with text. | Replace with the rights classes and `allowed_use` in this proposal. Snapshots store hash only until Q-K2 is answered. |
| C-3 | `DATA_ARCHITECTURE.md` §5 says "writes through the app role only from editorial routes". | Replace with "loader under the migrations role; app role `SELECT` only" (stronger integrity). |
| C-4 | `AI_ARCHITECTURE.md` lists streaming as missing. `stream_inference` exists in the pin's public API but always raises `InferenceUnsupportedCapabilityError`. | Clarify the wording; the conclusion is unchanged. |
| C-5 | **Second ID collision (U-3).** `docs/phase-2/PHASE2_AUDIT_AND_PLAN.md` called a self-service "log out everywhere" proposal "U-3", but U-3 is streaming inference (Phase 0 register; `docs/phase-1/STREAMING_SPIKE.md`). | **Resolved (final owner decision 2026-11-20).** "Log out everywhere" is U-11, with a design proposal and open questions in `RISKS_AND_DECISIONS.md` §3.1. U-3 stays streaming inference. |
| C-2…C-4 status | Not changed in this commit; the documentation task covered only the Phase 3 documents, the ADR and the U-renumbering. | Proposed for a later docs commit. |

## 12. Verdict

**CONDITIONAL GO.** The architecture is sound and needs no fundamental change.
On 2026-11-20 the owner approved the design and took decisions P3-D1, P3-D2,
P3-D5, P3-D6, P3-D9 and P3-D10 (§13).

**Implementation itself is not yet approved.** It needs separate, explicit owner
approval, and PR #1 should be merged first, with owner permission.

**Technical development may continue** once implementation is approved, using
fixture content. **Real knowledge content must not be approved or published**
until all of these are in place:

1. a second, independent content reviewer is appointed (P3-D3, open);
2. the editorial tenant exists (P3-D10);
3. the legal questions are answered (Q-K1, Q-K2, Q-K5, Q-K6; P3-D12, open).
   Until then only R1–R3 content is allowed;
4. branch protection on `main` is enabled by the repository owner (P2-F7,
   open), because content review runs through PRs.

## 13. Open decisions

Status per decision after the owner's decision of 2026-11-20.

| ID | Decision | Impact | Recommendation / decision | Status |
|---|---|---|---|---|
| P3-D1 | D-07: how to access full-text search | Architecture rule; database chokepoint | **Option 3**: one SQL function in a migration plus one module `knowledge.fts` allowed to use `sqlalchemy.func`; SaaS-OS keeps tenant isolation, RLS, permissions, rate limits and audit; U-1 upstream; no embeddings or vector database in the MVP | **Decided** (owner, 2026-11-20) |
| P3-D2 | Where content lives and how it is edited | Integrity, review flow, public exposure | Own explanations, facts and links in `knowledge/` in this repo; no copied official content without demonstrable rights; rights evidence outside the public repo; no user personal data | **Decided** (owner, 2026-11-20) |
| P3-D3 | Who is the second reviewer (four-eyes) | Without it, publication cannot meet the four-eyes rule | An independent second reviewer is mandatory for real content. Technical development may continue; no real content is approved or published until one is appointed. | **Open**: reviewer not yet appointed |
| P3-D4 | Automated change detection of official pages | Legal exposure; freshness | **Off.** Manual review schedule first; revisit after Q-K2, per source, only where terms and robots.txt allow | No |
| P3-D5 | Show unverified consulate attributes (single-source addresses)? | User trust versus completeness | Single-source addresses are shown with the label "nog niet onafhankelijk bevestigd" and a link to the source; opening hours and jurisdiction stay "not available" until officially verified | **Decided** (owner, 2026-11-20) |
| P3-D6 | Review periods | Editorial workload versus freshness | Fees 90 days, procedures 180 days, own explanations 365 days; a known change triggers an earlier re-check; expired content is never shown as current | **Decided** (owner, 2026-11-20) |
| P3-D7 | Display name for the Rotterdam consulate | UX consistency with official lists | "Consulaat-generaal Rotterdam" with location "Schiedam" (owner instruction); revisit if Moroccan sources name it otherwise | No (decided by owner) |
| P3-D8 | Public (unauthenticated) catalogue | Reach and SEO versus scraping surface | Authenticated only in Phase 3; reconsider at launch | No |
| P3-D9 | Search-query analytics | Search quality versus privacy | Only aggregated totals; no individual search terms stored or searches logged; at least 10 searches per reported cell; no re-identification through successive reports or small subgroups. The minimum is a privacy measure, not a guarantee. | **Decided** (owner, 2026-11-20, final) |
| P3-D10 | Editorial tenant for audit | Needed because SaaS-OS audit needs a tenant | One separate editorial tenant, created via the SaaS-OS operator; it must exist before the first publication | **Decided** (owner, 2026-11-20); **not yet created** |
| P3-D11 | Renumber upstream proposals (C-1, C-5) | Documentation clarity | U-4 RP-initiated logout, U-5 governed image input, U-8 governed embeddings, U-9 unused, U-10 back-channel logout, U-11 log out everywhere | **Done** (owner, 2026-11-20, final) |
| P3-D12 | Legal: Q-K1 (paraphrase or quotation), Q-K2 (snapshots), Q-K5 (Rijksoverheid reuse), Q-K6 (law 09-08) | Which rights classes are allowed | Until legal review: own explanations, cited facts and short summaries in our own words only; no verbatim reuse or hosted forms without demonstrable permission | **Open** |

## 14. Risks and dependencies

| Risk or dependency | Impact | Mitigation |
|---|---|---|
| Editorial capacity (solo maintainer) | High: content is the product | Start with 5–8 services in NL; golden set grows with content |
| Arabic and Darija recall | Medium | Term table; golden set per language; embeddings triggers |
| Official sites unreachable from some networks (Phase 0, R-03) | Medium | Manual verification from a residential connection; unreachable ≠ withdrawn |
| Hosting supports `pg_trgm` and `unaccent` | Medium | Verify at the D-10 hosting choice; both are standard contrib |
| U-1 upstream not accepted | Low | The exception remains, contained and tested |
| PR #1 not merged | Blocks a clean Phase 3 branch | Owner decision |

## 15. Estimated complexity

- **Engineering:** about 20–25 developer days (`PHASE3_IMPLEMENTATION_PLAN.md`
  §3). Complexity is **medium**: no new infrastructure, one migration, one new
  module, and moderate frontend work.
- **Editorial:** likely larger than the engineering effort, and it is the
  critical path to useful content.

Nothing in this design is implemented or migrated.
