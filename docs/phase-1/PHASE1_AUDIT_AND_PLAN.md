# Phase 1 — Audit and implementation plan

Status: Phase 1 step 1 (audit), 2026-11-19. Classification as in Phase 0:
VERIFIED / PARTIALLY VERIFIED / NOT VERIFIED / RECOMMENDATION.

## 1. Repository state at the start of Phase 1

| Item | Finding | Class |
|---|---|---|
| Remote `aelboum/marocassist` | Empty (`isEmpty: true`, no default branch), visibility **PUBLIC** (`gh repo view`) | VERIFIED |
| Local clone | Branch `main`, no commits; untracked `README.md` and `docs/` (14 Phase 0 documents) | VERIFIED |
| Secrets / personal data in Phase 0 docs | Pattern scan (API-key, token, password assignments, private keys, e-mail addresses, local user paths): no hits | VERIFIED |
| Toolchain | Python 3.13.14 (`py -3.13`), uv 0.12.3, Node 24.18.0, npm 11.16.0, pnpm 12.11.2, Docker 29.8.2, Compose v5.5.1, gh 2.97.0 | VERIFIED |

## 2. SaaS-OS pin

| Check | Result | Class |
|---|---|---|
| `git ls-remote ... refs/tags/v0.15.0^{}` | `cdede956dd884fc816b234f1b546ce3b983b4efc` (annotated tag object `c3fd1b2…` peels to it) | VERIFIED |
| `saas-os` repository visibility | PUBLIC (installable over HTTPS without credentials) | VERIFIED |
| `pyproject.toml` version at the pin | `0.15.0` | VERIFIED |
| Consumer guide §14 "v0.14.0 → v0.15.0" | No migration (head `e1f5a8c3b7d9`), no new permission, new public package `saas_os.inference.settings` | VERIFIED (read at the pin) |

## 3. Phase 0 documentation review

The Phase 0 set remains valid. Deviations required by the Phase 1 brief or
found during this audit:

| # | Phase 0 statement | Phase 1 change | Reason |
|---|---|---|---|
| 1 | Backend at repository root (`src/marocassist`) | `backend/src/marocassist` | Phase 1 brief §3 prescribes `backend/` |
| 2 | D-02 packaging "default uv" | uv confirmed by owner | Phase 1 brief §2 |
| 3 | D-05 extension tooling "Phase 5" | TypeScript + Vite now | Phase 1 brief §2 |
| 4 | Compose: Postgres, Redis, ZITADEL, Mailpit, backend, worker, Caddy | Same; ZITADEL is required for the "login via SaaS-OS" requirement of work package C | SaaS-OS has no other login path (OIDC only) |
| 5 | DB role init scripts | SaaS-OS ships `01-create-app-role.sh` inside its package; Compose cannot mount a file from site-packages | Product-owned copy in `deploy/postgres/init/` (ADR-0015 rules 9-10 allow copying) |
| 6 | Extension pairing with a service-account key (Phase 0 §7) | Re-assessed in work package E with a short expiry and no self-renewal | Phase 1 brief §8 forbids a permanent, broad key |

## 4. Facts established at the pin (evidence for the design)

All read in the SaaS-OS source at `cdede95`:

- `build_platform_app()` adds `CorrelationIdMiddleware` (`X-Request-ID`), health routes and `/auth/*`; nothing else (`saas_os/api/platform.py:103`).
- Every route needs one policy: `require_permission`, `get_current_actor`/`get_current_session` (authenticated), `public_route(reason)` or platform permission (`saas_os/api/route_policy.py`).
- Session cookie lifetime 12 h (`saas_os/api/auth/routes.py:103`); login is authorization code + PKCE; the session token is never exposed to frontend code.
- Cookie-authenticated mutations must carry `Origin == PUBLIC_APP_ORIGIN` (ADR-0044, `saas_os/api/dependencies.py:336`); a request from `chrome-extension://…` therefore cannot mutate with the cookie.
- API keys (`sok_…`): stored as hash only; optional `expires_at`; revocation, expiry, inactive owner, inactive service account and tenant lifecycle are each checked at every use and denials audited (`saas_os/core/api_keys/service.py:380`).
- Service-account keys: `create_service_account_api_key(caller=UserCaller, …, expires_at=…)` requires `(api_key, create)`; a key confers only the service account's own role permissions (`service.py:296`).
- Rotation needs `(api_key, rotate)` unless the caller is the owning *user*; a service account cannot rotate its own key without that tenant-wide permission (`service.py:704`).
- A route opts in to keys with `require_permission(..., api_key=True)`; authority-changing permissions can never accept a key; keys are rate-limited per key and per tenant (consumer guide §9).
- `SystemCaller(SystemAuthority.PROVISIONING)` is documented for "a consumer's own provisioning/seed code" (`saas_os/core/authority/caller.py:40`).
- `run_inference` is non-streaming; `stream_inference` refuses every request (consumer guide §12a).

## 5. Implementation plan (order of work)

| Step | Deliverable | Evidence planned |
|---|---|---|
| A | `backend/` uv project pinned to `cdede95`; app on `build_platform_app`; settings; `/v1/meta` version route; product exception handlers; JSON logging via SaaS-OS observability; Alembic history; permissions; purge participant | unit tests, pin test, route-policy start, import-linter |
| A2 | Personal workspace provisioning (`POST /v1/workspaces/personal`, authenticated) with `SystemCaller(PROVISIONING)`; tenant-owned `marocassist.workspace_settings` with forced RLS | integration tests: provisioning idempotent, user A cannot read user B (API and predicate-free query) |
| E | Copilot pairing spike: service account + `copilot_client` role + key with ≤ 12 h expiry; `GET /v1/tenants/{t}/copilot/session` with `api_key=True`; revoke | integration tests: key works only on copilot routes, 403 elsewhere, expired/revoked key 401 |
| B | Next.js App Router skeleton: layout, nav, locale prep nl/fr/ar/en + RTL, `/auth/login` redirect, dashboard shell, API client, error/loading states | typecheck, lint, Vitest, build |
| D | MV3 extension (Vite): service worker, content script on an allow-listed local test site only, side panel, shared contracts, MutationObserver snapshot without field values | typecheck, lint, Vitest (DOM observation, panel update, manifest permission test), build |
| G | `docker-compose.yml`: db, redis, mailpit, zitadel(+db, bootstrap), backend, worker, web, edge, copilot test site; `.env.example`; health checks; volume | `docker compose up`, `/healthz`, `/readyz`, web via edge |
| F | Streaming spike report (no provider code) | document |
| Docs | Integration matrix, extension-auth report, ADRs, runbooks, Phase 1 report | review |

Nothing is pushed, merged, released or deployed. The repository stays PUBLIC.
