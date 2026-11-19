# MarocAssist backend

Python 3.13 + FastAPI modular monolith on SaaS-OS v0.15.0
(`cdede956dd884fc816b234f1b546ce3b983b4efc`, pinned in `pyproject.toml` and
`uv.lock`). SaaS-OS supplies identity, sessions, tenancy with PostgreSQL RLS,
RBAC, API keys, audit, jobs, email and health; this package adds the product.

## Layout

| Module | Role |
|---|---|
| `marocassist/app.py` | Entry point: `build_platform_app()` + product routers + exception handlers |
| `marocassist/config.py` | Bounded product settings (`MAROCASSIST_*`); secrets stay in SaaS-OS's provider |
| `marocassist/errors.py` | Central exception handling (no input echo, no internals) |
| `marocassist/permissions.py` | Product permissions and the `owner` / `copilot_client` roles |
| `marocassist/accounts/` | Personal workspace (one tenant per user) and workspace settings |
| `marocassist/copilot/` | Extension device pairing (service account + short-lived key) |
| `marocassist/api/meta.py` | `GET /v1/meta` (public, constants only) |
| `marocassist/migrations/` | Product Alembic history (`alembic_version`) |
| `marocassist/migrate.py` | SaaS-OS migrations → product migrations → permissions |
| `marocassist/worker.py`, `jobs.py` | SaaS-OS worker with product jobs (none yet) |
| `marocassist/purge.py` | Tenant purge participant |

Rules (checked by tests and import-linter): no `saas_os.control_plane`
imports; no `sqlalchemy`/`psycopg` outside migrations; no raw SQL helpers;
every route declares a SaaS-OS route policy; every product route under `/v1`.

## Run and test

```bash
uv sync --locked                       # Python 3.13, dev tools included
uv run ruff check src tests && uv run ruff format --check src tests
uv run mypy                            # strict
uv run lint-imports
uv run pytest                          # unit tests, no services needed
docker compose up -d db redis          # from the repository root
docker compose run --rm migrate
uv run pytest -m integration           # PostgreSQL 16 + Redis 7 (127.0.0.1:5433 / :6380)
uv run pip-audit
uv run python -m tests.export_openapi  # after an intended API change
```

Integration tests read the generated local credentials from the repository
`.env` (created by `scripts/dev-env.sh`, never committed).
