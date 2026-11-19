# SaaS-OS integration assessment

Status: Phase 0 audit, 2026-11-19. Read-only. SaaS-OS was not modified.

## 1. What was inspected

| Item | Value | Status |
|---|---|---|
| Repository | `https://github.com/aelboum/saas-os` (public), cloned fresh into a scratch directory | VERIFIED |
| Latest release | **v0.15.0**, published 2026-11-17 (GitHub Release "SaaS OS v0.15.0") | VERIFIED |
| Tag object | `c3fd1b270d5ee3cd4ae74418baa0e23811e41e1d`, peels to commit **`cdede956dd884fc816b234f1b546ce3b983b4efc`** (`git ls-remote`) | VERIFIED |
| Tag signature | `git tag -v v0.15.0`: good SSH (ED25519) signature, key `SHA256:3fTXhSPM2oxUpEzCS2/pbbOzUfkkIlsHhfHZAfZpi/c`, signer = repository owner | VERIFIED |
| Release commit = merge of PR #287 | `CHANGELOG.md` v0.15.0 entry; `git log` | VERIFIED |
| CI on release commit | GitHub Actions CI run 44171921719 (main) and Release run 44180486519: success | VERIFIED (status read via `gh run list`; logs not inspected) |
| `main` HEAD at audit time | `07aca36` (two docs-only commits after the tag: PR #289) | VERIFIED |
| `pyproject.toml` version | `0.15.0`, `requires-python >=3.13` | VERIFIED |
| Size | ~1,014 Python files; 527 `test_*.py` files; 63 ADRs | VERIFIED (counted) |
| Tests executed during this audit | **None.** No SaaS-OS test was run in Phase 0 | — |
| Open upstream issues relevant to MarocAssist | #206 streaming inference, #230 in-app notification inbox, #225 sending-domain management, #205 egress GET — all open | VERIFIED |

Method: the release metadata above was checked directly. The capability
matrix was produced by source and test inspection (two read-only code
explorations plus direct spot checks of the decisive claims: CORS absence
test, `stream_inference` refusal, image-part refusal, tool/JSON refusal,
provider-protocol check constraint, `SystemAuthority.PROVISIONING`,
`saas_os.infra.db.__all__`, scaffold imports).

### Recommended dependency pin (RECOMMENDATION)

```toml
dependencies = [
    "saas-os @ git+https://github.com/aelboum/saas-os@cdede956dd884fc816b234f1b546ce3b983b4efc",  # v0.15.0
]
```

Pin the 40-character commit SHA, never the tag or a branch (SaaS-OS ADR-0015
rule 8; `docs/CONSUMER-GUIDE.md` §3). The consumer scaffold in SaaS-OS still
pins v0.14.0 (`fb842ff`) by design (examples name the previous release).
MarocAssist should pin v0.15.0: it is the first release with the public
`saas_os.inference.settings` package, which a product needs so that a tenant
can turn AI on.

Upgrades: `saas-os-update check` (classifies changes; migrations,
authorization, tenancy, billing and unknown changes require review), then the
per-release steps in `docs/CONSUMER-GUIDE.md` §14. Support policy (ADR-0062):
the previous minor release gets security fixes for 90 days after a new
release.

## 2. Integration model (VERIFIED)

- SaaS-OS is a **Python library** installed as a pinned git dependency. One
  import root: `saas_os` (ADR-0038). MarocAssist must not name a package
  `saas_os`.
- MarocAssist owns its application entrypoint (`build_platform_app()` plus
  its own routers), its worker (`saas_os.api.worker.main(extra_functions=...)`),
  its own database schema and Alembic history (ADR-0016; SaaS-OS uses
  `alembic_version_saas_os`), its frontend (ADR-0042: no reusable frontend)
  and its deployment.
- Implied stack: **Python 3.13, FastAPI, SQLAlchemy 2 (only through
  `saas_os.infra.db`), Alembic, PostgreSQL 16, Redis 7, ARQ** (ADR-0011).
  Choosing SaaS-OS fixes the backend language.
- Every route must declare exactly one route policy; the app refuses to start
  otherwise. Tenant routes use `require_permission(resource, action)` and must
  read the tenant from `context.tenant_id`.
- Product code does not import `sqlalchemy`/`psycopg` directly; it uses the
  primitives exported from `saas_os.infra.db` (55 names in `__all__`, including
  `Base`, `mapped_column`, `select`, `update`, `delete`,
  `tenant_session_scope`, `tenant_rls_statements`). Starting point:
  `examples/consumer-scaffold/`.

## 3. Capability matrix

Classes: **A** available and reusable · **B** partially available ·
**C** missing · **D** not verified. Paths are relative to the SaaS-OS
repository.

### 3.1 Identity and access

| Capability | Class | Interface / evidence | Notes for MarocAssist |
|---|---|---|---|
| OIDC login (auth code + PKCE + nonce), sessions | A | `saas_os.api.auth.routes` (`/auth/login`, `/auth/callback`, `/auth/logout`, `/auth/me`); `saas_os.core.identity` (`issue_session`, `validate_session`, `revoke_session`, `get_or_create_user_for_external_identity`). Tests: `tests/api/auth/*`, `tests/core/identity/test_oidc*.py`, `test_auth_flow_integration.py` | Reuse as-is for the web app |
| Identity provider | A | ZITADEL v4.19.5 in `docker-compose*.yml`; `saas_os/infra/local_identity/`; runbooks; ADR-0026 (product-owned embedded login) | Self-hosted ZITADEL with Login v2 behind the single origin |
| Self-registration, password reset, email verification | C (delegated) | None in SaaS-OS; users are created just-in-time on first login. `saas_os/core/email/__init__.py` states these flows are out of scope | Configure in ZITADEL. The product never handles passwords |
| Bearer vs cookie session | A | `saas_os/api/dependencies.py` (`get_current_session`): `Authorization: Bearer <session secret>` first, then cookie | The bearer value is SaaS-OS's opaque session secret, never returned in a response body |
| Non-browser client (extension) auth | B | No device flow, no token exchange, no refresh token. ZITADEL apps are bootstrapped with the authorization-code grant only (`saas_os/infra/local_identity/zitadel_bootstrap.py`) | Product-owned extension pairing; see `BROWSER_COPILOT_ARCHITECTURE.md` §5 |
| API keys (`sok_`), service accounts | A | `saas_os.core.api_keys` (`create_api_key`, `create_service_account_api_key`, `rotate_api_key`, `revoke_api_key`); `saas_os.core.identity.create_service_account`; routes opt in with `require_permission(..., api_key=True)`, header `X-API-Key`. Tests: `tests/core/api_keys/*`, `tests/api/v1/test_api_key_request_auth_integration.py` | Basis of the extension credential. No per-key scopes: a key carries its owner's permissions, so least privilege comes from a service account with a narrow role |
| CORS | C (by decision) | No CORS middleware; `tests/api/test_cors_unit.py` asserts it is absent | The extension calls the API from its service worker under a host permission; no CORS needed |
| Same-origin check on cookie mutations (ADR-0044) | A | `saas_os/api/dependencies.py` (`_enforce_same_origin_for_cookie_mutation`); `tests/api/test_csrf_unit.py` | Applies to cookie auth only |
| MFA | B | `session.multi_factor` from the `amr` claim; enforced only for platform operators (ADR-0049) | Optional user MFA via ZITADEL; product may require it for sensitive actions |

### 3.2 Tenancy and authorization

| Capability | Class | Interface / evidence | Notes |
|---|---|---|---|
| Tenant model, lifecycle, hierarchy | A | `saas_os.core.tenancy` (`create_tenant`, `transition_tenant_status`, `TenantStatus`), max depth 6. Tests `tests/core/tenancy/*` | |
| Row-Level Security | A | `saas_os.infra.db.tenant_session_scope`, `tenant_rls_statements`; role guard refuses superuser/BYPASSRLS at startup. Tests `tests/core/tenancy/test_tenant_isolation_integration.py`, `tests/architecture/test_tenant_session_boundary.py` | Every personal-data table is tenant-owned with RLS |
| Self-service tenant creation (B2C sign-up) | B | No HTTP route. `create_tenant` accepts `SystemCaller(SystemAuthority.PROVISIONING)` for consumer provisioning code (`saas_os/core/authority/caller.py`); pattern in `saas_os/api/tenant_bootstrap.py` | MarocAssist writes an onboarding route (section 5) |
| RBAC, delegation, deny, support access | A | `require_permission`; `saas_os.core.rbac` (`register_permission`, `create_role`, `grant_permission`, `assign_role`, `can`, delegation, deny, support-access); `saas_os.core.permission_grants` (ADR-0060). 19 RBAC test files | |
| Membership / invitation routers | A (opt-in) | `saas_os.api.v1` `members_router`, `invitations_router`, `invitation_acceptance_router` | Later: family/helper accounts |
| Platform operators and admin API | A (opt-in) | `build_platform_admin_router()` + `PLATFORM_ADMIN_HTTP_ENABLED=true`; platform audit; operator MFA | MarocAssist admin UI builds on this; SaaS-OS ships no operator UI |
| Feature flags | A (library; platform-admin routes only) | `saas_os.core.feature_flags` | Gate Copilot betas per tenant |

### 3.3 Commercial

| Capability | Class | Interface / evidence | Notes |
|---|---|---|---|
| Billing (provider-abstracted) | A (Stripe) / C (others) | `saas_os.core.billing.BillingProvider`, Stripe adapter (`saas-os[stripe]`), Catalog v2 plans (`create_owned_plan`), entitlements, `build_billing_router`, payment page, Stripe events router (ADR-0048, 0052). 25 billing test files incl. Stripe integration | Stripe only; another PSP needs a product-written `BillingProvider` |
| Entitlement + quota route dependency | A | `saas_os.api.dependencies.require_entitlement_and_quota` | Plan gates for Copilot, documents |
| Usage metering, quotas | A | `saas_os.core.usage` (`ingest_event`, `check_quota`, `consume_quota_idempotent`), `usage_router` | |
| AI token quota, monthly AI budget, usage reporting | A | `saas_os.inference.settings`, `saas_os.api.v1.ai_usage` | See `AI_ARCHITECTURE.md` |

### 3.4 Audit, messaging, jobs

| Capability | Class | Interface / evidence | Notes |
|---|---|---|---|
| Tenant audit log (immutable) | A | `saas_os.core.audit_log` (`record_in_transaction`, ...); ADR-0051 | Product records consent, document access, exports |
| Platform audit log | A | `core.platform_audit_log`, `GET /v1/platform/audit` | |
| Audit digests (tamper evidence) | A | `saas_os.core.audit_digest`, worker cron, ADR-0053, `python -m saas_os.ops.audit_digest verify` | Needs an append-only external log store in production |
| Email | B | `saas_os.core.email.send_email`; providers SMTP, Resend, Mailpit (dev). **No templates, no i18n** | Product renders NL/FR/AR/EN templates |
| Notifications | B | `dispatch_notification(...)`, channels `in_app`, `email`, via outbox; no HTTP route; in-app inbox is upstream issue #230 (open) | Product builds its notification list route |
| Outbound webhooks, outbox | A | `saas_os.core.webhooks`, `saas_os.core.outbox` | Not needed for MVP |
| Background jobs | A | `saas_os.infra.jobs` (`register_tenant_job`, `register_system_job`, `enqueue_job`); `saas_os.api.worker.main(extra_functions=, extra_cron_jobs=)`; interval cron only (`system_cron` is not in `__all__`) | Freshness checks, OCR, retention |
| Idempotency | A | `saas_os.core.idempotency`, `get_idempotency_key` | |
| Rate limiting | A | `saas_os.infra.ratelimit`; built into `require_permission`, per tenant and per API key | |
| Egress control | A | `saas_os.infra.egress.StrictEgressClient`; squid proxy + unbound in prod (ADR-0059). AI egress is direct HTTPS, not via the proxy | Knowledge fetcher uses `StrictEgressClient`; GET support is issue #205 (open) — verify at implementation |

### 3.5 Security, data, operations

| Capability | Class | Interface / evidence | Notes |
|---|---|---|---|
| Secrets | B | `saas_os.infra.secrets.SecretsProvider`: `.env` file (dev) or process environment; no Vault/KMS (ADR-0012) | Acceptable on one VPS for MVP |
| Field-level encryption | A | `saas_os.core.crypto.EncryptionService` (`encrypt_str`/`decrypt_str`, AES-GCM, versioned envelope, key rotation; ADR-0019). Tests `tests/core/crypto/*` | Use for passport/CNIE numbers with `associated_data` bound to tenant and row. No blind index, no column type, no file/stream encryption |
| Security headers | B | Caddy edge sets HSTS, nosniff, Referrer-Policy; **no CSP, no X-Frame-Options** | Product adds CSP and `frame-ancestors` |
| Observability | B | Structured logs with key-based redaction, correlation IDs, OpenTelemetry tracing with `console`/`none` exporters only. **No metrics, no OTLP** | Log-based alerting for MVP |
| Retention jobs | B | Sessions, login transactions, billing events, AI attempts and rollups, idempotency/webhook/job records; audit logs never deleted | Product schedules its own retention |
| Tenant purge | A | `saas_os.core.tenancy.register_purge_participant`; `saas-os-operator purge-tenant` | Every product table covered by a participant |
| User erasure | B | `saas_os.core.identity.erase_user_identity` / `saas-os-operator erase-user`: core identity, sessions, memberships, keys, notifications only; **no product-data hook** | Product erasure = personal-tenant purge + `erase-user` |
| DSAR / data export | C | Nothing in source | Product-owned export |
| Database, migrations, roles | A | PostgreSQL 16; three roles (app with RLS enforced, migrations, platform-config); `run_core_migrations`. 73 DB test files | **No pgvector** in images or migrations |
| Full-text search primitives | C | `saas_os.infra.db.__all__` exports no `text`, `func` or `TSVECTOR` | Decision D-07 |
| Object / blob storage | C | Only `S3CompatibleBackupDestination` (backups) | Product-owned storage port (Phase 7) |
| Backups | A | `saas_os.infra.db.backup`, age encryption, optional S3 off-site copy; systemd timers in `deploy/` | Reuse; add document-store backup |
| Deployment | A | `docker-compose.prod.yml` (Postgres, Redis, backend, worker, squid egress proxy, unbound, frontend, Caddy, ZITADEL stack); single origin (ADR-0024); `saas-os-edge-config`; single VPS + systemd (ADR-0010) | Product writes its own compose file on the same pattern |
| Testing infrastructure | A | pytest markers `integration`, `packaging`, `performance`; CI jobs backend/frontend/security/docker/packaging/migrations/security-integration; scaffold integration test runs from an installed wheel | Copy the pattern |
| Frontend | C (by decision) | `frontend/` is a fixture (Next 15, React 19) with an i18n foundation for en/fr/ar incl. RTL; ADR-0042 | Copy the i18n pattern; add `nl` |

### 3.6 AI (detail in `AI_ARCHITECTURE.md`)

| Capability | Class | Evidence |
|---|---|---|
| Governed text inference (`run_inference`), multi-turn, system prompt | A | `saas_os/inference/__init__.py`; `saas_os/control_plane/inference/resolution.py` |
| Providers: Anthropic Messages, OpenAI-compatible Chat Completions, Gemini generateContent, fake | A | `saas_os/control_plane/inference/adapters/`; DB check `ck_ai_providers_protocol` allows exactly these three protocols |
| Streaming | C | `stream_inference` raises `streaming_not_enabled` (`service.py`); issue #206 open |
| Image / vision input | C | `ContentPart.kind="image"` refused (`resolution.py`, reason `part_kind`) |
| Tools / function calling, JSON output | C | Refused (`tools`, `tool_messages`, `response_format`) |
| Embeddings, vector store, RAG | C | No code; `docs/AI-INFERENCE-ROADMAP.md` AI-G "Not authorized" |
| Product-supplied provider adapter | C | No supported extension point |
| Classification + destination policy; residency/retention/training preferences | A | `resolution.py` `policy_blockers`; `config/tenant_policy.py` |
| No prompt/completion persistence | A | `control_plane.ai_inference_attempts` has no content columns |
| Quotas, budgets, concurrency, usage reporting, retention | A | `accounting.py`, `budget.py`, `admission.py`, `saas_os/api/v1/ai_usage.py`, `saas_os/inference/retention.py` |
| PII redaction, prompt-injection defences | C | Only log redaction by key name (`saas_os/infra/observability/redaction.py`) |

### 3.7 Not verified (D)

- Whether OpenTelemetry auto-instruments FastAPI.
- `StrictEgressClient.get` behaviour at v0.15.0 (issue #205 suggests GET is not yet supported for provider reads; the consumer guide documents `StrictEgressClient.get` for email reads — confirm before relying on it for the knowledge fetcher).
- Exact behaviour of a service account invoking `run_inference` against a personal tenant (documented as supported; exercise in the Phase 2 spike).
- Runtime behaviour of anything: no SaaS-OS test or container was run in Phase 0.

## 4. Gaps and how MarocAssist handles them

| Gap | Handling in MarocAssist (RECOMMENDATION) | Upstream proposal? |
|---|---|---|
| No streaming | Non-streaming answers with progress UI; tight `max_output_tokens`; short answers by design | Support #206 when the owner approves |
| No vision | Deferred (Phase 6, optional); DOM-first design makes it non-essential | Only if evidence shows DOM is insufficient |
| No embeddings / RAG | Product-owned retrieval over a curated corpus with PostgreSQL full-text search | Embeddings only on a concrete requirement |
| No FTS primitives exported | D-07: isolate raw-SQL FTS in one product module, or request exports upstream | Small proposal |
| No object storage | Product storage port + S3-compatible adapter, client-side envelope encryption | Optional |
| No DSAR export, no product erasure hook | Product export job; erasure = personal-tenant purge + `erase-user` | Yes (erasure participant hook) |
| No email templates / i18n | Product template rendering | No |
| No CSP | Product sets CSP | Possibly |
| No metrics | Log-based alerts | Later |
| No B2C sign-up route | Product onboarding route using `SystemCaller(PROVISIONING)` | No (product concern) |
| No extension auth | Product pairing flow issuing a service-account API key | Maybe later (device flow) |

Upstream changes are proposals only. MarocAssist never patches or vendors
SaaS-OS. Keep proposals in `docs/upstream/saas-os-proposals.md` (the LeadStack
precedent).

## 5. B2C tenancy mapping (RECOMMENDATION)

- **One personal tenant per user**, created idempotently by MarocAssist's
  onboarding route on first login, with the user as owner. All personal data
  (profile, conversations, page contexts, documents, preferences) is
  tenant-owned with RLS.
- This keeps SaaS-OS's isolation guarantees intact (one shared tenant for all
  consumers would put every user's data under a single RLS scope) and maps
  billing (payer = tenant), AI policy, quotas and purge one-to-one onto a
  person.
- Later, a "family/helper" plan reuses invitations: a relative joins the
  personal tenant with a limited role.
- Non-personal content (the consular knowledge base) lives in non-tenant
  tables in the product schema, written only through editorial routes
  (`DATA_ARCHITECTURE.md`).
- AI is off for every tenant until enabled (SaaS-OS default). Onboarding
  enables the tenant's AI policy and grants the MarocAssist use cases through
  `saas_os.inference.settings`, as an explicit, audited step the user agrees to.

## 6. Prior art

LeadStack (an existing SaaS-OS consumer by the same owner, local checkout)
documents its pinned interfaces in `docs/architecture/saas-os-integration.md`
and keeps upstream proposals in `docs/upstream/saas-os-proposals.md`. It pins
an older SaaS-OS commit (`b126f1a…`) that predates the `saas_os` import root,
so its import paths do not apply to v0.15.0. Copy the documentation practice,
not the imports.
