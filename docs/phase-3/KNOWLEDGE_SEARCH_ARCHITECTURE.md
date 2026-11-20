# Knowledge search architecture (Phase 3 design proposal)

Status: design approved by the owner (2026-11-20) under the conditions in the
[architecture report](PHASE3_ARCHITECTURE_REPORT.md) §12–13; not implemented.
The decision record is [ADR-0007](../adr/0007-knowledge-search.md); rights and
provenance are in [CONTENT_RIGHTS_AND_PROVENANCE.md](CONTENT_RIGHTS_AND_PROVENANCE.md).

## 1. Goals

The search must:

1. Find the right **knowledge item** (an explanation or procedure) for a
   question in NL, FR, AR or EN.
2. Answer **facts** (fees, required documents, addresses) from structured,
   verified data, never from free text.
3. Respect consulate and country scope, verification status, freshness and
   source rank.
4. Feed the assistant only relevant, labelled, fenced knowledge, with citations
   preserved.

The design must not need embeddings, a vector database, an external search
service or a new server.

## 2. Module layout (MarocAssist)

```text
marocassist/knowledge/          # new feature module (independent of accounts/copilot)
  models.py        # global tables, declared with saas_os.infra.db primitives only
  catalogue.py     # structured fact and consulate lookup (select only)
  normalise.py     # pure Python: language detection, Arabic/French normalisation, synonym expansion
  fts.py           # ONLY non-migration module allowed to import sqlalchemy (func call to knowledge_search)
  retrieval.py     # pipeline: intent -> filters -> fts -> rerank -> evidence pack
  evidence.py      # builds fenced, labelled source blocks + source cards
  loader.py        # publishing loader (runs with the migrations role at deploy; not importable by app routes)
  routes.py        # read-only public search API + editor API (later)
marocassist/assistant/          # Phase 4: consumes retrieval.evidence; calls saas_os.inference
```

Import-linter changes (proposed):

- **`knowledge` joins the independence contract** with `accounts` and
  `copilot`.
- **Forbidden contract:** `marocassist.knowledge` is added to the source list,
  except `marocassist.knowledge.fts`.
- **New contract:** only `marocassist.knowledge.fts` may import `sqlalchemy`.
  An AST test checks that it uses only `sqlalchemy.func`.
- **Loader:** `marocassist.knowledge.loader` must not be imported by `app`,
  `api` or any `routes`.

## 3. Data model (conceptual)

All tables below are **global**, in schema `marocassist`: no `tenant_id`, no
RLS, `SELECT` granted to the app role. They are written only by the loader
under the migrations role.

| Table | Key columns (conceptual) |
|---|---|
| `knowledge_sources` | Source register (rights doc §2) |
| `knowledge_items` | `item_id`, `kind{procedure,explanation,faq}`, `rights_class`, `country_scope`, `consulate_scope[]`, `topic_keys[]`, `status`, `version`, `review_due_at` |
| `knowledge_item_texts` | `item_id`, `lang`, `title`, `body`, `keywords[]`, `lang_status`, `verified_at`; generated `tsv` (per language configuration) + `tsv_simple`; GIN indexes; trigram index on `title || keywords` |
| `knowledge_chunks` | `chunk_id`, `item_id`, `lang`, `ordinal`, `heading`, `text` (300–800 chars), generated `tsv`; the retrieval unit |
| `knowledge_facts` | `fact_key`, `scope`, `value jsonb`, `unit`, `valid_from`, `valid_until`, `status`, `verified_at` |
| `knowledge_citations` | `(item_id or fact_key) → source_id`, `locator` |
| `knowledge_terms` | `term`, `lang`, `normalised`, `canonical_key`, `kind{synonym,transliteration,plural,alias,abbreviation}`; trigram index on `normalised` |
| `consulates` | §6 |
| `consulate_attributes` | §6 |
| `consulate_jurisdictions` | §6 |
| `knowledge_publications` | `publication_id`, `content_version` (git SHA or bundle hash), `published_by`, `published_at`; one row per loader run |

Tenant-side tables (Phase 4, with RLS, purge participant) are **not** part of
the knowledge store:

- `conversations`, `messages`, `citations(tenant_id, message_id, source_id,
  item_id, fact_key, content_version)`;
- `content_reports(tenant_id, item_id, reason_code)` for "report outdated".
  Free text is optional and goes to editors pseudonymised.

The two stores are separate: knowledge never references a tenant, and tenant
rows reference knowledge only by id.

## 4. Search pipeline

```mermaid
flowchart LR
  Q[Question + UI language] --> N[normalise.py<br/>size cap, strip controls/bidi,<br/>detect language (script + hints)]
  N --> I[Intent + slots (rule-based)<br/>topic, consulate, fact type]
  I -->|fact question| F[catalogue.py<br/>structured fact lookup by key + scope]
  I -->|document question| X[Term expansion<br/>knowledge_terms: synonyms, plurals,<br/>transliterations (trigram ≥ 0.4)]
  X --> S[fts.py → knowledge_search()<br/>websearch_to_tsquery per language<br/>+ simple config, filters]
  S --> R[Rerank in Python<br/>ts_rank_cd × status × freshness × source rank<br/>dedupe per item, k ≤ 6]
  F --> E[evidence.py<br/>evidence pack + source cards]
  R --> E
  E --> A[assistant (Phase 4) / search UI]
```

