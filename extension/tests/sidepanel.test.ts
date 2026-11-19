import { beforeEach, describe, expect, it } from "vitest";

import { buildSnapshot } from "../src/content/extract";
import { renderSnapshot } from "../src/sidepanel/render";
import type { PageSnapshot } from "../src/shared/contracts";
import { loadTestPage, TEST_PAGE_URL } from "./helpers";

let root: HTMLElement;

beforeEach(() => {
  loadTestPage(document);
  root = document.createElement("div");
});

function texts(testId: string): string[] {
  return Array.from(root.querySelectorAll(`[data-testid='${testId}'] li`)).map((li) => li.textContent ?? "");
}

describe("side panel", () => {
  it("shows an empty state without a snapshot", () => {
    renderSnapshot(root, null);
    expect(root.textContent).toContain("Open the local test page");
  });

  it("renders the snapshot and updates when a new one arrives", () => {
    const first = buildSnapshot(document, TEST_PAGE_URL, 1000);
    renderSnapshot(root, first, 3000);
    expect(texts("fields")).toEqual(["Full name · text · required", "Email address · email · required", "Passport number · text · required"]);
    expect(root.querySelector("[data-testid='updated']")?.textContent).toBe("Updated 2s ago");
    expect(root.querySelector("[data-testid='alerts']")).toBeNull();

    document.getElementById("email")!.setAttribute("aria-invalid", "true");
    document.getElementById("email-error")!.textContent = "Please enter a valid email address.";
    document.getElementById("summary")!.textContent = "1 field(s) need attention.";
    renderSnapshot(root, buildSnapshot(document, TEST_PAGE_URL, 4000), 4000);
    expect(texts("alerts")).toEqual(["1 field(s) need attention."]);
    expect(texts("fields")[1]).toBe("Email address · email · required · error: Please enter a valid email address.");
  });

  it("shows the CAPTCHA notice only when a CAPTCHA is visible", () => {
    const snapshot = buildSnapshot(document, TEST_PAGE_URL);
    renderSnapshot(root, { ...snapshot, captchaPresent: true });
    expect(root.querySelector("[data-testid='captcha']")?.textContent).toContain("never interacts");
  });

  it("renders page text as text, never as markup", () => {
    const hostile: PageSnapshot = {
      ...buildSnapshot(document, TEST_PAGE_URL),
      title: "<img src=x onerror=alert(1)>",
      alerts: ["<script>alert(1)</script>"],
    };
    renderSnapshot(root, hostile);
    expect(root.querySelector("img")).toBeNull();
    expect(root.querySelector("script")).toBeNull();
    expect(root.textContent).toContain("<img src=x onerror=alert(1)>");
  });
});
