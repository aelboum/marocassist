# Phase 1 report — Technical foundation

Date: 2026-11-19. Status: **approved by the product owner on 2026-11-20**
(see §15). Pushed to `main` with the owner's permission; nothing merged,
released or deployed. Repository remains PUBLIC until MarocAssist is finished.

## 1. Executive summary

MarocAssist now has a working local foundation on SaaS-OS v0.15.0 (exact
commit pin): a FastAPI backend with personal-tenant provisioning and RLS, a
Next.js web app with real OIDC login through SaaS-OS and local ZITADEL, a
Chrome MV3 Copilot prototype that observes a local test site and updates a
side panel without reading values, and a reproducible Docker Compose stack.
The extension credential (short-lived, revocable, single-permission
service-account key) is implemented on the backend and tested; AI token
streaming is not possible on SaaS-OS v0.15.0 and is deferred. An independent
review found no critical or high issues; its medium finding and five low
findings were fixed and re-tested. Commits were first blocked: Git requires an
SSH signature; unblocked with the owner's approval (§12).

## 2. Implemented

| Work package | Result |
|---|---|
| A SaaS-OS integration | `SAAS_OS_INTEGRATION_MATRIX.md` |
| B Backend | `backend/`: config, health/readiness (SaaS-OS), `/v1` versioning, `X-Request-ID`, JSON logging, central error handling, DB + migrations, accounts, copilot pairing, purge participant, worker |
| C Web | `web/`: App Router, responsive shell, login via `/auth/login`, authenticated dashboard (overview, Copilot devices, settings), central API client, loading/error states, nl/fr/ar/en with RTL |
| D Extension | `extension/`: service worker, content script, side panel, shared contracts, local test site — `EXTENSION_PROTOTYPE.md` |
| E Extension auth | `EXTENSION_AUTH.md`, ADR-0004 |
| F Streaming spike | `STREAMING_SPIKE.md` |
| G Docker | `docker-compose.yml`, `.env.example`, `scripts/dev-env.sh`, health checks, volumes, `deploy/` |

## 3. Architecture and repository structure

```
backend/          FastAPI on SaaS-OS (uv, Python 3.13) — backend/README.md
web/              Next.js App Router + TypeScript
extension/        Chrome MV3 (TypeScript + Vite), testsite/ = local test website
packages/contracts/  OpenAPI snapshot + drift test
e2e/              Playwright browser checks against the Compose stack
knowledge/        placeholder (Phase 3)
deploy/           edge Caddyfile (from saas-os-edge-config), Postgres init
docs/             phase 0 docs, phase-1/, adr/
docker-compose.yml, .env.example, scripts/dev-env.sh
```

Runtime: one origin `http://localhost:8080` (Caddy edge) → backend for
`/auth/* /v1/* /healthz /readyz`, web for everything else; ZITADEL on
`zitadel.localhost:8081`; test site on `:8090`. All ports bound to 127.0.0.1.

## 4. SaaS-OS integration matrix

See `SAAS_OS_INTEGRATION_MATRIX.md` (capability, availability, integration,
executed test per row; findings F-1 to F-8).

## 5. Extension authentication

See `EXTENSION_AUTH.md`. Verdict: service-account key per device, role with
only `marocassist.copilot:use`, expiry ≤ 12 h (default 8 h), one opt-in
route, revocation immediate, tenant-bound, audited, max 3 devices. Residual
risk: bearer key (no sender constraint in SaaS-OS) — upstream proposal U-6.
Extension-side key delivery and storage are designed, built in Phase 5.

## 6. Streaming spike

