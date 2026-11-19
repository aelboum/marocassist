# MarocAssist

Independent, commercial, multi-tenant SaaS that helps people (initially
Dutch-speaking Moroccans in the Netherlands) understand and prepare Moroccan
consular procedures. Two parts:

- **MarocAssist Web** — account, consular services catalogue, grounded AI
  assistant, appointment preparation, documents (later), billing.
- **MarocAssist Copilot** — a Chrome (Manifest V3) side panel that explains,
  translates and guides on `rdv.consulat.ma` while the user stays fully in
  control. It never submits forms, never handles CAPTCHA, never reads
  passwords, cookies or tokens, and never contacts the RDV site itself.

MarocAssist is not affiliated with the Moroccan government.

**Status: Phase 1 (technical foundation) implemented, awaiting owner review.**
See `docs/phase-1/PHASE1_REPORT.md`. Development only: nothing is deployed.

## Local development

Requirements: Docker with Compose, Python 3.13 + uv, Node 22+.

```bash
./scripts/dev-env.sh                      # creates .env with random local secrets (gitignored)
docker compose up -d --build
docker compose logs zitadel-bootstrap     # first run: copy OIDC_CLIENT_ID into .env
docker compose up -d backend worker
```

| URL | What |
|---|---|
| http://localhost:8080 | Web app + API on one origin (`/auth/*`, `/v1/*`, `/healthz`, `/readyz` → backend) |
| http://zitadel.localhost:8081 | Local identity provider (login `admin@marocassist-local.zitadel.localhost`, password in `.env`) |
| http://localhost:8090 | Copilot test website (fictitious form) |
| http://127.0.0.1:8025 | Mailpit (captured development e-mail) |

Extension: `cd extension && npm ci && npm run build`, then load `extension/dist`
as an unpacked extension (`docs/phase-1/EXTENSION_PROTOTYPE.md`).

## Tests

| Part | Commands |
|---|---|
| Backend | `cd backend && uv run ruff check src tests && uv run mypy && uv run lint-imports && uv run pytest && uv run pytest -m integration` (integration needs `docker compose up -d db redis` and `docker compose run --rm migrate`) |
| Web | `cd web && npm ci && npm run typecheck && npm run lint && npm test && npm run build` |
| Extension | `cd extension && npm ci && npm run typecheck && npm run lint && npm test && npm run build` |
| End-to-end | `cd e2e && npm ci && npx playwright install chromium && node login.e2e.mjs && node extension.e2e.mjs` (full stack running) |

## Executive summary (Phase 0, 2026-11-19)

1. **Repository state.** `aelboum/marocassist` was empty (no commits, no
   branches). This documentation set is its first content. VERIFIED.
2. **Platform.** Build on SaaS-OS **v0.15.0**, pinned to commit
   `cdede956dd884fc816b234f1b546ce3b983b4efc` (signed tag verified, CI green).
   SaaS-OS supplies identity (OIDC/ZITADEL), tenancy with PostgreSQL RLS,
   RBAC, API keys and service accounts, billing (Stripe), usage quotas,
   immutable audit with digests, jobs, email, egress control, field
   encryption, backups and governed text-only AI inference. VERIFIED in source.
3. **Gaps MarocAssist must own.** SaaS-OS inference has no streaming, vision,
   tool use, embeddings/RAG or prompt-injection defences. There is no CORS or
   device auth for extensions, no B2C sign-up route, no object storage, DSAR
   export, email templates/i18n, metrics or CSP. VERIFIED in source. How each
   is handled: `docs/architecture/SAAS_OS_INTEGRATION.md` §4.
4. **Architecture.** Modular monolith: one Python 3.13/FastAPI backend (API +
   worker) composed on SaaS-OS, a Next.js web app, a TypeScript MV3
   extension, one PostgreSQL 16 database, a single EU VPS. One personal
   tenant per user. The extension authenticates with a narrowly-scoped
   service-account API key obtained through a pairing flow. Retrieval uses
   curated, cited content with PostgreSQL full-text search. RECOMMENDATION.
5. **RDV.** No public or partner API found. Only user-controlled browser
   guidance is in scope; undocumented internal endpoints are excluded.
   rdv.consulat.ma, consulat.ma and data.gov.ma were unreachable from the
   audit environment, so their terms are NOT VERIFIED.
6. **Biggest risks.** Being perceived as an appointment broker or bot;
   reuse rights for official content (idarati.ma reserves reproduction);
   legal scope under GDPR and Moroccan Law 09-08; RDV front-end changes; the
   daily AI price confirmation that SaaS-OS budgets require.
7. **Next step.** Phase 1 (foundation) once the owner confirms the SaaS-OS
   pin (D-01) and the monorepo layout (D-03). Legal review gates the Copilot
   closed beta, not Phase 1.

## Documentation

| Area | Documents |
|---|---|
| Architecture | [System](docs/architecture/SYSTEM_ARCHITECTURE.md) · [SaaS-OS integration](docs/architecture/SAAS_OS_INTEGRATION.md) · [Browser Copilot](docs/architecture/BROWSER_COPILOT_ARCHITECTURE.md) · [AI](docs/architecture/AI_ARCHITECTURE.md) · [Security & privacy](docs/architecture/SECURITY_AND_PRIVACY.md) · [Data](docs/architecture/DATA_ARCHITECTURE.md) |
| Roadmap | [Product roadmap](docs/roadmap/PRODUCT_ROADMAP.md) · [Implementation plan](docs/roadmap/IMPLEMENTATION_PLAN.md) · [MVP scope](docs/roadmap/MVP_SCOPE.md) · [Acceptance criteria](docs/roadmap/ACCEPTANCE_CRITERIA.md) · [Risks & decisions](docs/roadmap/RISKS_AND_DECISIONS.md) |
| Research | [Official data sources](docs/research/OFFICIAL_DATA_SOURCES.md) · [RDV integration](docs/research/RDV_INTEGRATION_ASSESSMENT.md) · [External APIs](docs/research/EXTERNAL_API_REQUIREMENTS.md) |
| Phase 1 | [Report](docs/phase-1/PHASE1_REPORT.md) · [Audit and plan](docs/phase-1/PHASE1_AUDIT_AND_PLAN.md) · [SaaS-OS integration matrix](docs/phase-1/SAAS_OS_INTEGRATION_MATRIX.md) · [Extension authentication](docs/phase-1/EXTENSION_AUTH.md) · [Streaming spike](docs/phase-1/STREAMING_SPIKE.md) · [Extension prototype](docs/phase-1/EXTENSION_PROTOTYPE.md) |
| Decisions | [ADR-0001 pin](docs/adr/0001-saas-os-pin-and-boundary.md) · [ADR-0002 monorepo](docs/adr/0002-monorepo-layout.md) · [ADR-0003 personal tenant](docs/adr/0003-personal-tenant-provisioning.md) · [ADR-0004 extension credential](docs/adr/0004-extension-device-credential.md) |
| Packages | [backend](backend/README.md) · [contracts](packages/contracts/README.md) · [deploy](deploy/README.md) · [knowledge](knowledge/README.md) |

Every Phase 0 document classifies its findings as **VERIFIED**,
**PARTIALLY VERIFIED**, **NOT VERIFIED** or **RECOMMENDATION**. No tests were
executed in Phase 0. Phase 1 test results are in `docs/phase-1/PHASE1_REPORT.md` §7.