### 4.1 Languages

| Language | Index configuration | Normalisation before indexing and query | Measured gap and mitigation |
|---|---|---|---|
| NL | `dutch` | lowercase, `unaccent` | — |
| FR | `french` | lowercase, `unaccent` (needed: `état` ≠ `etat` without it) | — |
| EN | `english` | lowercase, `unaccent` | — |
| AR | `arabic` | Remove diacritics and tatweel; unify أ إ آ → ا; ة → ه; ى → ي; Arabic-Indic digits → ASCII | Broken plurals are not stemmed (جوازات ≠ جواز): `knowledge_terms` plural entries plus editor keywords. Trigram is weak for Arabic, so it is used only on normalised terms. |
| Darija / transliteration | `simple` + trigram | lowercase, unify common Latin variants (`ou`/`u`, `e`/`a` vowel spread) through the alias table | Measured: `kafala`/`kefala` 0.40; different names score 0, so the alias table is required (Casablanca ↔ Dar el Beida) |
| Mixed-language documents | One text row per language; a chunk is stored in its own language. A query runs against the UI language first, then the detected query language. | | Cross-lingual matching happens only through `canonical_key` in the term table, not by machine translation |

### 4.2 Filters and ranking

- **Hard filters, in SQL:**
  - `status = 'published'`, or `expired` (kept, but flagged);
  - `lang` in the query languages;
  - `country_scope` contains the user's country (NL default);
  - `consulate_scope` is empty or contains the selected consulate.
  - `withdrawn` is never returned.
- **Score, in Python after SQL returns ids and `ts_rank_cd`:**
  `score = rank × w_status × w_fresh × w_source`.
  - `w_status`: published = 1.0, expired = 0.5.
  - `w_fresh`: decays after `review_due_at`.
  - `w_source`: rank 1 = 1.0, rank 2 = 0.9, secondary = 0.5.
- **Caps:** `k ≤ 6` chunks, at most 2 chunks per item, and a 200 ms statement
  timeout inside the function.

### 4.3 Fact questions versus document questions

| | Fact question | Document question |
|---|---|---|
| Example | "Wat kost een paspoort in Utrecht?" | "Hoe vraag ik een nieuw paspoort aan?" |
| Path | Intent gives `fact_key` = `fee.passport.*` and scope = `nl-utrecht`, then a structured lookup | FTS over chunks |
| Answer source | The fact row, rendered by a **template**; the model may rephrase around it but must keep the value verbatim (post-check) | Model summarises the chunks, with citations |
| Missing scope | Clarifying question: "Voor welk consulaat?" (or use the profile consulate when it is set) | Search all scopes, label the scope on each card |
| Conflict or expired | Show the state explicitly (rights doc §5.3) | Same, per card |

## 5. AI retrieval (interface to Phase 4)

The **evidence pack** is the only knowledge that reaches the model:

```text
<evidence version="2026-11-20T..Z" content_version="...">
  <source id="S1" rank="official" status="current" verified="2026-11-02"
          scope="consulate:nl-utrecht" lang="nl">…escaped editor-approved text…</source>
  <fact id="F1" key="fee.passport.adult" value="…" unit="MAD" status="conflict"
        sources="S1,S3" verified="2026-11-02"/>
</evidence>
```

Rules:

1. **Separation of roles:**
   - The `system` message holds the policy only.
   - The evidence and the user question go in `user` parts. Evidence parts have
     classification `none`; the question has classification `tenant_data`
     (SaaS-OS `ContentPart` requires a classification).
   - Delimiters inside the evidence are escaped. The policy states that
     evidence is data and never instructions.
2. **Only editor-approved knowledge** goes into the pack. Never raw web pages,
   PDFs or snapshots. Editor-approved knowledge is **still untrusted data**
   (owner decision 2026-11-20): it is escaped and fenced like any external
   text and can never act as an instruction.
3. **Minimal context:**
   - At most 6 sources and about 6 KB of evidence.
   - No conversation history beyond what Phase 4 sets.
   - No user profile data except the selected consulate code.
4. **Citations:** the model must cite `[S1]`/`[F1]`. The post-check:
   - removes unknown ids;
   - rejects procedural sentences without a citation;
   - checks that fact values in the answer equal the evidence;
   - allows only allow-listed URLs, and only from the source cards.
5. **Uncertainty:**
   - Status `expired`, `conflict` or `secondary-only` must appear in the answer.
     A template appends the notice if the model omits it.
   - "No evidence" leads to the fixed reply: "Ik kan dit niet bevestigen;
     raadpleeg [officiële bron]".
