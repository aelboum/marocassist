# Acceptance criteria

Status: Phase 0, 2026-11-19. Each criterion must be demonstrable by an
automated test or a recorded manual check (evidence linked in the phase's
closing PR). "Test" means it runs in CI unless marked (staging) or (manual).

## 1. Phase 1 — Foundation

- [ ] `pyproject.toml` pins SaaS-OS to the exact SHA decided in D-01; a test fails if the pin is a branch or tag.
- [ ] `marocassist.app` starts; SaaS-OS route-policy assertion passes; `/healthz` 200, `/readyz` 200 with DB and Redis.
- [ ] App and worker refuse to start with a superuser/BYPASSRLS DB role (inherited guard, covered by an integration test).
- [ ] `python -m marocassist.migrate` applies SaaS-OS and product migrations on an empty PostgreSQL 16; re-run is a no-op.
- [ ] Import-linter contracts pass and include: no `saas_os.control_plane`, no direct `sqlalchemy`/`psycopg` (except D-07 module if chosen), module boundaries.
- [ ] Web app builds; i18n test fails on hard-coded UI strings; RTL renders for `ar`.
- [ ] Extension builds; manifest permission snapshot test passes.
- [ ] `docker compose up` provides login through ZITADEL at the single origin (manual, recorded).
- [ ] CI jobs green: backend, web, extension, security, migrations, integration.
- [ ] Spike ADR records results for: personal-tenant provisioning, service-account key on `api_key=True` route, `run_inference` with fake provider as `ServiceAccountCaller`.

## 2. Phase 2 — Identity and SaaS foundation

- [ ] New user can sign up, verify email, log in, log out (staging, manual + E2E against local ZITADEL).
- [ ] First login creates exactly one personal tenant, also under concurrent requests (integration test).
- [ ] Every product route: 401 without credential, 403 without permission, 404 for another tenant's id (test matrix).
- [ ] Every tenant table: isolation test reading without tenant predicate returns only own rows.
- [ ] Consent change writes an audit row in the same transaction.
- [ ] Purge of a personal tenant removes all product rows (integration test asserting `registered_purge_participant_names()` equals the expected tuple).
- [ ] No PII values in application logs during the E2E run (log scan test).
- [ ] Cookie-authenticated mutation from a foreign `Origin` returns 403.

## 3. Phase 3 — Knowledge platform

- [ ] Content schema validation rejects a published procedure without at least one source per step/requirement.
- [ ] Each MVP service has published procedures for all four NL consulates-general (or an explicit "not offered").
- [ ] Every source record has `licence_status` and `last_checked_at`; records past `review_due_at` are flagged.
- [ ] Change-detection job marks a record for review when the fake fetcher returns a changed hash.
- [ ] Fetcher refuses non-allow-listed hosts and private addresses.
- [ ] Retrieval returns the expected procedure in top-3 for ≥ 90% of a 60-query fixture set (NL/FR/AR).
- [ ] Only editorial-tenant members with `knowledge:publish` can publish.

## 4. Phase 4 — AI assistant

- [ ] AI stays off until the user consents; then policy enabled and use cases granted via `saas_os.inference.settings`, each with an audit row.
- [ ] Golden set (≥150 questions): ≥ 90% correct with valid citations; 0 citations to non-provided sources; ≥ 95% correct language (staging eval, report committed).
- [ ] Redaction canaries (fake passport/CNIE numbers, birth dates, emails, IBANs) never appear in the request sent to the provider (fake adapter captures requests).
- [ ] Injection fixtures: assistant never outputs non-allow-listed URLs, never requests credentials or ID numbers.
- [ ] Every `InferenceError` category maps to a defined user message (unit test over the error list).
- [ ] Quota and budget exhaustion handled without retries loops (integration test).
- [ ] p95 latency < 15 s on staging eval run (recorded).

## 5. Phase 5 — Copilot

- [ ] Pairing creates a service account with only `copilot_client`; its key gets 403 on profile, documents and billing routes.
- [ ] Revoking the device makes the next extension call fail and the panel shows "disconnected".
- [ ] Without the optional host permission, no content script runs on rdv.consulat.ma (E2E).
- [ ] No snapshot leaves the browser before the user clicks share (default) — E2E asserts no API call.
- [ ] Canary page (password, hidden CSRF token, cookie, ID number in a filled field) → none of the canaries appear in any outbound payload (E2E network capture).
- [ ] Extension makes zero requests to `rdv.consulat.ma` or the mock RDV host (E2E network capture).
- [ ] Extension never sets input values, dispatches clicks/submits or navigates (code scan test + E2E DOM mutation audit).
- [ ] Recognition: ≥ 95% of fixture pages identified; unknown page shows generic help.
- [ ] Dynamic change (validation error injected into the DOM) produces an updated snapshot within 1 s (E2E).
- [ ] Independent-assistant banner visible on every panel view (E2E).
- [ ] Server rejects snapshots exceeding size/schema limits (contract test).

## 6. Phase 6 — Advanced Copilot

- [ ] Highlight requests referencing refs not in the current snapshot are ignored and logged.
- [ ] Highlight overlay does not change any input value, focus or form state (E2E).
- [ ] Translation cache entries contain no field values (schema + test).
- [ ] Validation-error explanation covers ≥ 90% of fixture errors with correct field reference.

## 7. Phase 7 — Documents

- [ ] Only PDF/JPEG/PNG under the size cap accepted; malicious corpus rejected or neutralised.
- [ ] Stored objects are ciphertext (test reads bucket object and fails to parse as PDF/image).
- [ ] Cross-tenant download returns 404; every download writes an audit row.
- [ ] Deleting a document deletes the blob and its wrapped DEK; restore from backup cannot decrypt after key destruction (documented test).
- [ ] No document content in any LLM request by default (fake adapter capture).

## 8. Phase 8 — Commercial

- [ ] Stripe test-mode subscription moves pending → active via verified webhook.
- [ ] Entitlement-gated routes return the defined error when the plan lacks the entitlement.
- [ ] Quotas consume idempotently; exhaustion shows upgrade path.
- [ ] Prices and terms shown before payment; cancellation works (manual, recorded).

## 9. Phase 9 — Production readiness

- [ ] SaaS-OS consumer guide §15 checklist completed with evidence.
- [ ] AI qualification D1–D14 completed in staging.
- [ ] Restore drill into an isolated target succeeded; RTO/RPO measured.
- [ ] Pen test: no open high/critical findings.
- [ ] DPIA approved; privacy notice and terms published (NL/FR/AR).
- [ ] Alerts fire in a test for: 5xx rate, dead-lettered jobs, AI refusals by reason, price staleness, backup failure.
- [ ] Chrome Web Store public listing approved.
