# ADR-0003: One personal SaaS-OS tenant per user

Status: Accepted (owner decision D-06; spike result 2026-11-19).

## Decision

On the first authenticated `POST /v1/me/workspace`, the backend creates a
tenant for the verified session user with
`SystemCaller(SystemAuthority.PROVISIONING)`: tenant (random, non-personal
name) → ACTIVE → roles `owner` and `copilot_client` with their permissions →
membership → first role assignment. A global lookup row
`marocassist.personal_workspaces(user_id, tenant_id)` records the mapping.
A transaction-scoped advisory lock keyed by the user id serialises
concurrent first requests.

## Evidence

Integration tests: one workspace per user, also under 5 concurrent calls;
owner role effective through `saas_os.core.rbac.can()`; user A gets 404 on
user B's tenant.

## Consequences

- If the process dies between Core's tenant creation and the mapping
  commit, an empty tenant without a mapping remains (no product data). A
  cleanup job is a Phase 2 task.
- Permissions added to the `owner` role later must reach existing tenants
  through SaaS-OS permission grant migrations (ADR-0060 of SaaS-OS).

## Amendment (Phase 2, 2026-11-20): resumable provisioning

Phase 1 finding S-8. The tenant name is now derived from the user id
(`personal-` + 32 hex characters of a SHA-256 over the internal user id,
never an email or name), and every provisioning step checks whether it is
already done (tenant by name, roles, grants, membership, owner role). A
crash part-way is finished by the next request instead of leaving an
orphan tenant; no reaper job is needed. Concurrent provisionings per
process are bounded (2) below the database pool size, and a request that
cannot get a slot within 30 s gets a retryable 503. A workspace is only
created for a session whose email address the identity provider verified.
