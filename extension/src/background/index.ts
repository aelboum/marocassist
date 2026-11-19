/**
 * Service worker: the only component that talks to both the content script
 * and the side panel.
 *
 * - Content scripts are registered dynamically, only for allow-listed
 *   origins whose optional host permission the user granted.
 * - Every incoming message is checked (`acceptSnapshot`): it must come from
 *   this extension, from an allow-listed tab, and match the strict snapshot
 *   schema. Anything else is dropped.
 * - The latest snapshot per tab is kept in `chrome.storage.session`
 *   (memory only, cleared when the browser closes, not exposed to content
 *   scripts) so the side panel can show it after a worker restart.
 * - Phase 1 sends nothing to any server.
 */

import { HOST_PERMISSION_PATTERNS, isAllowedUrl } from "../shared/allowlist";
import {
  type BackgroundToPanel,
  isPageSnapshot,
  PANEL_PORT,
  type PanelToBackground,
} from "../shared/contracts";
import { acceptSnapshot } from "./validate";

const CONTENT_SCRIPT_ID = "marocassist-observer";
const panels = new Set<chrome.runtime.Port>();

function storageKey(tabId: number): string {
  return `snapshot:${tabId}`;
}

function broadcast(message: BackgroundToPanel): void {
  for (const port of panels) port.postMessage(message);
}

async function syncContentScripts(): Promise<boolean> {
  const granted = await chrome.permissions.contains({ origins: [...HOST_PERMISSION_PATTERNS] });
  const existing = await chrome.scripting.getRegisteredContentScripts({ ids: [CONTENT_SCRIPT_ID] });
  if (granted && existing.length === 0) {
    await chrome.scripting.registerContentScripts([
      {
        id: CONTENT_SCRIPT_ID,
        js: ["content.js"],
        matches: [...HOST_PERMISSION_PATTERNS],
        runAt: "document_idle",
      },
    ]);
  } else if (!granted && existing.length > 0) {
    await chrome.scripting.unregisterContentScripts({ ids: [CONTENT_SCRIPT_ID] });
  }
  return granted;
}

async function sendLatest(port: chrome.runtime.Port): Promise<void> {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (tab?.id === undefined) return;
  const stored = await chrome.storage.session.get(storageKey(tab.id));
  const snapshot: unknown = stored[storageKey(tab.id)];
  const message: BackgroundToPanel = isPageSnapshot(snapshot)
    ? { type: "snapshot", tabId: tab.id, snapshot }
    : { type: "cleared", tabId: tab.id };
  port.postMessage(message);
}

chrome.runtime.onInstalled.addListener(() => {
  void chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true });
  void syncContentScripts();
});
chrome.runtime.onStartup.addListener(() => void syncContentScripts());
chrome.permissions.onAdded.addListener(() => void syncContentScripts());
chrome.permissions.onRemoved.addListener(() => void syncContentScripts());

chrome.runtime.onMessage.addListener((message: unknown, sender) => {
  const snapshot = acceptSnapshot(message, sender, chrome.runtime.id);
  const tabId = sender.tab?.id;
  if (snapshot === null || tabId === undefined) return false;
  void chrome.storage.session.set({ [storageKey(tabId)]: snapshot });
  broadcast({ type: "snapshot", tabId, snapshot });
  return false;
});

chrome.tabs.onActivated.addListener(() => {
  for (const port of panels) void sendLatest(port);
});
chrome.tabs.onRemoved.addListener((tabId) => {
  void chrome.storage.session.remove(storageKey(tabId));
  broadcast({ type: "cleared", tabId });
});
chrome.tabs.onUpdated.addListener((tabId, change) => {
  // Leaving an allow-listed page clears its snapshot.
  if (change.url !== undefined && !isAllowedUrl(change.url)) {
    void chrome.storage.session.remove(storageKey(tabId));
    broadcast({ type: "cleared", tabId });
  }
});

chrome.runtime.onConnect.addListener((port) => {
  if (port.name !== PANEL_PORT || port.sender?.id !== chrome.runtime.id) {
    port.disconnect();
    return;
  }
  panels.add(port);
  port.onDisconnect.addListener(() => panels.delete(port));
  port.onMessage.addListener((message: PanelToBackground) => {
    if (message.type === "panel-ready" || message.type === "test-site-access-granted") {
      void syncContentScripts().then((granted) => {
        port.postMessage({ type: "access", granted } satisfies BackgroundToPanel);
        return sendLatest(port);
      });
    }
  });
});
