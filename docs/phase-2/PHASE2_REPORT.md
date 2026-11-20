# Phase 2 report — Identity and SaaS foundation

Date: 2026-11-20. Status: implemented on the local branch `phase-2`
(signed commits, not pushed), **awaiting owner review**. Nothing merged,
released or deployed. Repository remains PUBLIC (owner decision: until
MarocAssist is finished). Plan: `PHASE2_AUDIT_AND_PLAN.md`.

## 1. Executive summary

A person can now create a MarocAssist account through the local identity
provider, confirm their email address with a code, complete a minimal
onboarding (optional name, consulate, 18+, privacy notice, optional
product emails), edit their profile and consents, download their data,
request deletion and sign out. Every consent, profile, onboarding, export
and deletion action is audited by SaaS-OS in the same transaction, without
personal values. Three Phase 1 findings are closed (S-8, S-9, S-10), CI is
defined for the first time, and an independent security review found no
critical or high issues; its two medium findings were fixed. One new
medium finding is open (P2-F1: signing out does not end the identity
provider's session).

## 2. Implemented

| WP | Result |
|---|---|
| A CI | `.github/workflows/ci.yml`: backend (ruff, format, mypy strict, import-linter, unit + OpenAPI drift), integration (PostgreSQL 16 + Redis 7, restricted app role), web, extension, security (pip-audit, npm audit, gitleaks over full history). Read-only token, no secrets, actions pinned by SHA, images by digest |
| B Account lifecycle | Local ZITADEL: self-registration, email verification code and password-reset mail to Mailpit, MFA offered not forced |
| C Onboarding and profile | Workspace only for a verified email (`Session.verified_email`); onboarding in one transaction; `profiles` table (display name, consulate code, country, 18+) |
| D Consents | `consents` table, purposes `privacy_notice` (required) and `product_emails` (optional), versioned; audit row per change in the same transaction; changed notice forces re-acceptance |
| E Account rights | `GET account/export` (JSON download), `POST account/deletion-request` (recorded once, audited, unpairs all Copilot devices at once); operator runbook |
| F Devices page | Web list and unpair on the Phase 1 API |
| G Phase 1 findings | S-8 resumable provisioning + bounded concurrency; S-9 revoked devices hidden, lifetime pairing cap; S-10 nonce CSP |
| H Tests | See §7 |
| I Docs | ADR-0005, ADR-0006, ADR-0003 amendment, runbook, draft privacy notice (in the app), this report, README |

## 3. Architecture changes

- New product tables (migration `0002_marocassist_profile`): `profiles`,
  `consents`, `deletion_requests`; forced RLS through
  `tenant_rls_statements`; `deletion_requests` has no UPDATE grant.
- New module `marocassist.privacy` composes `accounts` and `copilot` (export,
  deletion request); the two feature modules stay independent (import-linter).
- New permissions `marocassist.profile:{read,update}`,
  `marocassist.consent:{read,update}`, `marocassist.account:{onboard,export,delete}`
  for `owner`; declared SaaS-OS grant migration
  `0001_owner_profile_consent_account` for tenants created before Phase 2.
- Web: `proxy.ts` (Next 16 proxy) sets the CSP; new pages profile, account,
  privacy; session states unverified / onboarding / notice / ready.

## 4. SaaS-OS usage (published interfaces only, no bypass)

`get_current_session().verified_email`, `record_in_transaction` with
`UserCaller`, `require_permission`, `tenant_session_scope`,
`acquire_tenant_advisory_lock`, `acquire_global_advisory_lock`,
`find_tenants_by_name`, `get_membership`, `list_membership_roles`,
`get_role_permission`, `enforce_rate_limit`, `PermissionGrantMigration`,
`/auth/logout`. No identity data stored by the product; no second identity
system.

## 5. Security findings

Independent review of `main..phase-2` (read-only agent, 2026-11-20): 0
critical, 0 high.

| ID | Sev. | Finding | Status |
|---|---|---|---|
| R2-1 | Medium | `/v1/me/workspace` had no rate limit (per-tenant limit cannot apply before a tenant exists); 30 s blocking slot wait | **Fixed**: per-user SaaS-OS rate limit (tested), wait 5 s |
| R2-2 | Medium | Deletion request left Copilot device keys usable until the operator acts | **Fixed**: request unpairs all devices at once (tested); UI says so |
| R2-3 | Low | Export audit row in its own transaction after the read | Accepted: fails closed (no data on audit failure) |
| R2-4 | Low | CI checkout kept the job token on disk | **Fixed** (`persist-credentials: false`) |
| R2-5 | Low | CI images pinned by tag | **Fixed** (digest) |
| R2-6 | Low | `cancel-in-progress` also cancelled `main` runs | **Fixed** (pull requests only) |
| R2-7 | Low | No HSTS in web headers | Open: belongs to the TLS edge in production (dev is HTTP) |
| R2-8 | Info | Logs carry tenant ids (pseudonymous, 1:1 with users) | Accepted |
| R2-9 | Info | Concern that 422 echoes input | Not applicable: product handler returns locations/types only (unit + integration tests) |
| P2-F1 | **Medium** | Sign-out revokes the MarocAssist session but not the ZITADEL session; "sign in" on the same browser returns without a password (shared computers) | **Open**. Observed in E2E. SaaS-OS v0.15.0 has no RP-initiated logout and the local identity tooling registers no post-logout URI. Fix needs an upstream SaaS-OS change (proposal U-4) or an identity-provider setting; not worked around in product code |
| P2-F2 | Low | Open self-registration can create many tenants (one per verified address) | Open for production: needs registration protection at the identity provider (rate limit / bot protection) before public launch |

## 6. Phase 1 findings

| ID | Status |
|---|---|
| S-8 | **Closed**: deterministic opaque tenant name, every step idempotent, crash resumed (integration test), concurrency bounded with 503 (unit test) |
| S-9 | **Closed**: revoked devices hidden; lifetime cap `MAROCASSIST_COPILOT_MAX_DEVICE_HISTORY` (default 50) with `device_history_full` (test); SaaS-OS has no service-account delete, the tenant purge removes them |
| S-10 | **Closed**: nonce + `strict-dynamic` CSP, no `unsafe-inline`, `unsafe-eval` only in `next dev`; E2E checks the header, a fresh nonce per request and zero browser CSP violations |

## 7. Test results (all executed on 2026-11-20, Windows 11, Docker)

| Suite | Result |
|---|---|
| Backend lint/format/mypy strict/import-linter | pass |
| Backend unit (incl. generated 401 matrix over every product route, OpenAPI drift) | 28 passed |
| Backend integration on a fresh PostgreSQL 16 (CI emulation) and on the Compose DB | 38 passed |
| Web typecheck, lint, tests, build | 17 tests passed; build ok (all routes dynamic, proxy active) |
| Extension lint, tests, build | 45 passed (Phase 1 suite unchanged), build ok |
| E2E `login.e2e.mjs` | 12/12 |
| E2E `signup.e2e.mjs` (sign-up → Mailpit code → onboarding → profile → consent → export → deletion → sign-out → dead session → reset mail → CSP → log scan) | 20/20 |
| E2E `extension.e2e.mjs` | 11/11 |
| pip-audit (all locked PyPI packages), npm audit web + extension | 0 vulnerabilities |
| gitleaks over the full Git history | no leaks |

E2E ran in Playwright Chromium, not Chrome stable. CI has **not** run on
GitHub: it runs only after a push, which needs owner permission.

## 8. Phase 2 acceptance criteria

| # | Criterion | Status | Evidence |
|---|---|---|---|
| 1 | Sign up, verify email, log in, log out | PASS (local) | `signup.e2e.mjs`; staging NOT TESTED (no staging) |
| 2 | First login creates exactly one personal tenant, also concurrently | PASS | integration: provisioning, concurrency, crash-resume |
| 3 | Every product route: 401 / 403 / 404 | PASS | unit 401 matrix (OpenAPI-generated); integration 403 (member without role) and 404 (other user's tenant) over 14 routes |
| 4 | Every tenant table isolated without predicate | PASS | integration: `workspace_settings`, `profiles`, `consents`, `deletion_requests` |
| 5 | Consent change audited in the same transaction | PASS | integration: forced audit failure rolls the change back |
| 6 | Purge removes all product rows; participant names asserted | PASS | integration (`registered_purge_participant_names() == ("marocassist.accounts",)`) |
| 7 | No PII in application logs during E2E | PASS | `signup.e2e.mjs` log scan (email, first/last name, display name, password): 0 found |
| 8 | Cookie mutation from a foreign Origin → 403 | PASS | integration (Phase 1 test, still green) |
| 9 | CI jobs defined and green | PASS locally / NOT TESTED on GitHub | every job step run locally; a GitHub run needs a push |
| 10 | S-8, S-9, S-10 closed | PASS | §6 |
| — | Email templates NL/FR/AR/EN | PARTIAL | product sends no email in Phase 2; ZITADEL's own texts used; custom templates not done |
| — | Neutral identity-provider branding | PARTIAL | ZITADEL default branding (no government look); no custom label policy |
| — | Session fixation | PASS | E2E: planted cookie replaced at sign-in |
| — | Account deletion executed end to end | NOT TESTED | runbook written; needs an enrolled platform operator (not in the dev stack) |

## 9. Open issues

1. P2-F1 (identity-provider session after sign-out): needs an upstream
   SaaS-OS decision (RP-initiated logout) — owner decision on proposal U-4.
2. P2-F2 registration protection before public launch.
3. ZITADEL's registration form also asks first and last name (stored at the
   identity provider, not by MarocAssist): deviates from P2-2 "email +
   password only"; removing it needs ZITADEL login v2 customisation.
4. Privacy notice: draft with placeholders (controller, hosting, retention);
   NL and EN only, FR/AR show English. Legal review required.
5. FR and AR UI texts need a native-speaker review.
6. Consulate list (Amsterdam, 's-Hertogenbosch, Rotterdam, Utrecht) to be
   verified by the owner.
7. Deletion runbook not executed; permission grant migration not applied
   anywhere (no pre-Phase-2 tenants outside the reset dev stack).
8. `OIDC_CLIENT_ID` still copied by hand after a fresh stack.
9. Branch protection on `main` (P2-6) not set.

## 10. Deviations from the plan

- Deletion-request routes live in `marocassist.privacy` (not `accounts`), so
  the request can unpair devices without breaking module independence.
- No orphan-tenant reaper job: resumable provisioning makes it unnecessary
  (ADR-0003 amendment).
- Registration form fields (open issue 3).

## 11. Changed files

41 files, +4155 / −170 lines against `main` before this report: CI
workflow; backend accounts/privacy/permissions/config/copilot, migration
0002, tests; web lib/components/pages/proxy; docker-compose; E2E; docs.

## 12. Commits on `phase-2` (signed, not pushed)

1. `docs: Phase 2 audit and plan`
2. `ci: backend, integration, web, extension and security jobs`
3. `feat(backend): onboarding, profile, consents, export and deletion request`
4. `feat(web): onboarding, profile, consents, account rights and nonce CSP`
5. `feat(dev): ZITADEL registration and mail; account lifecycle E2E`
6. `fix: address the Phase 2 security review`
7. `docs: Phase 2 report, ADRs, runbook and README`

## 13. Owner decisions taken on recommended defaults

P2-1 MFA optional · P2-2 minimal fields (see open issue 3) · P2-3 four NL
consulates-general (to verify) · P2-4 self-declared 18+ · P2-5 draft notice
`2026-11-draft` · P2-6 branch protection by the owner after the first CI run.

## 14. Advice for Phase 3

1. Push `phase-2` and open a PR (owner permission) so CI runs on GitHub;
   then enable branch protection on `main` requiring all five jobs.
2. Decide P2-F1: propose RP-initiated logout upstream (U-4).
3. Legal review of the privacy notice and the consent wording; fill the
   placeholders.
4. Phase 3 (knowledge platform) starts with the content-rights model and
   D-07 (FTS access).
