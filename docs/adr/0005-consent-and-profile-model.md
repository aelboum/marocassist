# ADR-0005: Minimal profile, consents with audit, onboarding gate

Status: Accepted for development and closed beta (Phase 2, 2026-11-20).

## Decision

- The product stores a deliberately minimal profile per personal tenant:
  an optional display name, a consulate code, the country of residence and
  a self-declared 18+ confirmation. No birth date, nationality, civil
  status or document numbers (data minimisation; decisions P2-2, P2-4).
- The email address is never stored by MarocAssist. It lives at the
  identity provider (ZITADEL). The backend only checks that SaaS-OS marked
  the current session's address as verified (`Session.verified_email`)
  before it creates a workspace.
- Consents are one row per purpose (`privacy_notice`, `product_emails`)
  holding the current decision and version. The history of every change is
  the SaaS-OS audit log: each change writes `marocassist.consent.grant` or
  `marocassist.consent.withdraw` with `record_in_transaction` in the same
  transaction, so a change without its audit row cannot commit (tested by
  forcing the audit write to fail). Audit metadata holds purpose, version,
  granted and source only.
- The privacy notice is required. It cannot be withdrawn by a switch;
  withdrawal is account deletion. A new notice version forces a new
  acceptance before the dashboard is shown.
- Onboarding writes profile, language and both consents in one
  transaction, serialised per tenant by an advisory lock; it is idempotent.
- New permissions (`marocassist.profile`, `marocassist.consent`,
  `marocassist.account`) are granted to the `owner` role at provisioning,
  and to tenants created before Phase 2 through a declared SaaS-OS
  permission grant migration (ADR-0060 of SaaS-OS), applied by a platform
  operator.

## Rejected

- A product-side consent history table: duplicates the immutable SaaS-OS
  audit log.
- Storing the email address for product mail: not needed in Phase 2 (no
  product mail is sent); revisit with a consent-backed notification design.
- A first-login hook in SaaS-OS: it does not exist; onboarding stays an
  explicit, idempotent API call.

## Consequences

- Audit rows survive account deletion under SaaS-OS's retention policy;
  how long pseudonymous audit data may be kept is open question Q-P6 for
  counsel.
- The 18+ check is self-declared; age verification is out of scope.
