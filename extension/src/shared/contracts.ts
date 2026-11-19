/**
 * Shared contracts between content script, service worker and side panel.
 *
 * A `PageSnapshot` describes the *structure* of an allow-listed page so the
 * side panel can explain it. It never carries what the user typed or
 * selected, nor any password field, hidden field (CSRF tokens live there),
 * cookie, storage value, URL query or fragment. Everything is plain text,
 * length-capped, and validated again by the service worker.
 */

export const SNAPSHOT_VERSION = 1;
export const MAX_TEXT = 160;
export const MAX_ITEMS = 50;

export type FieldKind =
  | "text"
  | "email"
  | "tel"
  | "date"
  | "number"
  | "select"
  | "radio"
  | "checkbox"
  | "textarea"
  | "file"
  | "other";

export interface FieldInfo {
  /** Reference within this snapshot (index-based, never an id taken from the page). */
  ref: string;
  label: string;
  kind: FieldKind;
  required: boolean;
  /** A validation message the page shows for this field, if any. */
  error: string | null;
}

export interface PageSnapshot {
  version: typeof SNAPSHOT_VERSION;
  /** Origin and path only: no query string, no fragment. */
  location: string;
  title: string;
  headings: string[];
  fields: FieldInfo[];
  buttons: string[];
  alerts: string[];
  /** A CAPTCHA widget is present. The extension never interacts with it. */
  captchaPresent: boolean;
  capturedAt: number;
}

export type ContentToBackground = { type: "snapshot"; snapshot: PageSnapshot };

export type BackgroundToPanel =
  | { type: "snapshot"; tabId: number; snapshot: PageSnapshot }
  | { type: "cleared"; tabId: number }
  | { type: "access"; granted: boolean };

export type PanelToBackground = { type: "panel-ready" } | { type: "test-site-access-granted" };

export const PANEL_PORT = "marocassist-sidepanel";

const FIELD_KINDS: ReadonlySet<string> = new Set([
  "text",
  "email",
  "tel",
  "date",
  "number",
  "select",
  "radio",
  "checkbox",
  "textarea",
  "file",
  "other",
]);

function isText(value: unknown, max = MAX_TEXT): value is string {
  return typeof value === "string" && value.length <= max;
}

function isTextList(value: unknown): value is string[] {
  return Array.isArray(value) && value.length <= MAX_ITEMS && value.every((v) => isText(v));
}

function isField(value: unknown): value is FieldInfo {
  if (!value || typeof value !== "object") return false;
  const f = value as Record<string, unknown>;
  return (
    Object.keys(f).sort().join(",") === "error,kind,label,ref,required" &&
    isText(f.ref, 16) &&
    isText(f.label) &&
    typeof f.kind === "string" &&
    FIELD_KINDS.has(f.kind) &&
    typeof f.required === "boolean" &&
    (f.error === null || isText(f.error))
  );
}

/** Strict schema check: exact key set, types and size limits. */
export function isPageSnapshot(value: unknown): value is PageSnapshot {
  if (!value || typeof value !== "object") return false;
  const s = value as Record<string, unknown>;
  return (
    Object.keys(s).sort().join(",") ===
      "alerts,buttons,captchaPresent,capturedAt,fields,headings,location,title,version" &&
    s.version === SNAPSHOT_VERSION &&
    isText(s.location, 512) &&
    !String(s.location).includes("?") &&
    !String(s.location).includes("#") &&
    isText(s.title) &&
    isTextList(s.headings) &&
    isTextList(s.buttons) &&
    isTextList(s.alerts) &&
    Array.isArray(s.fields) &&
    s.fields.length <= MAX_ITEMS &&
    s.fields.every(isField) &&
    typeof s.captchaPresent === "boolean" &&
    typeof s.capturedAt === "number"
  );
}
