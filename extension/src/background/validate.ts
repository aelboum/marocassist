import { isAllowedUrl } from "../shared/allowlist";
import { isPageSnapshot, type PageSnapshot } from "../shared/contracts";

/** Minimal shape of `chrome.runtime.MessageSender` used here (testable without Chrome). */
export interface SenderLike {
  id?: string;
  url?: string;
  tab?: { id?: number; url?: string };
}

/**
 * Accept a message only if it is a valid snapshot sent by this extension's
 * own content script, running in an allow-listed tab, describing that same
 * origin. Returns the snapshot or null.
 */
export function acceptSnapshot(message: unknown, sender: SenderLike, extensionId: string): PageSnapshot | null {
  if (sender.id !== extensionId) return null;
  if (sender.tab?.id === undefined || !isAllowedUrl(sender.tab.url) || !isAllowedUrl(sender.url)) return null;
  if (!message || typeof message !== "object") return null;
  const record = message as Record<string, unknown>;
  if (record.type !== "snapshot" || !isPageSnapshot(record.snapshot)) return null;
  const snapshot = record.snapshot;
  if (new URL(snapshot.location).origin !== new URL(sender.tab.url as string).origin) return null;
  return snapshot;
}
