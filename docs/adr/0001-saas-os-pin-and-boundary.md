# ADR-0001: SaaS-OS pin and dependency boundary

Status: Accepted (owner, Phase 1 brief, 2026-11-19).

## Decision

- Exactly one dependency on SaaS-OS: `saas-os @ git+https://github.com/aelboum/saas-os@cdede956dd884fc816b234f1b546ce3b983b4efc` (release v0.15.0). Never a branch or tag.
- `uv.lock` records the same SHA; `backend/tests/test_unit.py` fails otherwise.
- Product code imports only `saas_os.*` public modules, never `saas_os.control_plane`, and never `sqlalchemy`/`psycopg` outside migrations (tests + import-linter).
- No change to SaaS-OS itself; gaps become product code or upstream proposals.

## Consequences

Pin moves are their own pull request with `saas-os-update check` output and
the consumer-guide upgrade steps for every release in between.
