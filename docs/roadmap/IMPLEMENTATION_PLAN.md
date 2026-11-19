# Implementation plan

Status: Phase 0, 2026-11-19. Describes *how* phases are executed, and breaks
the next phase (Phase 1) into reviewable pull requests. Later phases are
broken down at their own kickoff, following the same process.

## 1. Delivery process (per phase)

1. **Scope** — phase issue listing scope, out-of-scope, acceptance criteria
   (from `ACCEPTANCE_CRITERIA.md`), decisions needed.
2. **Dependencies** — confirm decisions and upstream pins; record blockers.
3. **Tasks** — one GitHub issue per PR-sized task (≤ ~400 changed lines of
   non-generated code where practical).
4. **Implement** — branch per task (`feat/…`, `fix/…`, `docs/…`), never on
   `main`; conventional commits.
5. **Local checks** — `scripts/check-all.sh` (lint, format, types, unit,
   architecture, security) and `scripts/check-integration.sh` when DB-related.
6. **CI** — same scripts; required checks on `main`.
7. **Independent review** for security-sensitive PRs (auth, permissions,
   extension permissions/extraction, AI prompts/redaction, crypto, documents,
   billing): a second reviewer or a review agent started without the
   author's context; findings recorded in the PR.
8. **Document** — update architecture docs/ADRs/runbooks in the same PR.
9. **Approval** — owner approves and merges. No auto-merge.

No extra governance: no change advisory boards, no external audits except the
single pre-launch pen test (D-14). Prefer tests over checklists.

## 2. Branching, versioning, releases

- Trunk-based: short-lived branches into protected `main`.
- Versions: `0.y.z` until public launch; tag on owner approval.
- Extension versions independent (`extension/manifest.json`), released through
  the Chrome Web Store after the backend version that supports them is live.
- SaaS-OS pin moves are their own PRs with `saas-os-update check` output.

## 3. Test strategy

| Layer | Backend | Web | Extension |
|---|---|---|---|
| Unit | pytest (hermetic, no services) | Vitest | Vitest + jsdom |
| Integration | pytest `-m integration` with disposable PostgreSQL 16 + Redis 7 (CI service containers; unique DB per run) | — | — |
| Architecture | import-linter, route-policy, pin test | eslint boundaries | manifest snapshot |
| Contract | OpenAPI schema snapshot | generated types compile | message schemas |
| E2E | — | Playwright against Compose stack | Playwright with unpacked extension against mock RDV site |
| Security | pip-audit, detect-secrets, redaction canaries, isolation tests | npm audit | npm audit, payload canaries |
| AI eval | fake-provider structural tests (CI); real-provider eval (scheduled, staging) | — | injection fixtures |

Rule: never run tests against the real rdv.consulat.ma, real official sites,
or production services from CI.

## 4. Phase 1 work breakdown (next phase)

| # | PR | Content | Depends on | Size |
|---|---|---|---|---|
| 1.1 | `chore: repository baseline` | README, LICENSE decision placeholder (owner), `.gitignore`, `.editorconfig`, PR template with security checklist, CODEOWNERS, `CLAUDE.md` | — | S |
| 1.2 | `docs: ADR-0001..0004` | SaaS-OS pin/boundary, monorepo, tenancy mapping, extension auth (status Proposed until spike) | 1.1 | S |
| 1.3 | `feat(backend): package skeleton` | `pyproject.toml` (pinned SaaS-OS SHA), lockfile, `src/marocassist/{app,worker,migrate,permissions}.py` from scaffold, empty migrations history, ruff/pyright/import-linter config, pin test | 1.1, D-01, D-02 | M |
| 1.4 | `ci: backend + security + migrations + integration jobs` | GitHub Actions mirroring SaaS-OS jobs; `scripts/check-*.sh` | 1.3 | M |
| 1.5 | `feat(dev): compose stack` | Postgres, Redis, ZITADEL (+ login), Mailpit, backend, worker, Caddy single origin (`saas-os-edge-config`), `.env.example` | 1.3 | M |
| 1.6 | `feat(web): Next.js skeleton` | App Router, i18n nl/fr/ar/en with RTL, CSP headers, login redirect, health page; `scripts/check-web.sh`; CI job | 1.4 | M |
| 1.7 | `feat(extension): MV3 skeleton` | Manifest (minimal permissions), side panel hello, service worker, build, manifest snapshot test, CI job | 1.4 | S |
| 1.8 | `spike: SaaS-OS integration` | Throwaway branch: personal tenant provisioning, service-account key route, fake-provider `run_inference`; findings → ADR-0003/0004 Accepted or revised | 1.3, 1.5 | M |
| 1.9 | `feat(contracts): OpenAPI → TS types` | `packages/contracts` generation + drift check | 1.6, 1.7 | S |
| 1.10 | `docs: runbooks (dev setup, upgrade SaaS-OS)` | | 1.5 | S |

Exit: all Phase 1 acceptance criteria met; owner approval.

## 5. Inputs needed from the owner before/early in Phase 1

1. Confirm D-01 (pin v0.15.0) and D-03 (monorepo).
2. Confirm or override D-02 (uv) and D-04 (Next.js).
3. Licence choice for the repository (the GitHub repo is currently **public**;
   decide whether it should be private before code lands).
4. Domain/brand direction (D-09) for staging (can wait until end of Phase 1).
5. Start legal counsel engagement (D-18) in parallel; it gates the closed beta,
   not Phase 1.
6. Manual evidence capture of official sites (`../research/*`, follow-up
   sections).
