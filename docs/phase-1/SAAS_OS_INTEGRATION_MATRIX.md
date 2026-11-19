# SaaS-OS integration matrix (Phase 1)

SaaS-OS v0.15.0, commit `cdede956dd884fc816b234f1b546ce3b983b4efc`, installed
from `backend/uv.lock`. "Available" means read in the source at the pin.
"Test evidence" names a test that was **executed** on 2026-11-19 (results in
`PHASE1_REPORT.md` §7); "source only" means not exercised by a MarocAssist test.

| Capability | SaaS-OS available | MarocAssist integration | Test evidence |
|---|---|---|---|
| Pin | `saas-os @ git+…@cdede95…`; tag `v0.15.0^{}` resolves to it | `backend/pyproject.toml`, `uv.lock` (`?rev=…#…`) | `test_saas_os_is_pinned_to_the_exact_release_commit`, `test_lockfile_resolves_saas_os_to_the_same_commit`, `test_installed_saas_os_is_v0_15_0` |
| Authentication / OIDC | Yes: `/auth/login` (code + PKCE S256), `/auth/callback`, `/auth/me`, `/auth/logout`; local ZITADEL via `saas-os-local-identity` | `build_platform_app()`; ZITADEL v4.19.5 in Compose; web links to `/auth/login` | E2E `login.e2e.mjs`: redirect to ZITADEL, callback to `/dashboard`, sign-out → `/auth/me` 401; curl: 303 with `code_challenge_method=S256` |
| Session management | Yes: opaque session secret, HttpOnly cookie, 12 h, hashed at rest; Bearer header accepted | Web never handles a token; relative same-origin fetches | E2E: cookie HttpOnly + SameSite=Lax, not visible to `document.cookie`; integration tests use `issue_session` Bearer |
| Same-origin mutation guard (ADR-0044) | Yes, cookie mutations need `Origin == PUBLIC_APP_ORIGIN` | Inherited on every product route | `test_cookie_mutation_from_extension_origin_is_refused` (403) |
| Tenant isolation / RLS | Yes: `tenant_session_scope`, `tenant_rls_statements`, startup refuses a BYPASSRLS role | `marocassist.workspace_settings` with forced RLS; app role `marocassist_app` NOSUPERUSER NOBYPASSRLS | `test_user_a_cannot_read_or_write_user_b_workspace`, `test_rls_hides_other_tenants_rows_without_a_predicate`, `test_application_role_cannot_bypass_rls`; `pg_class.relforcerowsecurity = t` checked |
| Personal tenant per user | No sign-up route; `SystemCaller(PROVISIONING)` documented for consumer provisioning | `accounts/provisioning.py`, advisory lock per user | `test_first_request_provisions_exactly_one_personal_workspace`, `test_concurrent_provisioning_creates_one_tenant`, `test_owner_role_is_assigned` |
| RBAC / permissions | Yes: catalog, roles, `require_permission`, anti-amplification | `marocassist.workspace:{read,update}`, `marocassist.copilot:{pair,use}`; roles `owner`, `copilot_client` | Integration tests (403/404 matrix); `test_every_route_declares_a_saas_os_route_policy` |
| Route policy (fail closed) | Yes: app refuses to start with an undeclared route | Every route declares `require_permission`, authenticated or `public_route` | `test_every_route_declares_a_saas_os_route_policy`; lifespan runs in integration tests |
| Audit logging | Yes: Core writes audit rows in the same transaction | Provisioning, pairing and revocation audited by Core | `test_pairing_and_revocation_are_audited` (`service_account.create`, `api_key.create`, `service_account.disable`) |
| API keys / service accounts | Yes: `sok_` keys hashed, optional `expires_at`, revocation, per-route opt-in `api_key=True` | Copilot device pairing (`copilot/devices.py`) | `test_paired_key_is_short_lived_and_reaches_only_the_copilot_route`, `test_device_key_is_bound_to_its_tenant`, `test_revoked_device_key_stops_working_immediately`, `test_expired_device_key_is_refused`, `test_device_limit_is_enforced` |
| Rate limiting | Yes: per tenant and per key in `require_permission`; failed-credential limit; auth route limit | Inherited, no product tuning | Source only (not load-tested) |
| Quotas / entitlements | Yes: `require_entitlement_and_quota`, `consume_quota` | Not used in Phase 1 (billing is Phase 8) | Not tested |
| Background jobs | Yes: ARQ worker, `register_tenant_job`, `extra_functions` | `marocassist.worker` wraps SaaS-OS worker; no product job yet | Compose: `worker` healthy (`--check` probe) |
| Email | Yes: SMTP / Mailpit / Resend, outbox | `EMAIL_PROVIDER=mailpit` in dev | Worker starts with the email config validated (healthy); no mail sent by MarocAssist |
| Outbound network control | Yes: `StrictEgressClient`, egress proxy | Not used (no outbound calls in Phase 1) | Not tested |
| AI inference governance | Yes: `run_inference` (non-streaming), use-case registry, classification, budgets; `stream_inference` refuses | Not used in Phase 1 (`STREAMING_SPIKE.md`) | Source only |
| Configuration and secrets | Yes: secrets provider (`.env` in development, process env otherwise); `ENVIRONMENT` required | `.env.example` with `__GENERATE__` placeholders, `scripts/dev-env.sh`; product tunables in `marocassist/config.py` (bounded) | `test_copilot_key_ttl_is_bounded`; secret scan of commit candidates (0 hits) |
| Migrations | Yes: `run_core_migrations()`, separate `alembic_version_saas_os` | `python -m marocassist.migrate` (SaaS-OS, then product, then permissions) | `test_migrations_are_idempotent`; DB shows `e1f5a8c3b7d9` + `0001_marocassist_accounts` |
| Health / readiness | Yes: `/healthz`, `/readyz` (DB + Redis) | Via edge and Compose healthcheck | `test_health_and_readiness`; curl through edge: 200/200 |
| Correlation id | Yes: `X-Request-ID` middleware, JSON logs | Product errors carry `request_id` | `test_meta_is_public_and_returns_constants_only`, `test_request_id_is_propagated` |
| Purge | Yes: purge participants | `AccountsPurgeParticipant` | `test_purge_participant_removes_only_the_purged_tenant` (participant called directly; full `purge_tenant` operator flow not run) |
| Single-origin edge | Yes: `saas-os-edge-config` | `deploy/edge/Caddyfile` emitted from the pin | Compose: edge healthy; E2E runs through `localhost:8080` |
| CORS | None, by design | Not added | E2E: cross-origin call to `localhost:8000` blocked |

