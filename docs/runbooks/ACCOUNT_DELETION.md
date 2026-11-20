# Runbook: carry out an account deletion request

Status: draft (Phase 2, 2026-11-20). **Not yet executed end to end**: it
needs an enrolled SaaS-OS platform operator, which the local stack does
not have. Each step is one SaaS-OS operator command (SaaS-OS v0.15.0,
`saas_os/ops/operator_cli.py`); verify the order on a staging copy before
the first real request (ADR-0006).

Deadline: within 30 days of the request (the UI promises this; GDPR Art. 12(3)).

## 0. Find open requests

Read-only query as the migrations role, never logging personal data:

```sql
SELECT tenant_id, requested_by, requested_at
FROM marocassist.deletion_requests ORDER BY requested_at;
```

`requested_by` is the SaaS-OS user id; `tenant_id` is their personal
tenant (also `marocassist.personal_workspaces.user_id -> tenant_id`). If a
user has no mapped tenant but a half-provisioned one exists, find it by
name: `personal-` + the first 32 hex characters of
`sha256("marocassist.personal:" + <user id>)`
(`marocassist.accounts.provisioning.personal_tenant_name`).

## 1. Erase the identity in SaaS-OS

Inside the backend container (it sets `ENVIRONMENT`; production also needs
`--confirm-production`):

```sh
saas-os-operator erase-user --user <user id> --tenant <tenant id> \
  --actor <operator user id> --confirm <user id>
```

Removes external identities, sessions, API keys (paired Copilot devices),
memberships' roles and notifications in that tenant. Re-run if it stops
part way.

## 2. Delete and purge the personal tenant

```sh
saas-os-operator delete-tenant --tenant <tenant id> --operator <operator user id> \
  --reason "DSR-<ticket>: account deletion" --confirm <tenant id>
saas-os-operator purge-tenant --tenant <tenant id> --actor <operator user id> \
  --setup marocassist.purge:register_purge_participants --confirm <tenant id>
```

The `--setup` registers MarocAssist's purge participant, which deletes the
profile, consents, deletion request, workspace settings and the
personal-workspace mapping. Never use `--no-product-participants`.

## 3. Delete the user at the identity provider

Delete the user in ZITADEL (console or management API). This removes the
email address, password and MFA factors, which MarocAssist never stores.

## 4. Record completion

Note the ticket, the date and the three command outputs (they contain
counts and ids only) in the DSR log. Audit rows remain in SaaS-OS under
its retention policy (open question Q-P6 for counsel).
