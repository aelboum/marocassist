import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { observePage, type PageObserver } from "../src/content/observer";
import type { PageSnapshot } from "../src/shared/contracts";
import { loadTestPage, TEST_PAGE_URL } from "./helpers";

const DEBOUNCE = 20;
let observer: PageObserver | undefined;

function waitFor(predicate: () => boolean, timeoutMs = 1000): Promise<void> {
  const started = Date.now();
  return new Promise((resolve, reject) => {
    const tick = () => {
      if (predicate()) return resolve();
      if (Date.now() - started > timeoutMs) return reject(new Error("timed out"));
      setTimeout(tick, 5);
    };
    tick();
  });
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

beforeEach(() => loadTestPage(document));
afterEach(() => observer?.stop());

describe("MutationObserver", () => {
  it("emits an initial snapshot", () => {
    const emitted: PageSnapshot[] = [];
    observer = observePage(document, TEST_PAGE_URL, (s) => emitted.push(s), DEBOUNCE);
    expect(emitted).toHaveLength(1);
  });

  it("emits an updated snapshot within 1 s when a validation error appears", async () => {
    const emitted: PageSnapshot[] = [];
    observer = observePage(document, TEST_PAGE_URL, (s) => emitted.push(s), DEBOUNCE);
    const started = Date.now();
    document.getElementById("full-name")!.setAttribute("aria-invalid", "true");
    document.getElementById("full-name-error")!.textContent = "Please enter your full name.";
    document.getElementById("summary")!.textContent = "1 field(s) need attention.";
    await waitFor(() => emitted.length === 2);
    expect(Date.now() - started).toBeLessThan(1000);
    const latest = emitted[1]!;
    expect(latest.alerts).toEqual(["1 field(s) need attention."]);
    expect(latest.fields[0]!.error).toBe("Please enter your full name.");
  });

  it("emits when the page moves to the next step", async () => {
    const emitted: PageSnapshot[] = [];
    observer = observePage(document, TEST_PAGE_URL, (s) => emitted.push(s), DEBOUNCE);
    document.getElementById("step-1")!.hidden = true;
    document.getElementById("step-2")!.hidden = false;
    await waitFor(() => emitted.length === 2);
    expect(emitted[1]!.headings).toContain("Step 2 of 2: Choose a date");
  });

  it("does not emit when the user only types", async () => {
    const emitted: PageSnapshot[] = [];
    observer = observePage(document, TEST_PAGE_URL, (s) => emitted.push(s), DEBOUNCE);
    (document.getElementById("full-name") as HTMLInputElement).value = "typing";
    await sleep(DEBOUNCE * 5);
    expect(emitted).toHaveLength(1);
  });

  it("does not emit duplicates for DOM changes that do not change the snapshot", async () => {
    const emitted: PageSnapshot[] = [];
    observer = observePage(document, TEST_PAGE_URL, (s) => emitted.push(s), DEBOUNCE);
    const spacer = document.createElement("div");
    document.body.append(spacer);
    spacer.remove();
    await sleep(DEBOUNCE * 5);
    expect(emitted).toHaveLength(1);
  });

  it("stops observing", async () => {
    const emitted: PageSnapshot[] = [];
    observer = observePage(document, TEST_PAGE_URL, (s) => emitted.push(s), DEBOUNCE);
    observer.stop();
    document.getElementById("summary")!.textContent = "changed";
    await sleep(DEBOUNCE * 5);
    expect(emitted).toHaveLength(1);
  });
});
