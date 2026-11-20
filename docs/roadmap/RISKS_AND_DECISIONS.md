# Risks and decisions

Status: Phase 0, 2026-11-19. Decisions marked **Blocking Phase 1** need an
owner answer before Phase 1 starts; all others have a recommended default
that Phase 1 can proceed on.

## 1. Decision register

| ID | Decision | Options | Recommendation | Blocks |
|---|---|---|---|---|
| D-01 | SaaS-OS pin | v0.15.0 `cdede95…` / older | **v0.15.0 `cdede956dd884fc816b234f1b546ce3b983b4efc`** (first release with `saas_os.inference.settings`) | **Blocking Phase 1** (confirm) |
| D-02 | Python packaging | pip + setuptools + `constraints.txt` (SaaS-OS ADR-0011, scaffold) / uv + `uv.lock` (LeadStack precedent) | uv with lockfile, `src/` layout — the owner's newer precedent, reproducible, hashes for pip-audit | Phase 1 (default OK) |
| D-03 | Repository layout | Monorepo (backend + web + extension) / three repos | **Monorepo**: shared API contracts, one CI, one review flow | **Blocking Phase 1** (confirm) |
| D-04 | Web frontend stack | Next.js (matches SaaS-OS fixture and LeadStack) / other | Next.js App Router, TypeScript, i18n nl/fr/ar/en with RTL | Phase 1 (default OK) |
| D-05 | Extension stack | TypeScript + Vite / WXT framework | TypeScript + Vite, minimal deps | Phase 5 |
| D-06 | Tenancy mapping | Personal tenant per user / one shared tenant | **Personal tenant per user** (`../architecture/SAAS_OS_INTEGRATION.md` §5) | Phase 2 |
| D-07 | Full-text search access (no FTS primitives in `saas_os.infra.db`) | (a) one product module allowed to import `sqlalchemy` for FTS, enforced by import-linter; (b) upstream proposal to export FTS primitives; (c) search in Python | (b) proposed upstream early; (a) as a documented, isolated interim exception if (b) is not available by Phase 3 | Phase 3 |
| D-08 | LLM provider(s) | Anthropic / OpenAI-compatible (incl. EU-hosted) / Gemini | Choose on EU processing, no-training terms, DPA, quality on the NL/FR/AR eval set; one primary + one fallback alias | Phase 4 |
| D-09 | Domain and brand | — | Owner choice; must not imply government affiliation (Q-P11) | Phase 1 for staging (dev uses localhost) |
| D-10 | Hosting provider (EU VPS) and object storage | — | EU provider with S3-compatible storage in the same jurisdiction | Phase 1 (staging) / Phase 7 |
| D-11 | RDV host permission model | optional host permission / `activeTab` only | Optional host permission granted at first use | Phase 5 |
| D-12 | Vision | none / upstream governed vision / direct API | None in MVP; upstream proposal only on evidence; never a direct API outside SaaS-OS governance | Phase 6 |
| D-13 | OCR engine | self-hosted / cloud OCR | Self-hosted first (ID documents stay in-house) | Phase 7 |
| D-14 | External penetration test before launch | yes / no | Yes, one-off, scoped to web, API, extension | Phase 9 |
| D-15 | Payment methods | Stripe (cards, iDEAL, SEPA) / Moroccan PSP | Stripe only for an NL-first launch (iDEAL/SEPA coverage to verify at procurement) | Phase 8 |
| D-16 | Pricing model | freemium + subscription / per-procedure pass | Freemium (catalogue + limited assistant) + monthly/annual plan; never priced per appointment | Phase 8 |
| D-17 | Launch market, languages, MVP services | — | NL first; UI NL + FR + AR (+EN); content NL-first; 5–8 services | MVP |
| D-18 | Legal counsel engagement | — | NL privacy counsel + Moroccan counsel before closed beta | **Blocking closed beta** |

## 2. Risk register

Scale: likelihood (L) / impact (I): Low, Medium, High.

