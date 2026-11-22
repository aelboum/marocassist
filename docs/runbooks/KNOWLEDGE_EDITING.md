# Runbook: editing and publishing knowledge

For editors and the second reviewer. Policy:
[content rights and provenance](../phase-3/CONTENT_RIGHTS_AND_PROVENANCE.md).
Format: [`knowledge/README.md`](../../knowledge/README.md).

> **Real content is blocked.** Until all of these are in place, only fixture
> content exists and nothing real is approved or published:
>
> - the second reviewer is appointed (P3-D3);
> - the editorial tenant exists (P3-D10);
> - the legal questions are answered (Q-K1, Q-K2, Q-K5, Q-K6);
> - branch protection is on for `main` (P2-F7).
>
> The steps below describe the process once those are done. Until then,
> practise on a copy of `backend/tests/fixtures/knowledge/valid/`.

## 1. Roles

| Role | Does | Never |
|---|---|---|
| Author (`ed-...`, role `author`) | Registers sources, writes items, facts and terms, opens the pull request | Approves their own work |
| Reviewer (`ed-...`, role `reviewer`) | Checks rights, facts and wording against the official page; sets `approver` and `approved_at`; approves the pull request | Approves text they wrote |

Editors appear in `knowledge/manifest.json` by pseudonymous handle only.
Never put a real name, an e-mail address or a user id in any content file:
this repository is public.

## 2. Before writing: the source

1. Open the official page in a normal browser, from a normal connection.
   Some Moroccan sites block certain networks. A page you cannot reach has
   not necessarily been removed.
2. Register it in `knowledge/sources.json`:
   - a new, never-reused `source_id`;
   - `official_url`, which must be on the domain allow-list in
     `backend/src/marocassist/knowledge/domains.py`. Adding a domain is a
     code change with its own review, never part of a content PR;
   - `source_type`, `publisher`, `geo_scope`, `language`, `consulted_at`
     and `verified_at`;
   - `licence: "unknown"` and `allowed_use: ["link", "cite_fact", "summary"]`.
     These are the only values allowed without recorded permission.
3. Do **not** save a copy of the page, as text, PDF or screenshot, in the
   repository. Until legal question Q-K2 is answered, store nothing but
   the URL, the title and your notes. Rights evidence, once there is any,
   is filed outside the public repository and referenced by
   `rights_evidence_ref`.

## 3. Writing an item

One file per item: `knowledge/items/<item_id>.json`.

- **Rights class:** use `R1` (own explanation), `R2` (cited fact) or `R3`
  (short summary in your own words). The loader refuses `R4`–`R6`.
- **Write in your own words.** Never copy sentences from the official page,
  and do not closely paraphrase it either. Use facts, not phrasing. An
  `R3` summary always ends by sending the reader to the official page.
- **Body format:** plain paragraphs and `## Heading` lines only. No other
  markup, no links in the text (the source card carries the link), no
  e-mail addresses or phone numbers.
- **Citations:** at least one per item. Give each a `locator`, such as the
  section heading on the official page or a page number in a PDF. The
  loader requires it for facts; for items, the reviewer expects it.
- **One text per language.** Each language has its own `lang_status` and its
  own review. A French text is not approved because the Dutch one is. A
  text you have not finished stays `pending_review`.
- **Keywords:** the words people actually type, including common
  misspellings.
- **AI help:** if you used an AI tool to draft a text, set
  `ai_assisted: true`. The text then needs an approver like any other.

### Facts (`knowledge/facts.json`)

Fees, required documents and deadlines are structured facts, never only
sentences in a body.

- Give each fact a `unit` and a `scope`: `global`, `country:NL` or
  `consulate:<code>`. Give a fee that differs per consulate one fact per
  consulate.
- Every fact needs an official or government source with `cite_fact`.
- **A fee changes:** never edit the old value. Give the old fact a
  `valid_until`, and add a new fact with the new value and `valid_from`.

### Terms (`knowledge/terms.json`)

Add search terms when a golden-set question or a user report shows that
something cannot be found:

- Arabic broken plurals (`جوازات` for `جواز`);
- transliterations (`kafala`, `kefala`);
- Darija (`lang: "ary"`);
- French and Dutch variants.

Terms that should find each other share one `canonical_key`.

### Consulates (`knowledge/consulates.json`)

Every attribute has its own source and its own verification date. An
address from a single source stays `pending_review`; the site then shows it
as "not yet independently confirmed". Opening hours and jurisdiction are
only entered when verified from an official source. Never fill them in from
memory or a directory site.

## 4. Review dates

Set `review_due_at` within these limits after `verified_at`. The loader
checks them. A later date needs a `review_override_reason`.

