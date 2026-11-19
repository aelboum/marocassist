# Product roadmap

Status: Phase 0 output, 2026-11-19 (RECOMMENDATION). MVP = Phases 1–5 plus
the minimum of Phases 8–9 needed for a beta (see `MVP_SCOPE.md`). Complexity:
S (days), M (1–2 weeks), L (3–5 weeks), XL (6+ weeks), assuming one or two
developers with AI assistance. Estimates are indicative, not commitments.

Changes from the preliminary phase list:

- Phase 1 includes a **SaaS-OS integration spike** (onboarding tenant,
  service-account key, `run_inference` with the fake provider) because three
  core design choices depend on behaviour not yet exercised end to end.
- Phase 3 starts with the **content-rights and editorial model**, because
  official sources offer no verified reuse licence or API.
- Basic translation and error explanation move into Phase 5 when cheap;
  Phase 6 keeps highlighting polish, workflow graphs and optional vision.
- Phase 9 work (privacy, backups, monitoring) is spread across phases as
  Definition-of-Done items; Phase 9 is the final hardening and launch gate.

Common Definition of Done (applies to every phase): small reviewed PRs; CI
green (lint, types, unit, integration, architecture, security scans);
isolation tests for every new tenant table; purge participant updated;
docs updated (architecture + runbooks); no secrets; security-sensitive
changes independently reviewed; owner approval before merge.

---

## Phase 0 — Architecture and repository audit (this phase)

- **Objective:** evidence-based plan. **Status:** complete with this document set.
- **Deliverables:** `docs/architecture/*`, `docs/roadmap/*`, `docs/research/*`, README summary.
- **Open items:** owner decisions D-01, D-03; evidence capture of official sites.

## Phase 1 — Foundation

- **Business objective:** a deployable, tested skeleton so every later feature lands safely.
- **Functional scope:** none user-visible beyond health pages and login redirect.
- **Technical tasks:**
  1. Repo scaffolding per `SYSTEM_ARCHITECTURE.md` §9 from `examples/consumer-scaffold` (renamed `marocassist`), SaaS-OS pinned to D-01.
  2. `marocassist.app` on `build_platform_app()`; worker on `saas_os.api.worker.main`; `marocassist.migrate`.
  3. Import-linter contracts (module boundaries, no `saas_os.control_plane`, no direct `sqlalchemy`).
  4. Next.js `web/` skeleton with i18n (nl/fr/ar/en, RTL), CSP.
  5. `extension/` skeleton (MV3 manifest, side panel "hello", build, permission snapshot test).
  6. Docker Compose dev stack (Postgres 16, Redis 7, ZITADEL, Mailpit, backend, worker, web, Caddy single origin via `saas-os-edge-config`).
  7. CI: backend, web, extension, security (pip-audit, npm audit, detect-secrets), migrations job (Postgres service), integration job (Postgres + Redis).
  8. **Integration spike** (throwaway branch, findings in an ADR): personal tenant via `SystemCaller(PROVISIONING)`; service account + `sok_` key calling an `api_key=True` route; `run_inference` with the fake provider under a `ServiceAccountCaller`.
  9. ADRs: 0001 SaaS-OS pin and consumer boundary, 0002 monorepo, 0003 tenancy mapping, 0004 extension auth.
  10. `CLAUDE.md`/contributing guide; PR template with security checklist.
- **Dependencies:** D-01, D-02, D-03 decided.
- **Deliverables:** green CI on `main`; `docker compose up` gives a working single-origin dev stack with login.
- **Acceptance criteria:** see `ACCEPTANCE_CRITERIA.md` §1.
- **Automated tests:** app starts with route-policy check; migrations up/down on empty DB; health/readiness; architecture contracts; manifest snapshot.
- **Security requirements:** app refuses superuser DB role (SaaS-OS guard); no secrets in repo; CSP baseline; dependency scans gate CI.
- **Risks:** R-15 (upstream API drift), spike disproves D-06 or extension auth design.
- **Complexity:** M–L.
- **Critical decisions:** D-01, D-02, D-03, D-04.
- **Definition of Done:** common DoD + spike ADR accepted.

