/**
 * Build a `PageSnapshot` from the DOM: structure only, never values.
 *
 * Read: headings, field labels and types, required flags, visible
 * validation messages, button labels, alerts, whether a CAPTCHA is present.
 * Never read: `.value`, `.checked`, `.selectedIndex`, `.files`, password
 * and hidden inputs (skipped entirely), cookies, storage, the URL query or
 * fragment. Long digit runs in page text are masked, because a page may
 * echo a user-entered number (passport, phone) in an error message.
 *
 * Pure function of the document: no network, no DOM writes, no events.
 */

import {
  type FieldInfo,
  type FieldKind,
  MAX_ITEMS,
  MAX_TEXT,
  type PageSnapshot,
  SNAPSHOT_VERSION,
} from "../shared/contracts";

// Field names that mark a credential or payment field. Not "pass": that also
// matches "passport", a field the Copilot must be able to explain.
const SENSITIVE_NAME = /password|passwd|pwd|token|csrf|xsrf|secret|captcha|\botp\b|\bpin\b|cvc|cvv|iban|card[-_]?num/i;
const CAPTCHA_HINT = /captcha|recaptcha|hcaptcha|turnstile/i;

// A page may echo what the user typed inside a message ("Passport number
// AB1234567 is not valid"). Mask anything that looks like an identifier:
// e-mail addresses, phone-like digit runs, and every token with 3+ digits
// (passport, CNIE, dossier and phone numbers). Dates with 3+ digit years are
// masked too; that loss is accepted. Names cannot be detected reliably:
// residual risk, handled by consent before any page text leaves the browser
// (docs/phase-1/EXTENSION_PROTOTYPE.md).
const EMAIL = /[^\s@<>()]+@[^\s@<>()]+/g;
const PHONE = /\+?\d[\d\s().-]{6,}\d/g;
const NUMBERED_TOKEN = /[\p{L}\p{N}_-]*\d{3,}[\p{L}\p{N}_-]*/gu;

export function cleanText(raw: string | null | undefined): string {
  const collapsed = (raw ?? "").replace(/\s+/g, " ").trim();
  const masked = collapsed.replace(EMAIL, "•••").replace(PHONE, "•••").replace(NUMBERED_TOKEN, "•••");
  return masked.length > MAX_TEXT ? `${masked.slice(0, MAX_TEXT - 1)}…` : masked;
}

function kindOf(element: Element): FieldKind | null {
  if (element instanceof HTMLTextAreaElement) return "textarea";
  if (element instanceof HTMLSelectElement) return "select";
  if (!(element instanceof HTMLInputElement)) return null;
  const type = (element.getAttribute("type") ?? "text").toLowerCase();
  if (type === "password" || type === "hidden") return null;
  if (["submit", "button", "reset", "image"].includes(type)) return null;
  const known: FieldKind[] = ["text", "email", "tel", "date", "number", "radio", "checkbox", "file"];
  return (known as string[]).includes(type) ? (type as FieldKind) : "other";
}

function isSensitive(element: Element): boolean {
  const attributes = ["name", "id", "autocomplete"].map((a) => element.getAttribute(a) ?? "");
  return attributes.some((value) => SENSITIVE_NAME.test(value));
}

/**
 * Text of an element without what a user may have typed or chosen inside
 * it: nested form controls (prefilled textarea text, option lists) and
 * editable regions are removed from a copy before reading.
 */
export function staticText(element: Element | null): string {
  if (!element) return "";
  if (element.matches("[contenteditable]:not([contenteditable='false'])")) return "";
  const clone = element.cloneNode(true) as Element;
  clone
    .querySelectorAll("input, select, textarea, [contenteditable]:not([contenteditable='false'])")
    .forEach((node) => node.remove());
  return clone.textContent ?? "";
}

function textOfIds(document: Document, ids: string | null): string {
  if (!ids) return "";
  return ids
    .split(/\s+/)
    .map((id) => staticText(document.getElementById(id)))
    .join(" ");
}

