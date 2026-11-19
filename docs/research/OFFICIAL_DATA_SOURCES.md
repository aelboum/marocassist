# Official data sources

Status: Phase 0 research, 2026-11-19. Desk research only; several Moroccan
government sites were unreachable from the audit environment (see
`RDV_INTEGRATION_ASSESSMENT.md`, section 1).

## 1. Source inventory

| Source | Owner (as found) | Content relevant to MarocAssist | Machine access | Reuse terms | Status |
|---|---|---|---|---|---|
| idarati.ma | Ministère de la Transition Numérique et de la Réforme de l'Administration | National portal of administrative procedures and formalities; e-services; AI chatbot | No API or open-data feed mentioned on home page, terms or legal notice | Legal notice prohibits reproduction, representation, modification, publication or adaptation of any part of the site without the ministry's prior written authorisation (`/mentions-legales`). Processing declared to CNDP (D-PO-1692/2025). | VERIFIED (site reachable, terms read by research agent) |
| consulat.ma | Presumed MAECAMRE | Consular services catalogue (registration, CNIE, passport, laissez-passer, criminal record, legalisation, civil status) | Unknown | Unknown | NOT VERIFIED (unreachable) |
| rdv.consulat.ma | Presumed MAECAMRE | Appointment workflow | None documented | Unknown | NOT VERIFIED (unreachable) |
| diplomatie.ma | MAECAMRE | Ministry news, consular notices | Unknown | Unknown | NOT VERIFIED (HTTP 522 / WAF rejection) |
| data.gov.ma | Agence de Développement du Digital (ADD) | National open-data portal; reportedly CKAN-based; no consular dataset found | Reportedly CKAN API | Licence page exists per secondary sources; name and terms unknown | NOT VERIFIED (unreachable) |
| passeport.ma | DGSN | Passport procedure | Unknown | Unknown | NOT VERIFIED (TLS error) |
| cnie.ma, watiqa.ma, Marocains du Monde ministry | Various | CNIE, civil-status extracts, diaspora services | Not attempted | Unknown | NOT VERIFIED |
| rijksoverheid.nl list of Moroccan posts in NL | Dutch government | Addresses and contacts of the embassy and four consulates-general | HTML | Dutch government content reuse is generally permitted, but confirm the specific page's terms | VERIFIED (contents), terms NOT VERIFIED |

Moroccan posts in the Netherlands (VERIFIED, rijksoverheid.nl; cross-checked
with Wikipedia): Embassy in The Hague; Consulates-General in Amsterdam,
's-Hertogenbosch, Rotterdam (address in Schiedam) and Utrecht.

## 2. Consequences for the knowledge platform

1. **No source has a verified machine-readable feed or reuse licence.** Bulk
   scraping and republishing official content is therefore excluded.
   (RECOMMENDATION)
2. **Content model: curated, paraphrased, cited.** MarocAssist editors write
   procedure records in their own words (Dutch first), each fact linked to the
   official page it came from, with a `last_verified_at` date. Short
   quotations only where legally acceptable. (RECOMMENDATION; needs legal
   confirmation, see Q-K1)
3. **Source snapshots for provenance**, not for republication: when an editor
   verifies a fact, the system stores the URL, retrieval time, content hash
   and (optionally, privately) the fetched text, so changes can be detected.
   Whether storing a private copy is acceptable is legal question Q-K2.
4. **Freshness checks** run as scheduled jobs that fetch the cited official
   pages (low rate, identified User-Agent, robots.txt respected) and flag a
   record for re-review when the hash changes. Because Moroccan sites may
   block non-Moroccan or data-centre IPs, the checker must tolerate
   unreachability and must not be worked around with proxies that disguise
   the origin. (RECOMMENDATION)
5. **Permissions**: the owner should request written reuse authorisation from
   the idarati.ma publisher and MAECAMRE before any verbatim reuse. Phase 0
   contacts nobody.

## 3. Legal questions

| # | Question |
|---|---|
| Q-K1 | Is paraphrasing official procedure information with citations acceptable without authorisation under Moroccan copyright law, given idarati's reservation? (Moroccan counsel) |
| Q-K2 | May MarocAssist keep private snapshots of official pages for provenance and change detection? |
| Q-K3 | What disclaimers are required when presenting official procedure information, so the product never appears to be an official source? |
| Q-K4 | data.gov.ma licence terms, once the site is reachable. |

## 4. Owner follow-up (read-only)

From a residential connection: open consulat.ma, diplomatie.ma, data.gov.ma,
passeport.ma, cnie.ma and watiqa.ma; save their legal notices and terms; list
the consular services and per-consulate pages relevant to the Netherlands.
Store the evidence with dates under `docs/research/evidence/`.
