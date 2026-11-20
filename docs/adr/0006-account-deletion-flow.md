# ADR-0006: Account deletion = recorded request + operator-run purge and erasure

Status: Accepted for development and closed beta (Phase 2, 2026-11-20).
Re-assess before public launch.

## Context

SaaS-OS v0.15.0 erases a person's identity data with
`erase_user_identity` / `saas-os-operator erase-user` and removes a
tenant's data with the tenant purge (product rows through registered purge
participants). Neither has an HTTP route, and there is no product hook for
user erasure. The MVP scope accepts an operator-assisted deletion in beta.

## Decision

1. The user requests deletion in the web app
   (`POST /v1/tenants/{tenant_id}/account/deletion-request`, permission
   `marocassist.account:delete`). The request is stored once
   (`deletion_requests`, no UPDATE grant) and audited.
2. An operator carries it out within 30 days following
   `docs/runbooks/ACCOUNT_DELETION.md`: close and purge the personal tenant
   (our purge participant removes every product row), erase the identity
   with `saas-os-operator erase-user`, and delete the user at the identity
   provider.
3. The export (`GET .../account/export`) gives the user a copy of all
   product data first; identity-provider data is exported there.

## Rejected

- A product route that calls `erase_user_identity` directly: SaaS-OS
  deliberately exposes no such route and leaves authorisation to the
  operator path; adding one would bypass that control.
- Deleting rows without the SaaS-OS purge: would skip Core's own tables
  and its purge lock.

## Consequences

- Deletion is not immediate; the UI says "within 30 days" and the user can
  still sign in until then.
- Upstream proposal U-2 (product hook for user erasure) would allow full
  automation later.
