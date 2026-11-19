# MVP scope

Status: Phase 0 proposal, 2026-11-19 (RECOMMENDATION).

## 1. MVP goal

A Dutch-speaking Moroccan living in the Netherlands can sign up, find out
exactly what a consular procedure requires at their consulate, ask grounded
questions in Dutch, prepare a document checklist, and use the Copilot on
rdv.consulat.ma to understand each step and validation error — without
MarocAssist ever touching their credentials or submitting anything.

## 2. MVP = Phases 1–5 (+ minimal Phase 8 billing and Phase 9 readiness)

### In scope

| Area | MVP content |
|---|---|
| Identity | ZITADEL sign-up/login (email verification, password reset, optional MFA); personal tenant onboarding; consents |
| Profile & preferences | Display name, language (NL/FR/AR/EN), consulate (NL posts), notification prefs |
| Catalogue | 5–8 high-demand services (passport renewal, CNIE, consular registration, civil-status extracts/transcription, legalisation, laissez-passer — final list D-17), for the 4 NL consulates-general |
| Knowledge | Curated, cited, NL-first records with review dates; editorial UI (minimal); freshness checks |
| Assistant | Grounded Q&A with citations; conversation history; delete conversation |
| Appointment preparation | Per-service checklist with required documents, fees (as published), what to bring; printable |
| Copilot (Phase 5) | Chrome MV3 side panel on rdv.consulat.ma; pairing; site/page recognition for the main flow; step explanation; Q&A about the page; basic translation of visible text; consent + preview |
| Notifications | Email: verification (ZITADEL), welcome, review-date updates on saved preparations |
| Billing | Free tier + one paid plan via Stripe (could launch free-only in private beta) |
| Admin | Platform operator basics (SaaS-OS router) + editorial publishing |
| Privacy | Export and delete account (operator-assisted workflow acceptable in beta) |
| Ops | Single-VPS production, backups + restore drill, log-based alerts |

### Explicitly out of MVP (later phases)

- Smart highlighting and validation-error explanation polish (Phase 6; basic
  error explanation may ship in 5 if cheap)
- Vision/screenshot analysis (Phase 6, optional, blocked upstream)
- Personal document uploads, OCR, completeness checks (Phase 7)
- Usage-quota tiers beyond the simple plan, in-app notification inbox (Phase 8)
- Edge, voice, Darija, other administrations (Phase 10)
- Any RDV API or partner integration (only with authorisation)
- Native mobile apps

## 3. MVP release stages

1. **Private alpha** (Phases 1–4): web app only, invited users, test-mode
   billing, staging LLM budget.
2. **Closed beta** (Phase 5): Copilot as unlisted Chrome Web Store item,
   10–50 testers, legal review R1–R3 and Q-P1/3/4/5 completed.
3. **Public launch** (after Phase 9 essentials): listed extension, paid plan
   live, pen test done, DPIA done.

## 4. MVP success metrics

- ≥ 90% of golden-set questions answered with correct, cited sources.
- 0 occurrences of identifier/credential canaries in any outbound payload
  (CI + staging monitoring).
- Copilot recognises ≥ 95% of main-flow pages in fixture tests and degrades
  gracefully on unknown pages.
- p95 assistant latency < 15 s (non-streaming).
- Beta users: task completion without contacting the consulate for basic
  questions (qualitative).
