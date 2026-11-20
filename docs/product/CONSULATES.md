# Consulates of Morocco in the Netherlands: product data model and verification

Status: 2026-11-20. Owner decision (Phase 2 approval): the first product version
uses four consulates — Amsterdam, Rotterdam, Utrecht and 's-Hertogenbosch. The
physical location of the Rotterdam-region consulate is shown as **Schiedam**
when the official address confirms it.

No product database, migration or API was changed for this document. The product
stores only a consulate **code** in `profiles.consulate_code` (Phase 2,
migration `0002_marocassist_profile`). Addresses, opening hours and jurisdiction
are **not** published in the product.

## 1. Separation of concerns

These four attributes are kept apart. Each one changes on its own and needs its
own source:

| Attribute | Meaning | Where it lives today | Status |
|---|---|---|---|
| Consulate code | Stable internal key | `profiles.consulate_code`, `CONSULATE_CODES` in `web/lib/i18n.ts`, `CONSULATES` in `backend/src/marocassist/accounts/profile.py` | Implemented (Phase 2) |
| Consulate name | Display name, per language | i18n keys `consulate.<code>` (NL/FR/AR/EN) | Implemented; FR/AR need review (P2-F5) |
| Physical location (city) | Where the office actually is | Not in the product | Documented below; not published |
| Official address | Street, postcode, city | Not in the product | Documented below; not published |
| Jurisdiction (ressort) | Which municipalities each consulate serves | Not in the product | **Not verified**: no official source found |

The code `nl-rotterdam` and the name "Consulaat-generaal Rotterdam" stay as they
are. The Schiedam location belongs in the separate physical-location and address
fields, which a later, approved work package (Phase 3, knowledge platform) will
add. Renaming the code would change stored profile data and is not needed.

## 2. Official data found (not yet published in the product)

Source: Rijksoverheid, "Marokko — ambassades, consulaten en overige
vertegenwoordigingen"
(https://www.rijksoverheid.nl/onderwerpen/ambassades-consulaten-en-overige-vertegenwoordigingen/overzicht-landen-en-gebieden/marokko),
read 2026-11-20. The page shows no date of last change.

| Code | Name on the Rijksoverheid list | Visiting address | Postcode | City |
|---|---|---|---|---|
| `nl-amsterdam` | Consulaat-Generaal van het Koninkrijk Marokko (Amsterdam) | Vondelstraat 65-67 | 1054 GK | Amsterdam |
| `nl-rotterdam` | Consulaat-Generaal van het Koninkrijk Marokko (**Schiedam**) | De Brauwweg 38-44 | 3125 AE | **Schiedam** |
| `nl-utrecht` | Consulaat-Generaal van het Koninkrijk Marokko (Utrecht) | Kanaalweg 95 D/E | 3533 HH | Utrecht |
| `nl-den-bosch` | Consulaat-Generaal van het Koninkrijk Marokko ('s-Hertogenbosch) | Larenweg 46 | 5234 KA | 's-Hertogenbosch |

### Verification status

- **One official source only.** This is the Dutch government list. It has not
  yet been cross-checked against a Moroccan source (the Moroccan Ministry of
  Foreign Affairs, consulat.ma, or each consulate's own site).
- **Rotterdam vs Schiedam.** The Rijksoverheid list places the Rotterdam-region
  consulate in Schiedam (De Brauwweg 38-44). Third-party directories still show
  an older Rotterdam address (Calandstraat 11); they are not authoritative and
  are not used. The Rijksoverheid list itself names the office "(Schiedam)". The
  owner must decide whether the display name stays "Rotterdam" with location
  Schiedam (current owner instruction) or follows the list's naming.
- **Opening hours:** not on the official list. Not verified, not published.
- **Jurisdiction (ressort):** not on the official list. Not verified, not
  published.

## 3. Before publishing addresses in the product

1. Confirm each address against a second, Moroccan official source, and record
   the source URL and date per row.
2. Obtain the official jurisdiction per consulate (which municipalities belong
   to which consulate) from an official source. Do not derive it.
3. Add the location, address and jurisdiction fields only in an approved
   Phase 3 work package. Store each row with source URL and verification date,
   and re-verify periodically.
4. Never show unverified opening hours. Link to the official source instead.