## Phase 2 — Identity and SaaS foundation

- **Business objective:** users can create an account and see a personalised dashboard.
- **Functional scope:** sign-up/login (ZITADEL, email verification, reset, optional MFA); onboarding (personal tenant, language, consulate, consents); profile; preferences; dashboard shell; account export/delete request; connected devices page (empty until Phase 5).
- **Technical tasks:** onboarding route (idempotent); roles `owner`/`copilot_client` + permission registration and grants; profile/preferences/consents tables with RLS + purge participant; audit records for consent changes; email templates (NL/FR/AR/EN); ZITADEL branding neutral (no government look).
- **Dependencies:** Phase 1; D-06.
- **Deliverables:** account lifecycle end-to-end in staging.
- **Acceptance criteria:** `ACCEPTANCE_CRITERIA.md` §2.
- **Automated tests:** 401/403/404 matrix per route; cross-tenant isolation per table; onboarding idempotency and concurrency; consent audit row in same transaction; purge removes all product rows.
- **Security requirements:** ADR-0044 same-origin behaviour verified; session fixation/logout tests; no PII in logs.
- **Risks:** ZITADEL configuration complexity; email deliverability.
- **Complexity:** L.
- **Critical decisions:** sign-up fields minimal (email + password/passkey only); MFA optional vs required.
- **Definition of Done:** common DoD + privacy notice draft.

## Phase 3 — Consular knowledge platform

- **Business objective:** trustworthy, cited consular information for the MVP services and NL consulates.
- **Functional scope:** catalogue browsing/search (NL/FR/AR); procedure pages with steps, required documents, fees, sources, last-verified date; appointment preparation checklist; editorial workflow (draft → review → publish) in the editorial tenant.
- **Technical tasks:** content-rights approach confirmed (Q-K1 interim: paraphrase + cite); data model (`DATA_ARCHITECTURE.md`); content as reviewed source files in `knowledge/` imported by a migration-safe loader **or** editorial UI (start with files + PR review: cheapest, auditable); source registry + snapshots + change-detection job (`StrictEgressClient`, allow-list, robots.txt); FTS index (D-07); retrieval API with filters; freshness dashboard.
- **Dependencies:** Phase 2; D-07; owner evidence capture of official sites.
- **Deliverables:** 5–8 services × 4 consulates published with sources.
- **Acceptance criteria:** `ACCEPTANCE_CRITERIA.md` §3.
- **Automated tests:** content schema validation; every published fact has a source; retrieval relevance tests on fixtures; change-detection job with fake fetcher; editorial permission tests.
- **Security requirements:** knowledge writes only by editorial permission; fetcher cannot reach internal addresses (egress policy); sanitised rendering.
- **Risks:** R-03, R-04, R-05, R-09.
- **Complexity:** L.
- **Critical decisions:** D-07; file-based vs UI-based editing (recommend file-based first).
- **Definition of Done:** common DoD + editorial runbook.

## Phase 4 — AI assistant

