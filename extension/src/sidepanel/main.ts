/**
 * Side panel entry. Connects to the service worker over a named port,
 * re-renders on every snapshot, and asks for the optional host permission
 * only when the user clicks the button (a user gesture is required).
 */

import { HOST_PERMISSION_PATTERNS } from "../shared/allowlist";
import { type BackgroundToPanel, PANEL_PORT, type PanelToBackground } from "../shared/contracts";
import { renderSnapshot } from "./render";

const root = document.getElementById("content") as HTMLElement;
const accessButton = document.getElementById("grant-access") as HTMLButtonElement;
const port = chrome.runtime.connect({ name: PANEL_PORT });

function send(message: PanelToBackground): void {
  port.postMessage(message);
}

port.onMessage.addListener((message: BackgroundToPanel) => {
  if (message.type === "access") {
    accessButton.hidden = message.granted;
  } else if (message.type === "snapshot") {
    renderSnapshot(root, message.snapshot);
  } else if (message.type === "cleared") {
    renderSnapshot(root, null);
  }
});

accessButton.addEventListener("click", () => {
  void chrome.permissions.request({ origins: [...HOST_PERMISSION_PATTERNS] }).then((granted) => {
    if (granted) send({ type: "test-site-access-granted" });
  });
});

renderSnapshot(root, null);
send({ type: "panel-ready" });
