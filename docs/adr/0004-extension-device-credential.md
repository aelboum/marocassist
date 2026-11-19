# ADR-0004: Extension credential = short-lived service-account key per device

Status: Accepted for development and closed beta; re-assess before public
launch (spike result 2026-11-19; analysis in
`docs/phase-1/EXTENSION_AUTH.md`).

## Decision

Pairing a browser creates a SaaS-OS service account in the user's personal
tenant with only the `copilot_client` role (`marocassist.copilot:use`) and
one API key that expires in at most 12 hours. Only routes declared with
`require_permission(COPILOT, USE, api_key=True)` accept it. Renewal is a new
pairing from the signed-in web app; there is no self-rotation. Revoking a
device revokes its keys and disables the service account. At most
`MAROCASSIST_COPILOT_MAX_DEVICES` active devices per tenant.

## Rejected

Session cookie or session secret in the extension; long-lived keys; a
product-specific token system.

## Residual risk

Bearer key without sender constraint (SaaS-OS v0.15.0 has none). Upstream
proposal U-6: token exchange / device grant with DPoP-bound refresh.
