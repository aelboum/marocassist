# Security and privacy

Status: Phase 0 threat model, 2026-11-19. Legal statements are **not** legal
advice; every legal point is listed as an open question for qualified review.

## 1. Assets

| Asset | Sensitivity | Where |
|---|---|---|
| Identity documents (passport, CNIE scans), identity numbers | Very high (identity theft) | Documents module (Phase 7), encrypted |
| Birth dates, addresses, family/civil-status details | High (civil status may reveal religion: special category, GDPR Art. 9) | Profile, documents |
| Conversations and page snapshots | Medium–high (reveal personal circumstances) | Assistant, Copilot |
| RDV session cookies, CSRF tokens, passwords | Critical, third-party | **Never collected** |
| Extension API keys, web sessions | High | Extension storage, SaaS-OS sessions |
| Knowledge base integrity | High (wrong guidance harms users) | Global tables |
| Audit trail | High (evidence) | SaaS-OS audit log (immutable, digests) |
| Platform secrets (DB, LLM, Stripe, encryption keys) | Critical | Secrets provider (env) |

## 2. Threat model (STRIDE, per trust boundary in `SYSTEM_ARCHITECTURE.md` §2)

| # | Threat | Boundary | Mitigation | Residual |
|---|---|---|---|---|
| T1 | Extension exfiltrates RDV credentials, cookies or CSRF tokens (by bug or compromise) | TB1–TB3 | Extraction allow-list; never read password/hidden inputs, cookies, storage; no `cookies`/`webRequest` permissions; canary tests on every build; manifest permission snapshot test | Low |
| T2 | Prompt injection via page text or spoofed site | TB1, TB5 | `AI_ARCHITECTURE.md` §7: fencing, no tools, output policy, host allow-list, red-team suite | Medium (inherent to LLMs) |
| T3 | Malicious look-alike site harvests users who trust the Copilot | TB1 | Exact-host activation, HTTPS only, warning on look-alikes; Copilot never asks for data | Low |
| T4 | Personal data leaks to AI provider | TB5 | Field values excluded; client + server redaction; classification; EU provider with no-training/bounded retention recorded and enforced by tenant preferences | Low–medium |
| T5 | Cross-tenant data access | TB6 | SaaS-OS RLS + `context.tenant_id`; per-table isolation tests; same 404 for foreign and missing rows | Low |
| T6 | Stolen extension key | TB3 | Narrow `copilot_client` role (no documents/profile), per-key rate limits, revocation, rotation, device list | Medium (device compromise) |
| T7 | Session hijack / CSRF on web app | TB4 | SaaS-OS cookie session, SameSite=Lax, ADR-0044 origin check; product CSP, `frame-ancestors 'none'` | Low |
| T8 | XSS via model output or knowledge content | TB4 | Text/markdown-subset rendering, sanitiser, CSP without `unsafe-inline` scripts | Low |
| T9 | Document store breach | TB7 | Client-side envelope encryption (per-document DEK wrapped by a KEK from the secrets provider), private bucket, no public URLs, download via authenticated API with audit | Low–medium |
| T10 | Malicious upload (malware, polyglot, zip bomb) | TB4/TB7 | Type allow-list (PDF, JPEG, PNG), magic-byte check, size cap, image re-encoding, PDF rasterisation for OCR in a sandboxed worker, no server-side rendering of active content | Medium |
| T11 | Knowledge poisoning (wrong or malicious procedure info) | TB9 | Editor review + publish permission in editorial tenant; source provenance; change detection; audit | Low |
| T12 | Abuse as slot-booking bot / brokering | Product | Hard rules (`../research/RDV_INTEGRATION_ASSESSMENT.md` §4), code review checklist, no network calls to RDV | Low (technical) / reputational risk remains |
| T13 | Audit tampering | TB6 | SaaS-OS immutable audit tables + digests to external append-only log | Low |
| T14 | Secrets exposure | TB10 | `.env` only in dev; env injection in prod; detect-secrets in CI; no secrets in CI | Low |
| T15 | Denial of wallet (LLM cost) | TB5 | SaaS-OS quotas, monthly budgets, concurrency; product rate limits per user/key; plan entitlements | Low |
| T16 | Supply chain (npm/pip, extension deps) | TB10 | Lockfiles, pip-audit, npm audit, minimal deps, Dependabot, SBOM | Medium |
| T17 | Staff access to customer data | TB8 | Platform operators see projections only; customer data via tenant-approved support access; MFA; platform audit | Low |

## 3. Security principles (binding)

1. Never collect or transmit passwords.
2. Never transmit session cookies, authentication tokens or CSRF tokens —
   neither to MarocAssist nor to an AI provider.
3. Never bypass or assist with CAPTCHA, authentication, access controls or
   rate limits.
