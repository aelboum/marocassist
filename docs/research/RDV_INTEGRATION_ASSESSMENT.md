# RDV integration assessment (rdv.consulat.ma)

Status: Phase 0 research, 2026-11-19. Read-only desk research. No account was
created, no form submitted, no internal endpoint called.

Classification used throughout: **VERIFIED** (seen at the source),
**PARTIALLY VERIFIED**, **NOT VERIFIED**, **RECOMMENDATION**.

## 1. What could and could not be inspected

| Check | Result | Status |
|---|---|---|
| `https://rdv.consulat.ma/` from the audit workstation | DNS resolves to `194.204.218.70`; TCP connection to port 443 timed out after 10 s | VERIFIED (unreachable from this environment) |
| `https://rdv.consulat.ma/robots.txt` | Unreachable (same timeout); a separate web-fetch service got "connection refused" | VERIFIED (unreachable) |
| `https://www.consulat.ma/`, `https://data.gov.ma/` | Unreachable from both environments | VERIFIED (unreachable) |
| `https://www.idarati.ma/` | HTTP 200 | VERIFIED |
| Terms of use, legal notice, privacy notice of rdv.consulat.ma | Could not be read | NOT VERIFIED |
| CAPTCHA presence, languages offered, automation clauses | Could not be read | NOT VERIFIED |

The most likely explanation is geo- or network-based filtering of non-Moroccan or
data-centre traffic. That is an inference, **NOT VERIFIED**. If it is true, it
matters architecturally: a MarocAssist server could not even fetch public RDV
pages reliably, and only the user's own browser can see the site. That is
consistent with the browser-copilot approach this document recommends.

**Required follow-up (owner, manual, read-only):** from a normal residential
connection, open rdv.consulat.ma, save the terms of use, privacy notice and
legal notice, note the languages offered, whether a CAPTCHA appears and at
which step, and the robots.txt contents. Store them under
`docs/research/evidence/` with the date. Until then, every statement below
about the site's workflow is **NOT VERIFIED**.

## 2. What the site is (secondary sources only)

- Official online appointment platform for Moroccan consular posts abroad.
  **NOT VERIFIED** (secondary guides: lesmre.com, demarchesmaroc.com).
- Operator: presumed to be the Ministry of Foreign Affairs, African Cooperation
  and Moroccans Abroad (MAECAMRE). The Dutch government's list of Moroccan
  posts in the Netherlands shows `@maec.gov.ma` addresses for most posts
  (rijksoverheid.nl). **PARTIALLY VERIFIED** (domain only; operator of the RDV
  site itself not confirmed).
- Workflow described by third-party guides (**NOT VERIFIED**):
  1. Create an account (email as login), activate through an emailed link.
  2. Choose the consulate by place of residence.
  3. Choose the service; required documents are listed; some services need
     forms pre-filled online.
  4. Choose a slot on a calendar.
  5. Review and confirm; a confirmation email follows. Changes and
     cancellations happen in the personal account.
- Booking reportedly free; some consular services carry fees shown at
  service selection. **NOT VERIFIED**.

## 3. Integration options

| Option | Description | Availability | Status |
|---|---|---|---|
| 1. Official API | Server-to-server integration authorised by MAECAMRE | No public or partner API documentation found | NOT VERIFIED (absence of evidence only) |
| 2. Permitted partner integration | Contracted data/booking partnership | None known; would require a formal approach by the owner | NOT VERIFIED |
| 3. User-controlled browser guidance | Copilot in the user's own browser explains pages, translates, highlights; the user performs every action | Technically feasible with Chrome MV3; needs no RDV cooperation | RECOMMENDATION (MVP) |
| ~~Undocumented internal AJAX endpoints~~ | Calling endpoints observed in the site's own front end | **Excluded.** Undocumented internal interfaces, no authorisation | RECOMMENDATION: never use without written authorisation |

The architecture keeps a port for options 1 and 2 (`integrations/rdv/`
adapter interface, see `../architecture/SYSTEM_ARCHITECTURE.md`) with **no
implementation** until an authorisation exists. Option 3 is the only
integration in the MVP.

