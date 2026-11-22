# Phase 3 security and privacy review (design stage)

Status: design approved by the owner (2026-11-20) under the conditions in the
[architecture report](PHASE3_ARCHITECTURE_REPORT.md) §12–13. This reviews a **design**, not code. Nothing is
implemented, so findings are design risks with required controls; none are
vulnerabilities in running code.

## 1. Scope and assets

The review covers:

- knowledge tables (global);
- the publishing loader;
- search routes;
- the evidence pack sent to `saas_os.inference`;
- editor workflow;
- the tenant-side citations and reports.

| Asset | Why it matters |
|---|---|
| Integrity of published knowledge | Wrong or forged consular information directly harms users (R-05) |
| Separation of user data from knowledge | A leak into a shared table would expose personal data to all users |
| The answer model's instruction channel | Injection could make the assistant mislead users or ask for credentials |
| Rights status of content | Unlicensed copying is a legal risk (R-04) |

## 2. Threats and controls

| ID | Threat | Control (design) | Residual risk |
|---|---|---|---|
| T-1 | The running app (or an injection bug) modifies published knowledge | App role has `SELECT` only on knowledge tables; writes only by the loader under the migrations role at deploy; integration test asserts `INSERT/UPDATE/DELETE` denied for the app role | Low |
| T-2 | A single editor publishes wrong or malicious content | Four-eyes (author ≠ approver, enforced); content files reviewed in a PR with required review (needs branch protection, P2-F7); publication audited | Low–Medium (solo maintainer: two-person rule needs a second reviewer; see P3-D3) |
| T-3 | User personal data ends up in a global knowledge table | No tenant or user columns in the knowledge schema (CI schema test); loader PII scan; user reports stored only in tenant tables; editor tooling never copies conversation text into knowledge | Low |
| T-4 | Cross-tenant leak through search | Knowledge is global and contains no tenant data; tenant-side tables (citations, reports) use `tenant_rls_statements`, are purge participants, and are covered by the existing 404 cross-tenant test pattern | Low |
| T-5 | SQL injection through the search query | One SQL function with typed parameters; `websearch_to_tsquery` (never `to_tsquery` on raw input, which errors on syntax); no string-built SQL; AST test on `fts.py` | Low |
| T-6 | Search denial of service (expensive queries, huge `k`) | Query length cap (256 chars), `k ≤ 6` inside the function, `SET LOCAL statement_timeout` (`set_local_statement_timeout` from SaaS-OS), SaaS-OS rate limit | Low |
| T-7 | Stored XSS through snippets or titles | `ts_headline` output escaped before markers are added; React renders text, never HTML; existing nonce CSP (S-10) | Low |
| T-8 | Open redirect or phishing link in answers or cards | Card URLs come only from `knowledge_sources.official_url` on a domain allow-list; model-produced URLs are stripped | Low |
| T-9 | Prompt injection via external content (§3) | Raw external content never reaches the answer model; editor-approved content is also treated as untrusted data; layered controls below | Medium (an editor could still approve subtle injected text; mitigated by sanitisation and red-team tests) |
| T-10 | Stale or withdrawn information presented as current | Expiry computed when the item is read (it does not depend on a job); status in the evidence pack; template-enforced notices; "stale leakage = 0" eval metric | Low |
| T-11 | Spoofed source: a look-alike domain registered as official | Source domains on an owner-maintained allow-list; `official` and `consulate` types allowed only for allow-listed domains; adding a domain needs review | Low |
| T-12 | Supply chain: the `pg_trgm` and `unaccent` extensions | Shipped with PostgreSQL contrib (image pinned by digest); created by migration, not at runtime | Low |
| T-13 | Content-rights violation (verbatim copying) | Rights classes; the loader refuses R4–R6 without evidence; verbatim-overlap check against the editor's pasted source text when available | Medium until Q-K1/Q-K2 are answered |
| T-14 | Public repository exposes editorial or rights evidence | Rights evidence and snapshots are never stored in the public repo; content files contain only own text and links (P3-D2) | Depends on P3-D2 |

