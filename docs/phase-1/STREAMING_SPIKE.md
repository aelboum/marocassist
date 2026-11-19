# Work package F — Streaming technical spike

Status: Phase 1, 2026-11-19. Research spike: part A implemented and measured,
part B assessed only (no provider code, no provider account, nothing sent to
any AI provider).

## A. DOM reactivity (implemented)

| Item | Result | Evidence |
|---|---|---|
| Change detection | `MutationObserver` on the document (`childList`, `subtree`, `characterData`, filtered `attributes`), debounced 150 ms, emits only when the value-free snapshot changes | `extension/src/content/observer.ts` |
| Typing is not observed | Setting an input's value changes no DOM node; no snapshot is emitted | `observer.test.ts` "does not emit when the user only types" — VERIFIED |
| Latency to side panel | 297 ms and 486 ms in two Chromium E2E runs (validation error injected by the page → side panel updated) | `e2e/extension.e2e.mjs` — VERIFIED (< 1 s target) |
| Transport | content script → `chrome.runtime.sendMessage` → service worker (validated) → `Port` to side panel | `background/index.ts`, `security.test.ts` |

Conclusion: done for Phase 1. Phase 5 adds per-page recognition rules on top.

## B. AI token streaming (assessed)

### What SaaS-OS v0.15.0 provides — VERIFIED at the pin

- `saas_os.inference.stream_inference` exists but refuses **every** request
  with `InferenceUnsupportedCapabilityError("streaming_not_enabled")` before
  anything is read or sent (`saas_os/control_plane/inference/service.py:1193`).
- Six release criteria must pass first (AI-INFERENCE-CONTRACTS §6.6):
  adapter conformance (abrupt close, malformed event, mid-stream error,
  missing usage); connection closed on break/cancel/deadline; no retry or
  fallback after the first delta; interrupted attempts in the ledger with
  usage mirrored once; open streams counted by per-tenant concurrency;
  canary-credential test on streaming error paths.
- Upstream issue #206 ("Enable stream_inference …") is **OPEN**
  (last updated 2026-11-03, `gh issue view`).
- `run_inference` (non-streaming) is governed: authority, tenant policy,
  use-case grant, classification, entitlement, quota, budget, concurrency
  lease, attempt ledger, audit of denials, egress policy.

### Options

| # | Option | Governance | Verdict |
|---|---|---|---|
| 1 | Direct provider streaming from backend, web or extension | Bypasses attempt ledger, budgets, classification, egress, audit | **Rejected** (brief: never bypass SaaS-OS governance; never a direct provider connection from frontend or extension) |
| 2 | Progress streaming: one governed `run_inference` call; the route streams status events over SSE (`queued`, `retrieving`, `generating`, `done`/`error`) and then the full answer | Unchanged (one governed call) | **Possible now**; improves perceived latency without tokens |
| 3 | Staged answers: several smaller governed calls (outline, then sections), each result pushed over SSE as it completes | Each call governed and audited | Possible; higher cost and latency overhead; use only if eval shows benefit |
| 4 | True token streaming via `stream_inference` once SaaS-OS enables it | Governed by SaaS-OS | **Target** (Phase 6, upstream U-3 / #206) |

### Implementation notes for options 2 and 4 (RECOMMENDATION)

- Transport: Server-Sent Events on the single origin (`text/event-stream`,
  FastAPI `StreamingResponse`). Web: `EventSource` or `fetch` streaming with
  the session cookie. Extension: `fetch` streaming from the service worker
  with `X-API-Key`, relayed to the side panel over the existing `Port`.
- Route policy: same `require_permission(...)` as any route; the tenant comes
  from `RequestContext`; one stream = one request = one tenant.
- Rate limiting: the per-request limiter of `require_permission` applies at
  stream start; SaaS-OS `AI_INFERENCE_TENANT_CONCURRENCY` (default 4) bounds
  concurrent inference per tenant. A product cap on open SSE connections per
  tenant is needed (not provided by SaaS-OS).
- Audit: SaaS-OS records each attempt before sending; MarocAssist adds no
  content to logs. Stream lifecycle events (started, finished, cancelled)
  as metrics, not content.
- Errors: every `InferenceError` category maps to one SSE `event: error`
  with a stable code; no automatic retry after the first delta (mirrors
  SaaS-OS criterion 3); a reconnect starts a new request (and a new cost).
- Edge: Caddy `reverse_proxy` flushes `text/event-stream` responses
  immediately (Caddy default for that content type) — NOT VERIFIED locally.
- MV3 lifetime: a service worker can be stopped when idle; an active
  `fetch` response keeps it alive in current Chrome versions — NOT VERIFIED;
  fallback is streaming in the side panel page with a key handed over the
  `Port` for the duration of one request only.

### Risks

| Risk | Mitigation |
|---|---|
| Duplicate cost on reconnect | Idempotency key per question; no auto-retry |
| Long-held connections | Per-tenant SSE cap, server timeout, heartbeat |
| Proxy buffering | Verify through the edge before enabling |
| Partial answer shown, then error | UI marks the answer incomplete; never cached |
| Prompt-injected output streamed before checks | Option 4 needs post-checks per chunk or a hold-back window; option 2 checks the full answer before sending |

### Decision

**Not in Phase 1.** Phase 4 (assistant): option 2 if latency eval shows the
need (no SaaS-OS change). Phase 6 or later: option 4 after SaaS-OS enables
streaming. Option 1 is excluded.
