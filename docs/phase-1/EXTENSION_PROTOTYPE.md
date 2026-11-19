# Work package D — Copilot extension prototype

Status: Phase 1, 2026-11-19. Chrome Manifest V3, TypeScript + Vite, no
framework, no AI, no network calls.

## Components

| Part | File | Role |
|---|---|---|
| Manifest | `extension/manifest.json` | `permissions: sidePanel, storage, scripting`; **no** `host_permissions`, **no** static content scripts; `optional_host_permissions: http://localhost:8090/*`; strict extension-page CSP |
| Shared contracts | `src/shared/contracts.ts`, `allowlist.ts` | `PageSnapshot` schema + strict validator; allow-list of origins |
| Content script | `src/content/{extract,observer,index}.ts` | Read-only snapshot of structure; MutationObserver; masking |
| Service worker | `src/background/{index,validate}.ts` | Registers the content script only after the user grants access; validates sender + schema; `chrome.storage.session` per tab |
| Side panel | `sidepanel.html`, `src/sidepanel/{main,render}.ts` | Independence banner; renders with `textContent` only; "Allow on the local test page" button requests the optional permission |
| Test website | `extension/testsite/` (Compose `copilot-testsite`, port 8090) | Fictitious two-step form with a hidden CSRF canary, a password field, echoing validation errors and a CAPTCHA placeholder |

## What a snapshot contains (and never contains)

Contains: page title, origin + path, headings, field label/type/required,
visible validation messages, button labels, alert texts, "CAPTCHA present".

Never contains: field values, checked state, selected options, files,
password and hidden inputs, cookies, storage, URL query or fragment. Page
text is masked for e-mail addresses, phone-like numbers and any token with
three or more digits, because pages echo user input in error messages
(found by the E2E test: a 5-digit passport fragment slipped through the
first masking rule; fixed and covered by tests). Names in page text cannot
be detected reliably: residual risk, to be handled by explicit consent and a
preview before any page text leaves the browser (Phase 5).

## Hard rules enforced by tests

`extension/tests/security.test.ts` fails if source code (comments excluded)
sets a value, checks a box, clicks, submits, dispatches events, reads
cookies, makes a network request, injects HTML, navigates, evaluates code or
uses persistent storage; and if the manifest gains a permission beyond the
three above, a static host permission, `<all_urls>`, `externally_connectable`
or `consulat.ma`.

## How to run it

1. `docker compose up -d copilot-testsite`
2. `cd extension && npm ci && npm run build`
3. Chrome → `chrome://extensions` → Developer mode → Load unpacked → `extension/dist`
4. Click the toolbar icon (opens the side panel) → "Allow on the local test page"
5. Open `http://localhost:8090/index.html`, click "Next" with empty fields: the panel updates.
