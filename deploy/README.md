# deploy/

Development-only infrastructure configuration used by `docker-compose.yml`.

| Path | Purpose |
|---|---|
| `edge/Caddyfile` | Single-origin local edge, emitted by `saas-os-edge-config` from the pinned SaaS-OS package (product-owned copy) |
| `postgres/init/01-create-app-role.sh` | Creates the restricted `NOSUPERUSER NOBYPASSRLS` application role on first boot |

There is no production deployment in Phase 1. Production edge, TLS, secrets
and backups are Phase 9 work.