See `STREAMING_SPIKE.md`. DOM reactivity done (297–486 ms measured).
Token streaming: SaaS-OS refuses (`streaming_not_enabled`, issue #206 open);
direct provider streaming rejected; progress-SSE possible in Phase 4; token
streaming after upstream enables it. Not in Phase 1.

## 7. Test results (all executed on 2026-11-19, Windows 11, Docker 29.8.2)

| Suite | Command | Result |
|---|---|---|
| Backend lint/format | `ruff check`, `ruff format --check` | PASS |
| Backend types | `mypy` (strict, 23 files) | PASS |
| Backend architecture | `lint-imports` (2 contracts) + AST tests | PASS |
| Backend unit | `pytest` | **21 passed** |
| Backend integration (PostgreSQL 16 + Redis 7) | `pytest -m integration` | **18 passed** (on a freshly recreated database) |
| Backend dependency audit | `pip-audit` | 0 known vulnerabilities (saas-os and marocassist not auditable on PyPI) |
| Web | `tsc --noEmit`, `eslint`, `vitest` | PASS, **11 passed** |
| Web build | `next build` (and Docker image) | PASS |
| Extension | `tsc --noEmit`, `eslint`, `vitest` | PASS, **45 passed** |
| Extension build | `npm run build` | PASS (`dist/` with manifest check) |
| npm audit | web, extension, e2e | 0 vulnerabilities |
| Compose | `docker compose down -v`, new `.env`, `up -d --build` | All 11 services up; 10 healthy (test site has no health check) |
| Smoke via edge | curl `/healthz` `/readyz` `/v1/meta` `/auth/me` `/auth/login` | 200 / 200 / 200 / 401 / 303 to ZITADEL with PKCE S256 |
| E2E login (Chromium) | `e2e/login.e2e.mjs` | **11 passed** |
| E2E extension (Chromium) | `e2e/extension.e2e.mjs` | **11 passed** |
| Secret scan | env values + key patterns + personal data over 114 commit candidates | 0 hits |
| Independent review | security reviewer agent, fresh context | 0 critical, 0 high; 1 medium + 6 low (§8) |

Not tested: rate limiting under load; email delivery (Mailpit only
configured); real Chrome (stable) with the unpacked extension and the
permission prompt (Chromium via Playwright used, with a test copy whose
manifest pre-grants the test-site permission); full operator `purge_tenant`
flow (participant tested directly); CI (no CI pipeline in Phase 1).

## 8. Security findings

| # | Severity | Finding | Status |
|---|---|---|---|
| S-1 | Medium | Compose loaded the whole `.env` into API/worker (migration role, ZITADEL master key, admin password) | **Fixed**: per-service `environment` lists; verified the API container no longer sees them |
| S-2 | Low | Device limit race (check then create) | **Fixed**: per-tenant advisory lock; concurrency test (5 threads → 2 paired, 3 refused) |
| S-3 | Low | Echoed identifiers in page text not masked (5-digit fragment) — found by E2E | **Fixed**: masking of e-mail, phone, tokens with 3+ digits; tests |
| S-4 | Low | URL path could carry identifiers into the snapshot | **Fixed**: path segments masked; test |
| S-5 | Low | Label/alert text could include prefilled controls or editable regions | **Fixed**: `staticText()` strips controls and `contenteditable`; test |
| S-6 | Low | Every `PermissionError` (also OS-level) mapped to 403 | **Fixed**: only SaaS-OS refusals → 403; test |
| S-7 | Low | `.env` briefly world-readable at creation | **Fixed**: `umask 077` |
| S-8 | Low | Provisioning holds a pooled connection while Core calls run; orphan tenant on crash | **Open** (Phase 2: short lock session, bounded concurrency, reaper job) |
| S-9 | Low | Disabled device service accounts accumulate; device listing unbounded | **Open** (Phase 5 cleanup job) |
| S-10 | Info | Web has no `script-src`/`default-src` CSP yet | **Open** (Phase 2, nonce-based CSP) |
| S-11 | Info | Dev-only: Redis without password, Mailpit without auth, bootstrap volume 0777 with a ZITADEL PAT — all loopback-only | Accepted for development; never in production |
| S-12 | Info | Names echoed in page text cannot be masked reliably | Accepted; consent + preview before any page text leaves the browser (Phase 5) |

## 9. Open issues

1. Resolved: commit signing (§12).
2. S-8, S-9, S-10 above.
3. Owner permissions added later need SaaS-OS permission grant migrations (F-7); `api_key:revoke` was added during Phase 1 — existing dev tenants were recreated, no production tenants exist.
4. `OIDC_CLIENT_ID` must be copied from the bootstrap log once per fresh stack (SaaS-OS tooling prints it; automation possible in Phase 2).
5. No CI pipeline yet (planned PR 1.4 of the implementation plan); all checks were run locally.
6. ESLint 10 is installed with `eslint-config-next` 16.4.6, whose plugins declare older ESLint peers (npm `ERESOLVE overriding peer dependency`); lint passes.

## 10. Deviations from Phase 0

| Phase 0 | Phase 1 | Why |
|---|---|---|
| Backend at repository root | `backend/` | Phase 1 brief (ADR-0002) |
| Extension stack decided in Phase 5 | TypeScript + Vite now, no framework | Phase 1 brief |
| Extension: `activeTab` + optional host permission, `externally_connectable` | Phase 1: `sidePanel`, `storage`, `scripting` + optional host permission for the test site; no `externally_connectable` yet (needed only for pairing in Phase 5) | Least privilege for what Phase 1 does |
| Extension key "narrow service-account key" | Same, plus ≤ 12 h expiry, device limit, no self-rotation | Phase 1 brief §8 |
| DB init scripts from SaaS-OS | Product-owned copy | Not shipped in the wheel (F-1) |
| `e2e/` not planned | Added | Browser evidence for login and extension |
| Implementation plan PR 1.4 (CI), 1.10 (runbooks) | Not done | Time; listed as open |

## 11. Changed files

All files are new except `README.md` and
`docs/architecture/SYSTEM_ARCHITECTURE.md` (§9 note). New: `.gitignore`,
`.env.example`, `docker-compose.yml`, `scripts/dev-env.sh`, `backend/**`
(source, tests, `pyproject.toml`, `uv.lock`, `Dockerfile`), `web/**`,
`extension/**` (incl. `testsite/`), `e2e/**`, `packages/contracts/**`,
`deploy/**`, `knowledge/README.md`, `docs/phase-1/**`, `docs/adr/**`.
Phase 0 documents are unchanged apart from the note above.

## 12. Commit overview

Signed commits on `main`, pushed to `origin/main` on 2026-11-20 with the
owner's permission. Signing was unblocked
after the owner's approval by pointing this repository's Git at the Windows
OpenSSH `ssh-keygen` (`git config --local gpg.ssh.program`), which uses the
key already loaded in the Windows ssh-agent. Signing was never bypassed.

1. `docs: Phase 0 architecture audit and roadmap`
2. `chore: repository baseline and Phase 1 audit`
3. `feat(backend): SaaS-OS pinned FastAPI foundation, accounts and migrations`
4. `feat(backend): Copilot device pairing with short-lived keys`
5. `test(backend): unit and integration tests, OpenAPI contract`
6. `feat(web): Next.js shell, login and dashboard`
7. `feat(extension): MV3 side panel prototype and local test site`
8. `feat(dev): Docker Compose stack, edge and local identity`
9. `test(e2e): browser checks for login and extension`
10. `docs: Phase 1 reports, ADRs and READMEs`
11. `docs: record signed commit history in the Phase 1 report`
12. `docs: record owner approval of Phase 1`

## 13. Phase 1 acceptance criteria

| Criterion | Status | Evidence |
|---|---|---|
| SaaS-OS v0.15.0 exactly pinned | PASS | pin tests, `uv.lock` |
| SaaS-OS integration demonstrably works | PASS | integration matrix, 18 integration tests, E2E login |
| Backend starts locally | PASS | Compose healthy, `/readyz` 200 |
| Web app starts locally | PASS | Compose healthy, E2E |
| Chrome extension works locally | PASS (Chromium via Playwright) | `extension.e2e.mjs`; manual load in Chrome stable NOT TESTED |
| Side panel reacts to DOM changes | PASS | 297–486 ms in E2E; unit tests |
| Prototype works on a local test website | PASS | E2E |
| Extension authentication securely designed and justified | PASS | `EXTENSION_AUTH.md`, 6 integration tests |
| Streaming research complete | PASS | `STREAMING_SPIKE.md` |
| Docker Compose works reproducibly | PASS | `down -v` + new `.env` + `up --build`; one documented manual step (client id) |
| Database connection and migrations work | PASS | migrations idempotent; heads verified |
| Tenant isolation tested | PASS | API 404 matrix, predicate-free RLS query, E2E 404 |
| Security rules tested | PASS | extension security tests, canary E2E, cookie origin test, review |
| All executed tests reported | PASS | §7 |
| Documentation updated | PASS | §2, README |
| No unresolved critical or high security issues | PASS | review: 0 critical/high; medium fixed |

## 14. Advice for Phase 2

1. Set up CI (backend, web, extension, integration, E2E) and branch protection.
2. Nonce-based CSP for the web app; CSRF review of all cookie mutations.
3. Provisioning hardening (S-8): short lock session, reaper for orphan tenants, ADR-0060 grant-migration module.
4. Sign-up/verification flow and consent records (Phase 2 scope of the roadmap); purge flow through the operator command.
5. Automate `OIDC_CLIENT_ID` handover in the dev stack.
6. Keep the repository decision: make it private after this review, as planned.

## 15. Owner decision

- 2026-11-20: the product owner approved Phase 1 ("akkoord phase 1").
- 2026-11-20: the owner gave permission to push to `main`.
- Repository visibility: stays PUBLIC until MarocAssist is finished; the
  owner decides then. No visibility change without explicit owner consent.
- Open review findings S-8, S-9 and S-10 (§8, §9) move to Phase 2.
