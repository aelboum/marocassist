/**
 * Content script. Injected only into allow-listed pages, and only after the
 * user granted the optional host permission (registered by the service
 * worker). Read-only: it never writes to the page, never sets a value,
 * never clicks, submits or navigates, and makes no network request.
 */

import { isAllowedUrl } from "../shared/allowlist";
import type { ContentToBackground } from "../shared/contracts";
import { observePage } from "./observer";

if (isAllowedUrl(window.location.href)) {
  observePage(document, window.location, (snapshot) => {
    const message: ContentToBackground = { type: "snapshot", snapshot };
    chrome.runtime.sendMessage(message).catch(() => {
      // The service worker may be restarting; the next change resends.
    });
  });
}
