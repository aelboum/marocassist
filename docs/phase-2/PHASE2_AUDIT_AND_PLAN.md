# Phase 2 audit and plan — Identity and SaaS foundation

Date: 2026-11-20. Status: plan, awaiting owner confirmation of the decisions
in §5. Base: `main` at `aff36e7` (Phase 1, approved). Work happens on the
local branch `phase-2`; nothing is pushed, merged or deployed without the
owner's explicit permission. The repository stays PUBLIC.

Sources: `docs/roadmap/PRODUCT_ROADMAP.md` (Phase 2),
`docs/roadmap/ACCEPTANCE_CRITERIA.md` §2, `docs/phase-1/PHASE1_REPORT.md`
§8–§9 and §14, SaaS-OS v0.15.0 source as installed (`cdede95`), ZITADEL
v4.19.5 `cmd/defaults.yaml`.

## 1. Current state (evidence)

| Item | State | Evidence |
|---|---|---|
| Personal tenant on first use, concurrency-safe | Done (Phase 1) | `accounts/provisioning.py`, integration tests |
| Roles `owner` / `copilot_client`, permission registration | Done (Phase 1) | `permissions.py` |
| Language preference (`workspace_settings.locale`) | Done (Phase 1) | `accounts/workspace_settings.py` |
| Device pairing API (list, pair, revoke) | Done (Phase 1); no web page yet | `copilot/routes.py` |
| CI | **Missing** — no `.github/` directory; Phase 1 roadmap item 7 was not built | `ls .github` |
| Branch protection on `main` | **Missing** | GitHub API: "Branch not protected" |
| Sign-up, email verification, password reset | Not configured: ZITADEL has no SMTP, so it cannot send mail | `docker-compose.yml` |
| Profile, consents, export, delete request | Missing | — |
| Open review findings | S-8 (provisioning holds a pooled connection; orphan tenant on crash), S-9 (disabled devices accumulate), S-10 (no `script-src` CSP) | Phase 1 report §8 |

## 2. What SaaS-OS v0.15.0 provides (verified in source)

| Need | SaaS-OS | Consequence for MarocAssist |
|---|---|---|
| Sign-up, verification, reset, MFA | Not in SaaS-OS: delegated to the OIDC provider (ZITADEL) | Configure ZITADEL; no second identity system |
| Knowing whether the email is verified | `email_verified` must be JSON `true`; otherwise login still succeeds but `Session.verified_email` is `None` (`api/auth/routes.py:337`) | Onboarding requires `Session.verified_email` (via `get_current_session`); no extra identity data stored |
| Logout | `POST /auth/logout` revokes the current session, clears the cookie | Web logout button; test old cookie → 401 |
| Session fixation | Every callback issues a new random 256-bit token, stores only its hash (`sessions.py:68`) | Test: session token changes across login |
| First-login hook | None ("no plugin/hook system") | Keep Phase 1's explicit `POST /v1/me/workspace` onboarding call |
| Audit row in the same transaction | `record_in_transaction(session, caller=UserCaller(...), tenant_id, action, resource_type, ...)`; free product action names; metadata ≤ 8 KiB, credential keys forbidden | Consent changes: product row + audit row in one `tenant_session_scope` |
| Idempotency | `run_idempotent` is tenant-scoped (needs an open tenant) | Onboarding before a tenant exists stays on the advisory-lock find-or-create; later mutations may use `Idempotency-Key` |
| User erasure | `erase_user_identity` (identities, sessions, keys, memberships); no HTTP route; CLI `saas-os-operator erase-user`; no product hook | Delete = request recorded by product + operator runbook: tenant purge (our purge participants) + `erase-user` |
| Data export | Nothing | Product endpoint returning the user's product data as JSON |
| Product email | `send_email` / `dispatch_notification`; no templates, no i18n | Phase 2 sends no product email; account mails come from ZITADEL |
| PII in logs | Formatter redacts credential keys only, not email or names | Never log personal values; log-scan test over the E2E run |
| Same-origin cookie mutations | Enforced for every non-GET cookie request (`api/dependencies.py:336`) | Already tested; extended to every new mutation |
| Self-service session list / "log out everywhere" | Not provided (operator-only `revoke_user_sessions`) | Out of scope; noted as upstream proposal U-3 |

ZITADEL v4.19.5 defaults: `LOGINPOLICY_ALLOWREGISTER: true`, MFA not forced,
password reset shown, minimum password length 8 with all character classes.
SMTP is configured with `ZITADEL_DEFAULTINSTANCE_SMTPCONFIGURATION_*`.