| ID | Risk | L | I | Mitigation | Owner |
|---|---|---|---|---|---|
| R-01 | Product perceived as appointment broker/bot; consular or store action | M | H | Hard rules, transparent docs, no RDV network calls, pricing not tied to slots, store listing review, legal review R1–R3 | Owner |
| R-02 | RDV front-end changes break page recognition | H | M | Fingerprint rules, graceful fallback, unknown-page telemetry, fast release path | Eng |
| R-03 | Official sites unreachable from non-Moroccan/data-centre networks (observed during this audit) | H | M | Editorial verification from residential connections; tolerant freshness jobs; never origin-disguising proxies | Ops/Editorial |
| R-04 | Content reuse rights (idarati reserves reproduction) | M | H | Paraphrase + cite; request authorisation; legal opinion Q-K1 | Owner |
| R-05 | Wrong or outdated guidance harms users | M | H | Provenance, review dates, freshness checks, citations, disclaimers, feedback button, editorial SLA | Editorial |
| R-06 | Personal data leaked to AI provider | L | H | Value-free snapshots, redaction, canary tests, provider terms, SaaS-OS preferences | Eng |
| R-07 | Prompt injection via page content | M | M | `../architecture/AI_ARCHITECTURE.md` §7, red-team suite | Eng |
| R-08 | No streaming → slow perceived UX | H | M | Short answers, progress UI, fast alias for small tasks; adopt upstream streaming when available (#206) | Eng |
| R-09 | Lexical retrieval recall insufficient | M | M | Structured filters, editor-written summaries, eval set; upstream embeddings proposal if needed | Eng |
| R-10 | SaaS-OS budget enforcement refuses requests when a model price was not confirmed within the last 24 h (consumer guide §12a; `AI_PRICE_MAX_AGE_SECONDS` max 86400) | H | H | Runbook and daily confirmation task, alert on `budget_pricing_unavailable`; raise upstream if burdensome; or run without budgets initially (token quota only) — decision at Phase 4 | Ops |
| R-11 | Single VPS = single point of failure | M | M | Backups + restore drill, documented RTO/RPO, status page | Ops |
| R-12 | Chrome Web Store rejection or delay | M | M | Single purpose, minimal permissions, clear disclosures, no remote code | Eng |
| R-13 | Legal scope under Moroccan Law 09-08 unclear | M | M | Counsel (Q-P1); keep processing in EU, no Moroccan processors | Owner |
| R-14 | Identity document storage breach | L | H | Envelope encryption, minimal retention, in-house OCR, pen test | Eng |
| R-15 | SaaS-OS upstream changes break the product | M | M | SHA pin, `saas-os-update check`, contract tests on used interfaces | Eng |
| R-16 | Solo-maintainer bandwidth vs. scope | H | M | Strict MVP scope, small PRs, automation over process | Owner |
| R-17 | LLM cost overrun | M | M | SaaS-OS budgets and quotas, plan entitlements, cached translations | Ops |
| R-18 | Page-recognition rules need real RDV page structures, which are behind login and unreachable from CI | H | M | Owner-captured, sanitised fixtures; mock site in CI; never test against the live site in CI | Eng/Owner |

## 3. Upstream (SaaS-OS) proposals to prepare (not submitted in Phase 0)

| ID | Proposal | Needed by | Priority |
|---|---|---|---|
| U-1 | Export FTS primitives from `saas_os.infra.db` | Phase 3 | High |
| U-2 | Product-data hook for user erasure (participant protocol like purge) | Phase 9 | Medium |
| U-3 | Streaming inference (support existing issue #206) | Phase 6 | Medium |
| U-4 | RP-initiated logout ([proposal](../saas-os-proposals/U-4-RP-INITIATED-LOGOUT.md); closes P2-F1) | Before production (P2-F1 is a production blocker) | High |
| U-5 | Governed image input (only if D-12 changes) | Later | Low |
| U-6 | Device-authorisation or token-exchange flow for first-party extension clients | Later | Low |
| U-7 | Email template + i18n helper | Later | Low |
| U-8 | Governed embeddings (only if R-09 materialises; triggers in [ADR-0007](../adr/0007-knowledge-search.md)) | Later | Low |
| U-10 | OIDC back-channel logout (future work in the U-4 proposal) | Later | Low |

Renumbered on 2026-11-20 (owner decision; Phase 3 report §11, C-1). Before
that, U-4 was "Governed embeddings" here, while Phase 2 had already used U-4
for RP-initiated logout. Embeddings moved to U-8, and back-channel logout
(called "U-5" in the first U-4 draft) is U-10. U-5 remains "Governed image
input" as in Phase 0. U-9 is not assigned: the requested move of image input
to U-9 conflicts with keeping U-5 and awaits the owner's clarification.
