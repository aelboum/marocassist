# API contracts

`openapi.json` is the backend's OpenAPI document, generated from the
application (`cd backend && uv run python -m tests.export_openapi`).
`backend/tests/test_unit.py::test_openapi_contract_is_up_to_date` fails when
the committed file and the running application differ, so every API change
is visible in review.

The extension's message contracts (content script ↔ service worker ↔ side
panel) live in `extension/src/shared/contracts.ts`; they are internal to the
extension and never leave the browser in Phase 1.

Phase 2 may generate TypeScript types from `openapi.json` for the web app
and the extension; Phase 1 keeps the small hand-written client in
`web/lib/api.ts`.
