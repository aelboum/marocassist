/**
 * Presentation rules for curated knowledge (Phase 3 WP E). Pure functions,
 * unit-tested; the components only render what these return.
 *
 * - Every text from the knowledge store is rendered as plain text. Item
 *   bodies use one structure only, `## Heading` lines and paragraphs
 *   (enforced by the loader); nothing else is interpreted, so no markup
 *   from content ever reaches the DOM.
 * - Outbound links are shown only for `https:` URLs (the loader already
 *   allow-lists the domains; this is a second check in the browser).
 * - Content keeps its own language and direction (`lang`, `dir`), which
 *   can differ from the UI language: a French text in the Arabic UI stays
 *   left-to-right.
 */

import type { ConsulateAttribute, ItemStatus, SourceCard } from "@/lib/api";
import type { MessageKey } from "@/lib/i18n";

export type BodyBlock = { kind: "heading"; text: string } | { kind: "paragraph"; text: string };

const HEADING = /^##[ \t]+(\S.*)$/;

export function bodyBlocks(body: string): BodyBlock[] {
  const blocks: BodyBlock[] = [];
  let paragraph: string[] = [];
  const flush = () => {
    const text = paragraph.join(" ").replace(/\s+/g, " ").trim();
    if (text) blocks.push({ kind: "paragraph", text });
    paragraph = [];
  };
  for (const line of body.split(/\r?\n/)) {
    const heading = HEADING.exec(line);
    if (heading) {
      flush();
      blocks.push({ kind: "heading", text: (heading[1] ?? "").trim() });
    } else if (line.trim() === "") {
      flush();
    } else {
      paragraph.push(line.trim());
    }
  }
  flush();
  return blocks;
}

export function contentDir(lang: string | null | undefined): "rtl" | "ltr" {
  return lang === "ar" ? "rtl" : "ltr";
}

/** The URL if it is an absolute https URL without credentials, else null. */
export function safeExternalUrl(url: string): string | null {
  try {
    const parsed = new URL(url);
    return parsed.protocol === "https:" && !parsed.username && !parsed.password ? parsed.href : null;
  } catch {
    return null;
  }
}

/** The notice an item shows, or null when it is current (rights doc 7). */
export function itemNotice(status: ItemStatus): MessageKey | null {
  if (status === "expired") return "kn.notice.expired";
  if (status === "withdrawn") return "kn.notice.withdrawn";
  return null;
}

export function sourceNotice(status: SourceCard["status"]): MessageKey | null {
  if (status === "expired") return "kn.notice.expired";
  if (status === "withdrawn") return "kn.notice.withdrawn";
  if (status === "unverified") return "kn.notice.unverified";
  return null;
}

const BADGES: Record<SourceCard["badge"], MessageKey> = {
  official: "kn.badge.official",
  secondary: "kn.badge.secondary",
  explanation: "kn.badge.explanation",
};

export function badgeKey(badge: SourceCard["badge"]): MessageKey {
  return BADGES[badge];
}

export type ScopeLabel = { key: MessageKey; code: string | null };

/** "Applies to" for a scope such as `consulate:nl-rotterdam`. */
export function scopeLabel(scope: string): ScopeLabel {
  if (scope.startsWith("consulate:")) return { key: "kn.scope.consulate", code: scope.slice("consulate:".length) };
  if (scope.startsWith("country:")) return { key: "kn.scope.country", code: scope.slice("country:".length) };
  if (scope.startsWith("region:")) return { key: "kn.scope.region", code: null };
  return { key: "kn.scope.global", code: null };
}

const VALUE_FIELDS = ["street", "postcode", "city", "phone", "email", "website"] as const;

/** An attribute value as display lines. Unknown shapes show nothing rather
 * than raw JSON. */
export function attributeLines(attribute: ConsulateAttribute): string[] {
  const value = attribute.value;
  if (typeof value === "string" || typeof value === "number") return [String(value)];
  if (!value || typeof value !== "object" || Array.isArray(value)) return [];
  const record = value as Record<string, unknown>;
  const text = (key: string) => (typeof record[key] === "string" ? (record[key] as string).trim() : "");
  if (attribute.attribute === "address") {
    return [text("street"), [text("postcode"), text("city")].filter(Boolean).join(" ")].filter(Boolean);
  }
  return VALUE_FIELDS.map(text).filter(Boolean);
}

export const ATTRIBUTE_KEYS: Record<string, MessageKey> = {
  display_name: "kn.attr.display_name",
  physical_city: "kn.attr.physical_city",
  address: "kn.attr.address",
  contact: "kn.attr.contact",
  opening_hours: "kn.attr.opening_hours",
};

export const REPORT_REASONS = ["outdated", "incorrect", "broken_link", "other"] as const;
export type ReportReason = (typeof REPORT_REASONS)[number];

export const REASON_KEYS: Record<ReportReason, MessageKey> = {
  outdated: "kn.reason.outdated",
  incorrect: "kn.reason.incorrect",
  broken_link: "kn.reason.broken_link",
  other: "kn.reason.other",
};