## 4. Hard rules for option 3 (RECOMMENDATION, binding for implementation)

1. The extension never submits a form, clicks a confirmation, selects a slot,
   or navigates on the user's behalf. Highlighting and explaining only.
2. No polling, auto-refresh, slot watching, slot alerts or any background
   request to rdv.consulat.ma. The extension makes **zero** network requests to
   RDV; it only reads the DOM of a tab the user opened.
3. No CAPTCHA handling of any kind (no detection-and-solve, no forwarding the
   CAPTCHA image to an AI, no "help me read this CAPTCHA").
4. No reading or transmitting of passwords, cookies, `localStorage` tokens,
   CSRF tokens or hidden inputs.
5. Field **values** are not sent to the backend by default; field labels,
   types, validation messages and page structure are (see
   `../architecture/BROWSER_COPILOT_ARCHITECTURE.md`, section 6).
6. No pricing tied to appointments ("pay for a slot"). MarocAssist sells
   guidance and preparation, never access to appointments.
7. Visual identity clearly distinct from the official site; the side panel
   says on every screen that MarocAssist is independent and not affiliated
   with the Moroccan government.

## 5. Risk context: appointment brokering

- BLS International (Spanish visas in Morocco) deployed multilayer
  anti-abuse controls (CAPTCHA, OTP, booking-anomaly detection) and ran a
  campaign against unauthorised agents; brokers resold slots for up to
  MAD 10,000. **VERIFIED** (Morocco World News, 22 Jul 2026,
  https://www.moroccoworldnews.com/2026/07/330812/bls-international-tightens-appointment-controls-to-curb-visa-broker-abuse-in-morocco/).
- Morocco reportedly urged foreign missions to block visa brokers; the Italian
  consulate in Morocco reportedly denounced intermediaries. **NOT VERIFIED**
  (secondary press: fr.hespress.com, bladi.net).
- Guides on Moroccan consulates warn that paid third-party appointment
  platforms are scams. **NOT VERIFIED** (search snippets).
- No official Moroccan consular statement on third-party assistance tools was
  found; consulat.ma could not be checked. **NOT VERIFIED**.

Consequence: being perceived as a slot broker or bot is the single largest
reputational and legal risk to the product. The rules in section 4 exist to
make that perception provably false, and the extension's code and Chrome Web
Store listing must be auditable against them.

## 6. Detection and change resilience

The RDV front end can change without notice. The copilot must:

- identify pages by URL pattern **and** structural fingerprints, never by a
  single CSS selector;
- degrade to "I don't recognise this page; here is general help" instead of
  guessing;
- keep page-recognition rules as versioned data shipped **inside** the
  extension package (MV3 forbids remotely loaded code; rules are data, not
  code), updated through store releases;
- report unknown-page events (URL path pattern only, no content) so the team
  knows when RDV changed.

Building the page-recognition rules needs real page structure. Because the
site is not reachable from the audit environment and the internal flow sits
behind a login, the rules must be authored from pages the owner (or a
consenting tester) captures in their own browser, with personal data removed
before the capture is stored in the repository.

## 7. Open questions (legal review required)

| # | Question | Owner |
|---|---|---|
| R1 | Do the RDV terms of use restrict third-party assistance tools or browser extensions operating on the site? | Owner to collect the terms; legal review |
| R2 | Does reading the DOM of a page the user is logged into, with the user's consent, raise any issue under Moroccan law (Law 09-08, cybercrime provisions of the Penal Code) or the site's terms? | Moroccan counsel |
| R3 | Is it lawful to describe the RDV workflow and reproduce screenshots or field labels in guidance content? | Moroccan counsel |
| R4 | Would MAECAMRE consider an official or partner channel? (Contact only after owner approval; Phase 0 contacts nobody.) | Owner |

None of these is presented as settled. They do not block Phase 1 (foundation),
but R1–R3 must be answered before the Copilot (Phase 5) is published to the
Chrome Web Store.