## 3. Prompt injection and untrusted content

### Sources of untrusted text

- official web pages;
- PDFs and forms;
- document metadata (titles, author fields, XMP);
- text an editor pastes in;
- user questions and Copilot page snapshots (Phase 4/5).

### Controls

1. **No raw path.** The answer path reads only published, editor-approved
   knowledge. Fetched pages and PDFs (when change detection is enabled) are
   hashed and diffed, never passed to search or the model. Editor approval
   does not make content trusted: approved knowledge is still escaped and
   fenced as data (owner decision 2026-11-20).
2. **Sanitisation at entry**, in the loader and editor tooling:
   - strip bidi control characters (U+202A–202E, U+2066–2069; "Trojan Source")
     and zero-width characters (U+200B–200D, U+FEFF);
   - strip HTML and markup, and normalise Unicode (NFKC, with Arabic shaping
     kept);
   - reject text that contains the evidence delimiters or role markers
     (`<source`, `</evidence>`, `system:`, `assistant:`);
   - flag imperative phrases aimed at an AI ("ignore previous", "you are
     now", "تجاهل التعليمات", "ignore les instructions") for review.
3. **PDF specifics.** Editors work from the visible rendering. If text is
   extracted for a draft, hidden layers, white-on-white text, annotations and
   metadata are excluded; text that is not visible is not trusted. Metadata
   (title, author) is never used as content and never as a source title without
   human confirmation.
4. **Structural separation in the prompt:**
   - The policy goes in the `system` message.
   - Evidence goes in a fenced, escaped `user` part with classification
     `none`.
   - The policy states explicitly that evidence and page data are data and can
     never change instructions, request actions, or ask for credentials,
     payment or identity numbers.
5. **No capability to abuse.** SaaS-OS refuses tools and the model has no
   network access. Output is plain text plus limited markdown, rendered as
   text.
6. **Output policy checks**, deterministic, after inference:
   - citations must be a subset of the evidence;
   - fact values must equal the evidence;
   - only allow-listed URLs are permitted;
   - block requests for passwords, codes, CNIE or passport numbers, or payment;
   - block instructions to contact non-official parties;
   - check the answer language.
7. **AI-assisted drafting** (`marocassist.knowledge.draft`, classification
   `none`): the output is a draft only. It is marked `ai_assisted`, cannot be
   published without four-eyes review, and the same sanitisation applies to the
   draft.
8. **Red-team suite in CI:** fixture pages and PDFs with injected instructions
   in visible text, hidden text, metadata, bidi tricks and Arabic/French
   phrasing. Expected result: the sanitiser flags them, and the evidence pack
   escapes them. With the fake provider, output checks catch planted unsafe
   answers.
   - **Implemented in WP G** in `backend/tests/fixtures/knowledge/redteam.json`
     and `test_knowledge_redteam.py`. It has 57 attacks:
     - visible: EN, FR, NL, AR and Darija phrasings;
     - hidden: zero-width, word joiner, soft hyphen, tag characters, variation
       selectors, filler letters, line separators, HTML styling and comments,
       markdown comments, and text from PDF layers;
     - metadata: PDF title, EXIF description, author URL;
     - bidi overrides, isolates and marks;
     - Cyrillic and Greek homoglyphs;
     - prompt delimiters (including fullwidth), URLs and XSS.
   - Each attack must be refused by the sanitiser and by the loader in every
     kind of text field. There are 16 benign texts in all four languages that
     must pass.
   - The first run found 22 gaps:
     - FR, NL and AR phrasings beyond the original patterns;
     - variation selectors and other invisible letters;
     - line separators;
     - RLM and ALM, which were refused only as generic controls;
     - markdown comments;
     - homoglyphs.

     The sanitiser now closes all of them.
   - The evidence-pack and output-check halves of this control arrive with
     WP H and reuse the same fixture.

## 4. Privacy (GDPR/AVG; Moroccan law 09-08)

| Topic | Assessment and design |
|---|---|
| Lawful basis | Knowledge search processes the user's question (personal data when linked to their account). Basis: performance of the service (Art. 6(1)(b) GDPR). Unchanged from Phase 2. |
| Data minimisation | Search queries are **not stored**. Logs carry route, timing, language, result count and status, never the query text. Owner decision 2026-11-20 (final): only aggregated totals; no individual search terms stored and no individual searches logged; at least 10 searches per reported statistical cell (smaller cells are suppressed or merged); no re-identification through successive reports or small subgroups (reports use fixed periods and fixed dimensions, and a cell suppressed in one report is not derivable from the difference with another). The minimum of 10 is a privacy measure, not a guarantee that every re-identification risk is excluded. |
| Personal data in knowledge documents | Not allowed beyond office-level contact details; enforced by the loader PII scan (T-3). Names of officials are not stored. |
| Separation | Global knowledge versus tenant tables; different write paths (loader vs app role) and different schemas or tables; tested. |
| Tenant isolation | Unchanged SaaS-OS RLS for all tenant-side rows (citations, reports, later conversations) |
| Logging and audit trails | Every publication is audited in the **editorial tenant** with `record_system_action_in_transaction` (SaaS-OS requires a tenant on every audit row; no tenant-less audit table is invented). Metadata: content version, counts, ids; no text. Editor actions are audited as the editor's user id (pseudonymous). |
| Retention | Knowledge: indefinite, with versions kept for audit. Tenant citations and reports: follow conversation retention (Phase 0 default 12 months) and the account purge. |
| Deletion requests | Tenant rows are deleted by the existing purge (add as purge participants). Knowledge has no user data, so nothing to erase. Editor identity in the audit log follows SaaS-OS `erase-user` semantics. |
| External AI providers | Evidence parts `none`, question `tenant_data`; SaaS-OS destination policy and tenant preferences (EU residency, no training) apply. No profile data except the consulate code. No knowledge-side data goes to a provider outside `run_inference`. |
| Moroccan law 09-08 | Applicability to an EU controller serving Moroccan nationals in the NL is an open legal question (Q-K6, Phase 0 R-13). The design keeps processing in the EU and adds no Moroccan processors. No transfer to Morocco is designed. |
| Change detection (if enabled) | Fetches public pages only; stores no personal data; honest User-Agent; no proxies disguising origin |

## 5. Findings to carry into implementation

| ID | Severity | Finding | Required before |
|---|---|---|---|
| P3-S1 | Medium | Four-eyes publishing needs a second, independent reviewer; a solo maintainer cannot satisfy it. Not yet appointed (owner, 2026-11-20). | First real content |
| P3-S2 | Medium | Rights questions Q-K1/Q-K2 are unanswered, so only R1–R3 content is allowed | First public content |
| P3-S3 | Medium | Branch protection (P2-F7) is a precondition for "content reviewed in a PR" | File-based publishing |
| P3-S4 | Low | Proposal ID collision: the Phase 0 register used U-4 = "Governed embeddings" and U-5 = "Governed image input"; the Phase 2 work used U-4 for RP-initiated logout and "U-5" for back-channel logout; the Phase 2 plan used "U-3" for log out everywhere | **Resolved** (final numbering 2026-11-20: U-5 image input, U-8 embeddings, U-9 unused, U-10 back-channel logout, U-11 log out everywhere) |
| P3-S5 | Low | `unaccent` is `STABLE`; generated columns need an `IMMUTABLE` wrapper. That is a known PostgreSQL pattern, but the wrapper must pin the dictionary schema-qualified to avoid `search_path` tricks | Migration |
| P3-S6 | Info | The import-linter exception for `knowledge.fts` widens the database chokepoint by one module | Accepted with exit U-1 |

No design-level critical or high findings.