- **Business objective:** users get grounded answers in their language.
- **Functional scope:** chat in the web app; conversation history (list, rename, delete); citations and source cards; answer language selection; AI consent/enablement in onboarding; usage view.
- **Technical tasks:** register use cases; enable tenant AI policy and grants via `saas_os.inference.settings` at onboarding (explicit consent); orchestration pipeline (`AI_ARCHITECTURE.md` §3); redaction; prompt templates versioned; citation validator; output policy checks; error mapping; operator AI configuration runbook (providers, aliases, destination policy, prices, quotas, budgets); eval harness + golden set (≥150 questions); mount `ai_usage` router.
- **Dependencies:** Phase 3 corpus; D-08 provider selected with DPA.
- **Deliverables:** assistant in staging meeting quality bar.
- **Acceptance criteria:** `ACCEPTANCE_CRITERIA.md` §4.
- **Automated tests:** pipeline unit tests with fake provider; redaction canaries; injection fixtures; citation validator; quota/budget error handling; eval run in CI (structure) + scheduled (quality).
- **Security requirements:** no identifiers in prompts; untrusted content fenced; output sanitised; budgets on (`AI_INFERENCE_TOKEN_QUOTA_REQUIRED`, `AI_INFERENCE_BUDGET_REQUIRED` in prod).
- **Risks:** R-06, R-07, R-08, R-10, R-17.
- **Complexity:** L.
- **Critical decisions:** D-08; budget enforcement vs. daily price confirmation (R-10).
- **Definition of Done:** common DoD + eval report committed.

## Phase 5 — MarocAssist Copilot (MVP)

- **Business objective:** the differentiator — guidance on rdv.consulat.ma while the user stays in control.
- **Functional scope:** install, pair, enable for RDV (optional permission), side panel with step recognition, explanation of the current step, Q&A about the page, basic translation, basic validation-error explanation, consent + preview, pause, independent-assistant banner.
- **Technical tasks:** pairing flow (service account + key); `copilot` API (`whoami`, `explain`, `ask`, `translate`) with `api_key=True`; content script extractor + masking + MutationObserver + recognition rules; owner-captured sanitised fixtures and a local mock site; side panel UI (NL default); server-side snapshot validation + redaction; `page_contexts` retention job; Chrome Web Store listing (unlisted) and privacy disclosures.
- **Dependencies:** Phase 4; legal R1–R3, Q-P3; D-05, D-11; real page captures (R-18).
- **Deliverables:** unlisted extension for closed beta.
- **Acceptance criteria:** `ACCEPTANCE_CRITERIA.md` §5.
- **Automated tests:** extractor unit tests; canary payload tests (passwords, hidden inputs, CSRF tokens, ID numbers); manifest permission snapshot; Playwright E2E with unpacked extension against mock site; API key scope tests (copilot key cannot read documents/profile); injection fixtures.
- **Security requirements:** all principles in `SECURITY_AND_PRIVACY.md` §3; no network calls to RDV (asserted by test that inspects extension network calls in E2E).
- **Risks:** R-01, R-02, R-12, R-18.
- **Complexity:** XL.
- **Critical decisions:** D-11; auto-share vs per-request share default (recommend per-request).
- **Definition of Done:** common DoD + independent security review of the extension + store review passed (unlisted).

## Phase 6 — Advanced Copilot

