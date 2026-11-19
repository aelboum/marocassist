/**
 * The only pages the Copilot may observe. Phase 1: the local test website
 * only. `rdv.consulat.ma` is NOT on this list; adding it is a Phase 5
 * decision (D-11) that also needs the legal review (D-18).
 *
 * This list must match `optional_host_permissions` in manifest.json
 * (checked by tests/manifest.test.ts).
 */

export const ALLOWED_ORIGINS: readonly string[] = ["http://localhost:8090"];
export const HOST_PERMISSION_PATTERNS: readonly string[] = ALLOWED_ORIGINS.map((origin) => `${origin}/*`);

export function isAllowedUrl(raw: string | undefined | null): boolean {
  if (!raw) return false;
  try {
    return ALLOWED_ORIGINS.includes(new URL(raw).origin);
  } catch {
    return false;
  }
}
