#!/usr/bin/env bash
# Creates the restricted PostgreSQL application role (NOSUPERUSER,
# NOBYPASSRLS) that DATABASE_URL points at. Row-Level Security is never
# applied to a superuser or a BYPASSRLS role, and SaaS-OS refuses to start
# the API or the worker under such a role.
#
# Product-owned copy of SaaS-OS's `saas_os/infra/db/init/01-create-app-role.sh`
# at v0.15.0 (cdede95). The installed `saas-os` wheel does not ship this
# script, so it cannot be mounted from the package (docs/phase-1/
# PHASE1_AUDIT_AND_PLAN.md, deviation 5). Added: identifier validation.
#
# Runs once, via the official postgres image's /docker-entrypoint-initdb.d
# mechanism, on the first boot of an empty data volume. Development only:
# production creates roles with its own provisioning. The password is
# never printed or persisted by this script.

set -euo pipefail

: "${APP_DB_USER:?APP_DB_USER must be set}"
: "${APP_DB_PASSWORD:?APP_DB_PASSWORD must be set}"

if ! [[ "$APP_DB_USER" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]; then
    echo "APP_DB_USER must be a plain SQL identifier." >&2
    exit 1
fi
if [[ "$APP_DB_PASSWORD" == *"'"* ]]; then
    echo "APP_DB_PASSWORD must not contain a single quote." >&2
    exit 1
fi

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    DO \$\$
    BEGIN
        IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '$APP_DB_USER') THEN
            CREATE ROLE "$APP_DB_USER" LOGIN PASSWORD '$APP_DB_PASSWORD'
                NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOREPLICATION;
        END IF;
    END
    \$\$;

    GRANT CONNECT ON DATABASE "$POSTGRES_DB" TO "$APP_DB_USER";
EOSQL