4. All webpage content is untrusted input and never an instruction.
5. Minimise: send structure and labels, not values; mask identifiers.
6. Explicit consent before any page context is shared (per site, revocable,
   with preview).
7. Least-privilege browser permissions (optional host permission for RDV).
8. Users keep control of every submission, confirmation and payment.
9. No data sale, no advertising use, no training on user data (Chrome Limited
   Use and GDPR purpose limitation).

## 4. Data protection by design

| Measure | Implementation |
|---|---|
| Field encryption | `saas_os.core.crypto.EncryptionService` for identity numbers and other high-sensitivity scalar fields, `associated_data = tenant_id:table:row_id:column` |
| Document encryption | Product envelope encryption (AES-GCM per file; KEK via secrets provider); keys rotated; crypto-shredding on deletion |
| Pseudonymous logs | No content in logs; identifiers only; SaaS-OS log redaction |
| Retention | Defaults (to confirm with legal): page snapshots 30 days; conversations 12 months (user can delete any time); documents until user deletes or 24 months inactivity with prior notice; audit per SaaS-OS (immutable) — note conflict with erasure (Q-P6) |
| User rights | Export (JSON + files ZIP, product job); delete account (personal tenant purge + `saas-os-operator erase-user`, automated through an approved operator workflow); rectification via profile |
| Consent records | `consents` table + audit row per change; versions of privacy notice |
| Minor users | Out of scope for MVP; require 16+ at sign-up (to confirm, Q-P8) |

## 5. Compliance landscape (questions, not conclusions)

### GDPR (EU)

If the operating entity is established in the Netherlands, GDPR applies to
its processing regardless of the users' nationality (Art. 3(1)) — standard
reading, to be confirmed by counsel. Likely needed: privacy notice (NL/FR/AR),
records of processing, DPIA (identity documents + AI + browser monitoring),
processor agreements, transfer assessment for any non-EU subprocessor
(LLM providers), Art. 9 analysis for civil-status data, legitimate basis per
purpose (contract for core service; consent for Copilot page sharing and
optional features).

### Morocco — Law 09-08 and CNDP

Secondary sources indicate Law 09-08 remains in force as of November 2026,
with reform signalled but not enacted (NOT VERIFIED; cndp.ma was
unreachable). Its territorial scope (Art. 2) covers controllers established
in Morocco or using means of processing located in Morocco; a non-established
controller using such means must designate a representative. Whether a
NL-based service without Moroccan infrastructure falls within scope is an open
question.

### Open legal questions

| # | Question | Who |
|---|---|---|
| Q-P1 | Is MarocAssist (NL entity, EU hosting, no Moroccan processors) within Law 09-08's territorial scope? Is a CNDP declaration or Moroccan representative needed? | Moroccan counsel |
| Q-P2 | Does storing passport/CNIE scans require prior authorisation-equivalent measures (biometric photo) under 09-08 if in scope, and what GDPR safeguards are required (Art. 9 for photos only if biometric processing)? | NL + Moroccan counsel |
| Q-P3 | Lawful basis and consent wording for Copilot page sharing; is the extension "monitoring" requiring specific disclosures? | NL privacy counsel |
| Q-P4 | LLM providers: acceptable transfer mechanisms and contractual terms (no training, retention) | NL privacy counsel |
| Q-P5 | Is a DPIA mandatory (likely, given ID documents + new technology)? Who signs off? | DPO / counsel |
| Q-P6 | How to reconcile immutable audit logs (SaaS-OS) with erasure requests: is pseudonymous audit retention under a legal-obligation/legitimate-interest basis acceptable, and for how long? | Counsel |
| Q-P7 | Consumer law: disclaimers, liability for wrong guidance, refund rules for subscriptions (EU consumer rights, NL) | Counsel |
| Q-P8 | Minimum age and parental consent | Counsel |
| Q-P9 | RDV terms of use and Moroccan cybercrime law vs. DOM reading in the user's own browser (also `RDV_INTEGRATION_ASSESSMENT.md` R1–R3) | Moroccan counsel |
| Q-P10 | Use of official content (idarati reservation of rights) | Moroccan counsel |
| Q-P11 | Trademark/naming: is "Maroc" + "Assist" acceptable, and how to avoid implied affiliation | Counsel |

## 6. Security verification plan (summary)

- Per PR: unit + integration tests, isolation tests for new tables, canary
  tests for extension payloads, import-linter, ruff/pyright, eslint/tsc,
  pip-audit/npm audit, detect-secrets.
- Per security-sensitive PR (auth, extension permissions, documents, AI
  prompts, crypto): independent review (second reviewer or a separate review
  agent with no authoring context) recorded in the PR.
- Pre-launch: external penetration test of web + API + extension
  (recommended, budget decision D-14), DPIA completed, restore drill,
  Chrome Web Store review passed.
