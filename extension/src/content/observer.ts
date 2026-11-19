/**
 * DOM reactivity: watch the page with a MutationObserver and emit a new
 * snapshot only when the page *structure* changed (debounced).
 *
 * The observer is configured without `characterData` on form controls'
 * values: typing into an input does not change the DOM tree and is never
 * observed. Attribute changes are limited to those that change the
 * snapshot (validation state, visibility, labels).
 */

import type { PageSnapshot } from "../shared/contracts";
import { buildSnapshot, snapshotKey } from "./extract";

export const DEBOUNCE_MS = 150;

const OBSERVED_ATTRIBUTES = ["aria-invalid", "aria-describedby", "aria-hidden", "hidden", "required", "aria-label", "class"];

export interface PageObserver {
  stop(): void;
}

export function observePage(
  document: Document,
  location: Location | URL,
  emit: (snapshot: PageSnapshot) => void,
  debounceMs = DEBOUNCE_MS,
): PageObserver {
  let lastKey = "";
  let timer: ReturnType<typeof setTimeout> | undefined;

  const publish = () => {
    timer = undefined;
    const snapshot = buildSnapshot(document, location);
    const key = snapshotKey(snapshot);
    if (key === lastKey) return;
    lastKey = key;
    emit(snapshot);
  };

  const observer = new MutationObserver(() => {
    if (timer !== undefined) clearTimeout(timer);
    timer = setTimeout(publish, debounceMs);
  });
  observer.observe(document.documentElement, {
    subtree: true,
    childList: true,
    characterData: true,
    attributes: true,
    attributeFilter: OBSERVED_ATTRIBUTES,
  });
  publish();

  return {
    stop() {
      observer.disconnect();
      if (timer !== undefined) clearTimeout(timer);
    },
  };
}