## 3. Work packages

| WP | Content | Notes |
|---|---|---|
| A | **CI** (GitHub Actions): backend (ruff, mypy, import-linter, unit), integration (PostgreSQL 16 + Redis 7 service containers, app role), web, extension, security (pip-audit, npm audit, secret scan). Actions pinned by SHA, `permissions: contents: read` | Workflow is written and run locally where possible; it only runs on GitHub after a push (owner permission). Branch protection is a GitHub setting: owner action or explicit permission |
| B | **ZITADEL account lifecycle**: SMTP to Mailpit (dev only), registration on, email verification, password reset, optional MFA, neutral branding (no government look) | Dev configuration only |
| C | **Onboarding and profile**: verified email required; onboarding state; `profiles` (display name optional, consulate code, residence country), preferences (language, product-email opt-in); onboarding page in the web app | Data minimisation: no birth date, no nationality, no civil status in Phase 2 |
| D | **Consents**: `consents` table (purpose, version, granted, decided_at, source); every change writes an audit row in the same transaction; privacy-notice version constant | Purposes in Phase 2: `privacy_notice` (required), `product_emails` (optional). AI and page-sharing consents are Phase 4/5 |
| E | **Account rights**: `GET` export (JSON of all product rows of the personal tenant); delete request (`deletion_requests` row + audit; operator runbook executes purge + `erase-user`); web pages | MVP scope allows an operator-assisted delete in beta |
| F | **Connected devices page** in the web app (list, revoke) on the existing API | Pairing from the web stays as in Phase 1 |
| G | **Phase 1 findings**: S-8 (short lock session, orphan-tenant reaper job), S-9 (disabled devices hidden from lists and limits; cleanup), S-10 (nonce-based CSP via Next.js middleware) | |
| H | **Tests**: 401/403/404 matrix for every route; isolation test per new table; onboarding idempotency and concurrency; consent audit row in the same transaction; purge removes all product rows (asserting `registered_purge_participant_names()`); logout and session-change tests; log scan for PII canaries during E2E; E2E sign-up → verify (Mailpit) → onboarding → dashboard → logout | |
| I | Docs: ADRs (consent model, account deletion flow), privacy-notice draft (marked draft, legal review pending), runbook for deletion, Phase 2 report with PASS/FAIL/BLOCKED/NOT TESTED per criterion | |

Order: A → G(S-8) → C/D → E → F → B → H (E2E) → G(S-10) → I.

## 4. Acceptance criteria (from ACCEPTANCE_CRITERIA.md §2, plus carry-overs)

1. Sign up, verify email, log in, log out (E2E against local ZITADEL + Mailpit).
2. First login creates exactly one personal tenant, also concurrently.
3. Every product route: 401 without credential, 403 without permission, 404 for another tenant's id.
4. Every tenant table: isolation test without tenant predicate.
5. Consent change writes an audit row in the same transaction.
6. Purge removes all product rows; participant names asserted.
7. No PII values in application logs during the E2E run.
8. Cookie mutation from a foreign `Origin` returns 403.
9. Carry-over: CI jobs defined and green locally (green on GitHub only after an approved push).
10. Carry-over: S-8, S-9, S-10 closed or explicitly re-scoped.

## 5. Owner decisions (recommended defaults; work proceeds on them unless changed)

| ID | Question | Recommendation |
|---|---|---|
| P2-1 | MFA optional or required | Optional (offered by ZITADEL), revisit before beta |
| P2-2 | Sign-up fields | Email + password only (passkey allowed by ZITADEL); display name optional in onboarding |
| P2-3 | Consulate list for the profile | Fixed list of the Moroccan consulates-general in the Netherlands, stored as codes; to be verified by the owner (editorial data proper is Phase 3) |
| P2-4 | Minimum age | Self-declared 18+ at onboarding until counsel answers Q-P8 |
| P2-5 | Privacy notice | Draft text marked "concept, not legally reviewed"; version `2026-11-draft` |
| P2-6 | Branch protection on `main` | Owner enables it (or gives explicit permission) after the first CI run on GitHub |

## 6. Out of scope for Phase 2

AI assistant, knowledge base, Copilot features beyond the devices page,
documents, billing, production deployment, staging infrastructure, product
emails, self-service session list, automated (non-operator) erasure.