- **Business objective:** reduce errors and drop-off in the appointment flow.
- **Functional scope:** smart highlighting of relevant fields/buttons; richer validation-error explanation; full-page translation view; workflow progress (step graph); optional vision (if D-12 changes).
- **Technical tasks:** highlight protocol (refs only, validated); step graph in knowledge model; translation cache + glossary; streaming adoption if upstream ships (#206); vision proposal only with evidence.
- **Dependencies:** Phase 5 beta feedback.
- **Acceptance criteria:** `ACCEPTANCE_CRITERIA.md` §6.
- **Automated tests:** highlight refs never address unknown elements; overlay never changes input values or focus; translation cache keyed without personal data.
- **Security requirements:** same as Phase 5; vision only under governed path.
- **Risks:** R-02, R-08.
- **Complexity:** L (XL with vision).
- **Critical decisions:** D-12.
- **Definition of Done:** common DoD.

## Phase 7 — Personal documents

- **Business objective:** users arrive at the consulate with a complete, valid file.
- **Functional scope:** secure upload (PDF/JPEG/PNG), document vault, type classification, expiry tracking, completeness check against a procedure's requirements, retention and deletion controls.
- **Technical tasks:** storage port + S3 adapter (EU); envelope encryption; upload validation pipeline; sandboxed OCR worker (D-13); rule-based classification and completeness (LLM optional, never with document content unless explicitly approved); expiry notifications; crypto-shredding; download audit.
- **Dependencies:** D-10, D-13; legal Q-P2; DPIA update.
- **Acceptance criteria:** `ACCEPTANCE_CRITERIA.md` §7.
- **Automated tests:** malicious file corpus; encryption at rest (bucket objects are ciphertext); cross-tenant download denial; deletion removes blob + DEK; OCR worker resource limits.
- **Security requirements:** MFA recommended for document access; no document content to LLM by default; audit every access.
- **Risks:** R-14.
- **Complexity:** XL.
- **Critical decisions:** D-13; whether to store identity numbers at all.
- **Definition of Done:** common DoD + independent security review.

## Phase 8 — Commercial features

- **Business objective:** sustainable revenue without tying price to appointments.
- **Functional scope:** plans (free/plus), Stripe checkout and payment page, plan management, usage quotas (assistant messages, Copilot sessions, document storage), notifications (in-app list + email).
- **Technical tasks:** Catalog v2 plans with entitlements (`ai.inference`, `ai.tokens`, product entitlements); `require_entitlement_and_quota` on product routes; Stripe events router + webhook secret; in-app notifications route (or adopt upstream #230); billing pages.
- **Dependencies:** D-15, D-16; company/legal setup for payments.
- **Acceptance criteria:** `ACCEPTANCE_CRITERIA.md` §8.
- **Automated tests:** Stripe test-mode integration; entitlement gating; idempotent subscribe; quota exhaustion UX.
- **Security requirements:** webhook signature verification (SaaS-OS); no card data handled by MarocAssist.
- **Risks:** R-17; consumer-law requirements (Q-P7).
- **Complexity:** M.
- **Critical decisions:** D-15, D-16.
- **Definition of Done:** common DoD.

## Phase 9 — Production readiness

- **Business objective:** safe public launch.
- **Functional scope:** none new; hardening.
- **Technical tasks:** threat-model review; external pen test (D-14); load test of assistant and API (`performance` marker pattern); DPIA and privacy notice final; production compose with TLS DB/Redis; backups + restore drill; audit digest shipping to append-only store; log-based alerting (AI errors, price staleness, job dead letters, 5xx); runbooks (incident, erasure, key rotation, RDV-change response); status page; SaaS-OS deployment checklist §15 complete; AI qualification D1–D14.
- **Dependencies:** all MVP phases; D-18 counsel outputs.
- **Acceptance criteria:** `ACCEPTANCE_CRITERIA.md` §9.
- **Automated tests:** smoke tests post-deploy; restore verification script; alert tests.
- **Security requirements:** all high findings fixed or formally accepted with expiry.
- **Risks:** R-11, R-13.
- **Complexity:** L.
- **Critical decisions:** RTO/RPO; go/no-go owner sign-off.
- **Definition of Done:** go-live checklist signed.

## Phase 10 — Future expansion

- **Scope candidates:** Microsoft Edge (Chromium; same MV3 code, separate store listing), voice (depends on upstream streaming/audio, #206), Darija (content + model eval), additional Moroccan administrative services (idarati-listed procedures, civil status, tax) and other countries (BE, FR, ES, DE).
- **Precondition per item:** demand evidence, legal check, upstream capability where needed.
- **Complexity:** each M–XL.

---

## Timeline sketch (indicative, sequential with overlap)

| Phase | Indicative duration |
|---|---|
| 1 | 2–3 weeks |
| 2 | 3–4 weeks |
| 3 | 3–5 weeks (content effort runs in parallel) |
| 4 | 3–4 weeks |
| 5 | 6–8 weeks |
| Closed beta | after Phase 5 + legal review |
| 6–9 | 10–16 weeks combined, order by beta feedback; 9 gates public launch |