## Missing in SaaS-OS v0.15.0 (findings, no workaround that weakens security)

| # | Finding | Impact | Handling |
|---|---|---|---|
| F-1 | DB role init script is not shipped in the wheel | Product copies it | `deploy/postgres/init/01-create-app-role.sh` (product-owned) |
| F-2 | No self-service sign-up / first-login hook | Product provisions with `SystemCaller(PROVISIONING)` | `accounts/provisioning.py`; orphan tenant possible on a crash between Core calls and the mapping commit (documented) |
| F-3 | No device-authorization or token-exchange flow; API keys are bearer keys without sender constraint | Extension uses a short-lived service-account key | `EXTENSION_AUTH.md`; upstream proposal U-6 refined there |
| F-4 | Service-account keys are not counted by `API_KEY_MAX_PER_USER` | Unlimited devices unless the product limits them | `MAROCASSIST_COPILOT_MAX_DEVICES` (default 3) |
| F-5 | No streaming inference (`streaming_not_enabled`, issue #206 open) | No token streaming | `STREAMING_SPIKE.md` |
| F-6 | No FTS primitives exported from `saas_os.infra.db` (Phase 0 D-07) | Knowledge retrieval (Phase 3) | Unchanged; upstream proposal U-1 |
| F-7 | Permissions added in a later release are not granted to existing tenants automatically | New owner permissions need ADR-0060 grant migrations | Required from the first production tenant on; noted in `PHASE1_REPORT.md` |
| F-8 | Session cookie name defaults to `saas_os_session` | Cosmetic | `AUTH_COOKIE_NAME` can be set; left default |
