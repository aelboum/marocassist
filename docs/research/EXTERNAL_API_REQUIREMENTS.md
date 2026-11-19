# External API and service requirements

Status: Phase 0, 2026-11-19. Lists every external dependency the roadmap
assumes, whether SaaS-OS already integrates it, and what must be decided or
procured. Nothing here has been subscribed to or contacted.

| # | Dependency | Purpose | SaaS-OS support (v0.15.0) | Needed by phase | Decision / action | Status |
|---|---|---|---|---|---|---|
| E1 | OIDC identity provider (ZITADEL, self-hosted) | Login, registration, MFA, email verification | Yes: OIDC routes, ZITADEL local identity and production runbooks | 2 | Confirm self-hosted ZITADEL vs. ZITADEL Cloud | VERIFIED (see `../architecture/SAAS_OS_INTEGRATION.md`) |
| E2 | LLM provider(s) | Assistant, translation, page explanation | Yes, text-only, non-streaming: Anthropic Messages, OpenAI-compatible Chat Completions, Gemini generateContent | 4 | Choose provider(s) with EU processing and no-training terms; DPA; price confirmation | VERIFIED (source) |
| E3 | Vision-capable LLM | Optional screenshot analysis | **No**: image parts refused by SaaS-OS | 6 | Upstream proposal or defer | VERIFIED (source) |
| E4 | Embeddings provider | Semantic retrieval | **No**: no embeddings API in SaaS-OS | 3 (optional) | MVP uses PostgreSQL full-text search; embeddings only after an upstream decision | VERIFIED (source) |
| E5 | Transactional email | Verification, notifications | Yes: SMTP, Resend, Mailpit (dev) | 2 | Choose Resend or SMTP relay; sending domain DNS (SPF/DKIM/DMARC) | VERIFIED |
| E6 | Payments | Subscriptions | Yes: provider-abstracted `BillingProvider` with a Stripe adapter; Stripe hosted payment page | 8 | Confirm Stripe (supports iDEAL/SEPA in NL; verify at procurement). Moroccan card acquiring (e.g. CMI) has no adapter | VERIFIED (adapter); payment-method coverage NOT VERIFIED |
| E7 | Object storage (S3-compatible, EU region) | Personal documents | See `../architecture/SAAS_OS_INTEGRATION.md` (S3 used for backups only) | 7 | Choose provider; SSE + client-side envelope encryption | RECOMMENDATION |
| E8 | OCR | Document reading | None | 7 | Prefer self-hosted (Tesseract/PaddleOCR) to keep ID documents in-house; external OCR only with DPA and EU processing | RECOMMENDATION |
| E9 | Chrome Web Store developer account | Publishing the Copilot | n/a | 5 | One-time registration fee; verified publisher; privacy disclosures | NOT VERIFIED (fee amount) |
| E10 | VPS / hosting (EU) | Runtime | SaaS-OS targets Docker Compose on a VPS (ADR-0010) | 1/9 | Choose EU provider | VERIFIED (ADR) |
| E11 | Off-host encrypted backup target | Backups | Yes: `saas-os[s3-backup]`, age encryption, systemd timers | 9 | Choose bucket provider | VERIFIED |
| E12 | Official consular sources | Knowledge | No API exists that we could verify | 3 | Curated content; reuse authorisation | See `OFFICIAL_DATA_SOURCES.md` |
| E13 | RDV official/partner API | Future integration | None known | 10+ | Only with written authorisation | See `RDV_INTEGRATION_ASSESSMENT.md` |
| E14 | Speech-to-text / TTS | Voice (later) | None (SaaS-OS issue #206 proposes governed streaming and audio; open, not implemented) | 10 | Defer | VERIFIED (issue open) |
| E15 | Error tracking / APM | Operations | SaaS-OS forbids collectors that capture local variables in worker/API (consumer guide §15) | 9 | Choose a tool configured without local-variable capture, or logs only | VERIFIED (doc) |

## Procurement principles

- EU data residency for every processor that sees personal data; DPA
  (verwerkersovereenkomst) in place before first production use.
- No processor receives passport or CNIE numbers, scans or birth dates unless
  the feature strictly requires it and the user consented to that feature.
- LLM providers: contractual no-training and bounded retention; record those
  facts with `saas-os-operator ai-provider-data-handling` so tenant
  preferences are enforced by SaaS-OS.