function decodeSafely(segment: string): string {
  try {
    return decodeURIComponent(segment);
  } catch {
    return segment;
  }
}

/** Path with identifier-like segments masked (e.g. /dossier/AB1234567). */
export function maskedPath(pathname: string): string {
  return pathname
    .split("/")
    .map((segment) => (segment ? cleanText(decodeSafely(segment)).replace(/\s+/g, "") : segment))
    .join("/");
}

function labelOf(document: Document, element: Element): string {
  const aria = element.getAttribute("aria-label");
  if (aria) return cleanText(aria);
  const labelledBy = textOfIds(document, element.getAttribute("aria-labelledby"));
  if (labelledBy.trim()) return cleanText(labelledBy);
  const id = element.getAttribute("id");
  if (id) {
    for (const label of Array.from(document.querySelectorAll("label[for]"))) {
      if (label.getAttribute("for") === id) {
        const text = staticText(label);
        if (text.trim()) return cleanText(text);
      }
    }
  }
  const wrapping = element.closest("label");
  if (wrapping) {
    const text = staticText(wrapping);
    if (text.trim()) return cleanText(text);
  }
  return cleanText(element.getAttribute("placeholder") ?? "");
}

function errorOf(document: Document, element: Element): string | null {
  if (element.getAttribute("aria-invalid") !== "true") return null;
  const message = cleanText(textOfIds(document, element.getAttribute("aria-describedby")));
  return message || null;
}

function isRendered(element: Element): boolean {
  return !element.closest("[hidden], [aria-hidden='true']");
}

export function detectCaptcha(document: Document): boolean {
  const widgets = Array.from(document.querySelectorAll("[class*='captcha' i], [id*='captcha' i], [data-sitekey]"));
  if (widgets.some(isRendered)) return true;
  return Array.from(document.querySelectorAll("iframe")).some(
    (frame) => isRendered(frame) && CAPTCHA_HINT.test(frame.getAttribute("src") ?? ""),
  );
}

export function buildSnapshot(document: Document, location: Location | URL, now = Date.now()): PageSnapshot {
  const headings = Array.from(document.querySelectorAll("h1, h2, h3"))
    .filter(isRendered)
    .map((h) => cleanText(staticText(h)))
    .filter(Boolean)
    .slice(0, MAX_ITEMS);

  const fields: FieldInfo[] = [];
  for (const element of Array.from(document.querySelectorAll("input, select, textarea"))) {
    if (fields.length >= MAX_ITEMS) break;
    const kind = kindOf(element);
    if (kind === null || isSensitive(element) || !isRendered(element)) continue;
    fields.push({
      ref: `f${fields.length}`,
      label: labelOf(document, element),
      kind,
      required: element.hasAttribute("required") || element.getAttribute("aria-required") === "true",
      error: errorOf(document, element),
    });
  }

  const buttons = Array.from(
    document.querySelectorAll("button, input[type='submit'], input[type='button'], [role='button']"),
  )
    .filter(isRendered)
    .map((b) => cleanText(b instanceof HTMLInputElement ? b.getAttribute("value") : staticText(b)))
    .filter(Boolean)
    .slice(0, MAX_ITEMS);

  const alerts = Array.from(
    document.querySelectorAll("[role='alert'], [aria-live='assertive'], [aria-live='polite']"),
  )
    .filter(isRendered)
    .map((a) => cleanText(staticText(a)))
    .filter(Boolean)
    .slice(0, MAX_ITEMS);

  return {
    version: SNAPSHOT_VERSION,
    location: `${location.origin}${maskedPath(location.pathname)}`,
    title: cleanText(document.title),
    headings,
    fields,
    buttons,
    alerts,
    captchaPresent: detectCaptcha(document),
    capturedAt: now,
  };
}

/** Comparison key: the snapshot without its timestamp. */
export function snapshotKey(snapshot: PageSnapshot): string {
  return JSON.stringify({ ...snapshot, capturedAt: 0 });
}
