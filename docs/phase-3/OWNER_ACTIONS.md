# Phase 3 owner actions

These steps cannot be done by the development work itself. None of them
blocks coding; all of them block **real** knowledge content. Status as of
2026-11-21.

## 1. Branch protection on `main` (P2-F7)

The four-eyes rule in the loader checks editor handles in
`knowledge/manifest.json`, which anyone can write (security review
finding P3-R4). It only means something
when every change to `main` goes through a reviewed pull request.

GitHub, repository **Settings, Branches, Add branch ruleset** (or classic
"branch protection rule") for `main`:

- Require a pull request before merging.
- Require status checks to pass, and select:
  - `backend (lint, types, architecture, unit, OpenAPI drift)`
  - `integration (PostgreSQL 16, Redis 7)`
  - `web (types, lint, tests, build, audit)`
- Require branches to be up to date before merging.
- Block force pushes and deletion.
- Required approvals: **1**.

Until a second reviewer exists (section 3) nobody else can approve, so you
cannot merge your own pull requests with "1 approval" enforced for admins.
Two workable options:

- **Recommended now:** enable everything above, and add yourself (repository
  admin) to the bypass list. Code keeps moving, CI is still mandatory, and
  no real content is merged anyway until a reviewer exists.
- **Once the reviewer is appointed:** remove the bypass, so every change,
  including `knowledge/`, needs their approval. Add a `CODEOWNERS` entry
  `knowledge/ @<reviewer-login>` at the same time.

## 2. Accept the loader's database exception

Decision needed (yes or no): `marocassist.knowledge.loader` may import
`sqlalchemy` directly, as a second exception besides the migrations. Reason:
the SaaS-OS ORM primitives have no array or JSONB column support, which the
knowledge tables need. Containment: an import-linter contract forbids every
runtime module (API, worker, jobs, other knowledge modules) from importing
the loader, and it only runs under the migrations role. Record the answer in
the decision register (`PHASE3_ARCHITECTURE_REPORT.md`, section 13).

## 3. Appoint the second reviewer (P3-D3)

An independent person who approves content they did not write. They need a
GitHub account (for pull request review) and get a pseudonymous handle
(`ed-...`) with the `reviewer` role in `knowledge/manifest.json`. Their real
name never goes in the repository.

## 4. Create the editorial tenant (P3-D10)

Create one separate tenant via the SaaS-OS operator for knowledge audit
rows, and set its id as `MAROCASSIST_EDITORIAL_TENANT_ID` in the deployment
environment. The loader refuses to publish without it.

Set it for the worker as well: the daily editor review report (WP F) is
written into this tenant, once per UTC day. Without it the review job runs
every minute but does nothing.

## 5. Send the legal questions

Send these to counsel (Moroccan counsel for Q-K1 and Q-K6; Dutch counsel is
sufficient for Q-K5). Answers decide which rights classes the loader may
allow beyond R1 to R3.

| # | Question |
|---|---|
| Q-K1 | Under Moroccan copyright law, may we paraphrase official procedure information in our own words, with citations and links, without authorisation, given that idarati.ma reserves reproduction rights? Does a quotation right allow short verbatim quotes with attribution? |
| Q-K2 | May we keep private, non-published snapshots of official pages (page text or PDF) for provenance and change detection? |
| Q-K3 | Which disclaimers are required so the product never appears to be an official source? |
| Q-K4 | What are the data.gov.ma licence terms (once the site is reachable)? |
| Q-K5 | May we reuse consulate addresses and contact details from rijksoverheid.nl pages? Are these unprotected facts? |
| Q-K6 | Does Moroccan law 09-08 apply to our processing, given an EU-based controller, processing in the EU, and users who are Moroccan nationals living in the Netherlands? |

Background for counsel: `docs/research/OFFICIAL_DATA_SOURCES.md` and
`docs/phase-3/CONTENT_RIGHTS_AND_PROVENANCE.md`.