6. **Clarifying question:** asked when a consulate-scoped fact has no
   consulate, or when intent confidence is low. This is a deterministic rule,
   not model judgement.
7. **No tools:** SaaS-OS refuses tools anyway. The model cannot fetch, browse
   or call anything.

## 6. Consulate data model

Each attribute group can be verified and updated on its own:

| Table | Columns | Notes |
|---|---|---|
| `consulates` | `code` (`nl-rotterdam`), `country` (`NL`), `kind` (`consulate_general`), `active` | Stable keys; the existing `profiles.consulate_code` stays valid |
| `consulate_attributes` | `code`, `attribute` (`display_name`, `physical_city`, `address`, `contact`, `opening_hours`), `lang` (for `display_name`), `value jsonb`, `source_id`, `verified_at`, `status` | One row per attribute (per language for names); each has its own source and status |
| `consulate_jurisdictions` | `code`, `municipality_code` (CBS), `source_id`, `verified_at`, `status` | Empty until an official source is found; **never derived** |

Initial content, proposed. Statuses come from `docs/product/CONSULATES.md`.

| code | display_name (NL) | physical_city | address | contact | opening hours | jurisdiction |
|---|---|---|---|---|---|---|
| `nl-amsterdam` | Consulaat-generaal Amsterdam | Amsterdam | Vondelstraat 65-67, 1054 GK — `pending_review` (one source: Rijksoverheid) | `pending_review` | **not available** | **not available** |
| `nl-rotterdam` | **Consulaat-generaal Rotterdam** | **Schiedam** | De Brauwweg 38-44, 3125 AE Schiedam — `pending_review` | `pending_review` | **not available** | **not available** |
| `nl-utrecht` | Consulaat-generaal Utrecht | Utrecht | Kanaalweg 95 D/E, 3533 HH — `pending_review` | `pending_review` | **not available** | **not available** |
| `nl-den-bosch` | Consulaat-generaal 's-Hertogenbosch | 's-Hertogenbosch | Larenweg 46, 5234 KA — `pending_review` | `pending_review` | **not available** | **not available** |

Owner decision P3-D5 (2026-11-20): an attribute confirmed by only one source
is shown with the label "nog niet onafhankelijk bevestigd — controleer bij
het consulaat" and a link to that source.
Missing opening hours and jurisdiction are shown as "zie officiële bron", never
filled in. Extending to another country means adding rows; there is no code
change.

## 7. Conceptual API

All routes are tenant-scoped (`/v1/tenants/{tenant_id}/knowledge/...`)
although the data is global. The reason: SaaS-OS `require_permission`, its
membership check and its per-tenant rate limit work per tenant, so the existing
chain is reused instead of building a parallel, tenant-less authorisation path.

| Method and path (prefix `/v1/tenants/{tenant_id}/knowledge`) | Auth | Purpose |
|---|---|---|
| `GET /search?q=&lang=&consulate=&kind=` | `require_permission` `marocassist.knowledge:read` (owner role; grant migration for existing tenants) | Search results: item id, title, snippet (`ts_headline`, escaped), status, source cards. No tenant data is written. |
| `GET /items/{item_id}?lang=` | Same | Published item and citations |
| `GET /facts/{fact_key}?consulate=` | Same | Fact value(s) with status and sources; conflict returns all values |
| `GET /consulates` and `/consulates/{code}` | Same | Consulate attributes with per-attribute status |
| `POST /reports` | User, `marocassist.knowledge:report` | "Report outdated"; stored tenant-scoped with RLS |
| Editor API (later) | Editorial tenant permissions `marocassist.editorial:{draft,review,publish}` | Only if the file-based workflow (P3-D2) is replaced |

Search stays authenticated. That avoids a public scraping surface, and the
SaaS-OS per-tenant rate limit applies. A public, unauthenticated catalogue
is a later product decision (P3-D8).

## 8. Evaluation

- **Golden set:** at least 150 questions, in NL (60), FR (40), AR (30, including
  Darija transliterations) and EN (20).
  - Each has expected `item_id`s or `fact_key`s and an expected scope.
  - Editors build it; it contains no personal data.
- **Metrics:**
  - recall@6 and MRR per language;
  - fact accuracy (exact value);
  - correct clarification rate;
  - stale-content leakage (expired facts presented without a notice = 0
    allowed);
  - p95 latency (< 300 ms search).
- **Process:** run in CI against a fixture corpus with no network. Report the
  results per language. The thresholds in the ADR trigger a re-evaluation of
  embeddings.

## 9. Search quality limits (stated, not hidden)

- Arabic recall depends on the term table, because the `arabic` stemmer misses
  broken plurals.
- Darija in Arabic script is not covered by any PostgreSQL configuration; it
  relies on `simple` plus terms.
- There is no cross-lingual search beyond `canonical_key`. A French-only source
  is found from a Dutch question through the linked Dutch item, not by
  translation.
