# Knowledge content

Curated, cited content about consular procedures lives here from Phase 3 on
(`docs/roadmap/PRODUCT_ROADMAP.md`, Phase 3; `docs/research/OFFICIAL_DATA_SOURCES.md`;
decision P3-D2).

**No real content may be added yet.** Real content is blocked until a second,
independent reviewer is appointed (P3-D3), the editorial tenant exists
(P3-D10), the legal questions are answered (Q-K1, Q-K2, Q-K5, Q-K6), and
branch protection is enabled on `main` (P2-F7). Until the legal answers,
only own explanations (R1), cited facts (R2) and own-words summaries (R3) are
allowed, and the loader refuses anything else. Official sites reserve
reproduction rights: never copy their text.

## Format

The directory is a content bundle, checked against `content.schema.json`
(generated from `backend/src/marocassist/knowledge/content.py`):

| File | Holds |
|---|---|
| `manifest.json` | Format version and the editor register (pseudonymous `ed-...` handles and roles) |
| `sources.json` | The source register (rights document section 2) |
| `items/<item_id>.json` | One knowledge item per file, with its texts per language |
| `facts.json` | Structured facts (fees, documents, deadlines) |
| `terms.json` | Search terms: synonyms, plurals, transliterations |
| `consulates.json` | Consulates and their separately verified attributes |

A worked example is the test fixture in
`backend/tests/fixtures/knowledge/valid/`; it is fixture data, not real
content.

Editors are identified by handle only. Never put a name, an e-mail address
or a SaaS-OS user id in these files: this repository is public. Rights
evidence and page snapshots never belong here either.

## Checking and publishing

```bash
cd backend
uv run python -m marocassist.knowledge.loader --dry-run ../knowledge   # what CI runs
uv run python -m marocassist.knowledge.loader ../knowledge             # at deploy
```

The dry run needs no database. It checks shapes, the sanitiser (bidi
controls and marks, zero-width and other invisible characters, markup and
markdown comments, URLs in text, words mixing Latin, Cyrillic or Greek
letters, prompt delimiters, injection phrases in five languages; see
backend/tests/fixtures/knowledge/redteam.json for what each rule catches),
the personal-data scan, the domain allow-list, rights classes,
four-eyes review (author is not the approver; approver is a registered
reviewer), review periods and citations. Any problem refuses the whole
bundle.

Publishing runs under the migrations role with `MAROCASSIST_EDITORIAL_TENANT_ID`
set. It replaces all knowledge in one transaction, writes one audit row in
the editorial tenant, and does nothing when the content is unchanged.
