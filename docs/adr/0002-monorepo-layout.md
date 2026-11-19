# ADR-0002: Monorepo layout

Status: Accepted (owner, Phase 1 brief, 2026-11-19).

## Decision

One repository: `backend/` (uv project, `src/marocassist`), `web/` (Next.js
App Router), `extension/` (MV3, TypeScript + Vite), `packages/contracts/`
(OpenAPI snapshot), `knowledge/`, `deploy/`, `e2e/`, `docs/`, root
`docker-compose.yml`.

Deviation from Phase 0 (`SYSTEM_ARCHITECTURE.md` §9 proposed the backend at
the repository root): the backend lives in `backend/` as the Phase 1 brief
prescribes. No other change.

## Consequences

One review flow and one CI later; each package keeps its own lockfile
(`uv.lock`, `package-lock.json`).