| Content | At most |
|---|---|
| Fees | 90 days, or `valid_until` if earlier |
| Procedures, required documents, FAQs | 180 days |
| Consulate address and contact details | 180 days |
| Opening hours | 90 days |
| Own explanations without facts | 365 days |

A known change, such as an announced fee or a new form, means you re-check
now, whatever the date.

## 5. Check locally

```bash
cd backend
uv run python -m marocassist.knowledge.loader --dry-run ../knowledge
```

This needs no database. On success it prints `ok: sha256:... (N items,
M facts); dry run`. Otherwise it prints one line per problem, in the form
`<file and field>: [<code>] <reason>`, and exits with code 1. Fix every
line. The message never repeats the offending text. Rights policy §11
lists what each code means. The most common:

| Code | Usually means |
|---|---|
| `unsafe_text` | Hidden characters, markup or a URL in text, or a phrase that looks like an instruction to an AI. Retype the text; do not paste it from a web page or PDF. |
| `personal_data` | An e-mail address, phone number or identity-number pattern outside a consulate contact field |
| `rights_not_permitted` | The rights class needs a use (`summary`, `cite_fact`) that the cited source does not allow |
| `review_period` | `review_due_at` is too far after `verified_at` |
| `four_eyes_missing`, `four_eyes_same` | A published text has no approver yet, or the approver is the author |
| `domain_not_allowed` | The source URL is not on the allow-list for its type |

## 6. Review (the second person)

The author opens a pull request with the changes. CI runs the dry run and
the golden set. The reviewer:

1. Opens every cited source and checks each fact, its date and its scope
   against the official page.
2. Checks the wording:
   - own words, no copied phrasing;
   - nothing that sounds official on behalf of the consulate;
   - for an `R3` summary, a pointer to the official page.
3. Checks the languages they can judge. French and Arabic texts need a
   native-speaker review (P2-F5) before they are set to `published`.
4. Sets `review.approver` to their own handle and `review.approved_at` to
   today's date, on every text, fact, source and attribute they approve.
5. Approves the pull request on GitHub.

The approver must not be the author. The loader refuses that, and branch
protection with `CODEOWNERS` makes sure the GitHub review really is by the
reviewer.

## 7. Publishing

Publishing happens at deploy, after the database migrations, under the
migrations role:

```bash
cd backend
uv run python -m marocassist.knowledge.loader ../knowledge
```

- `MAROCASSIST_EDITORIAL_TENANT_ID` must be set. Without it, the loader
  refuses to publish and exits with code 2.
- It replaces all knowledge in one transaction. Readers see either the old
  content or the new content, never a mix.
- It writes one audit row in the editorial tenant, with the content
  version and counts and no text.
- It prints `published <version> as <id>`. When the content is unchanged,
  it prints `unchanged: ...` and does nothing, so deploying twice is safe.

Nobody edits knowledge in the database by hand. The application cannot
write it at all.

## 8. Keeping content current

### Daily review report

Once per UTC day the worker writes a report into the editorial tenant
(`knowledge_review_reports`). It lists:

- content that is expired, or due within 14 days;
- facts under review, and facts in conflict;
- user reports ("outdated", "incorrect", "broken link", "other") from
  yesterday, and per item over the last 7 days.

It contains ids, dates and counts only. Phase 3 has no editor screen; a
platform operator reads the report from the database. An editor screen is
planned for later.

### What to do

| Report line | Action |
|---|---|
| Expired | Re-check against the official page. If unchanged, set a new `verified_at` and `review_due_at` and get it reviewed. If changed, update it. The site already shows "not recently verified" for expired content. |
| Due soon | Re-check it before it expires |
| Conflict | Find out which value is right. Withdraw or end (`valid_until`) the wrong one. Until then, users see both values with their sources. |
| User reports | Re-check the item, whatever its date |
| Source gone | If it was confirmed removed, set it to `withdrawn`. If it is only unreachable, set it to `expired` and try again from another network. |

### Withdrawing or replacing

- Set the item's `status` to `withdrawn`. When a new item replaces it, set
  `superseded_by` to the new item's id.
- Withdrawn items are never shown as current. The item page links to the
  successor.
- Publish as usual. Withdrawal takes effect on the next deploy.

## 9. Fixed answer texts

The fixed sentences the future assistant uses are in
`backend/src/marocassist/knowledge/answer_texts.json`:

- the notices for expired, conflicting, secondary-only and under-review
  content;
- "I cannot confirm this";
- the question "which consulate?".

Editors own their wording, in all four languages. A change is a code PR, and
the French and Arabic texts need the native-speaker review.
