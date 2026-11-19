import { beforeEach, describe, expect, it } from "vitest";

import { buildSnapshot, cleanText, maskedPath } from "../src/content/extract";
import { isPageSnapshot } from "../src/shared/contracts";
import { CANARIES, fillCanaries, loadTestPage, TEST_PAGE_URL } from "./helpers";

beforeEach(() => loadTestPage(document));

describe("page snapshot", () => {
  it("recognises the test page structure", () => {
    const snapshot = buildSnapshot(document, TEST_PAGE_URL);
    expect(isPageSnapshot(snapshot)).toBe(true);
    expect(snapshot.title).toBe("Demo appointment form (local test page)");
    expect(snapshot.headings).toEqual(["Demo appointment form", "Step 1 of 2: Your details"]);
    expect(snapshot.fields.map((f) => [f.label, f.kind, f.required])).toEqual([
      ["Full name", "text", true],
      ["Email address", "email", true],
      ["Passport number", "text", true],
    ]);
    expect(snapshot.buttons).toEqual(["Next"]);
  });

  it("keeps only origin and path of the URL", () => {
    expect(buildSnapshot(document, TEST_PAGE_URL).location).toBe("http://localhost:8090/index.html");
  });

  it("never contains typed values, passwords, hidden tokens or cookies", () => {
    fillCanaries(document);
    document.cookie = "session=CANARY-COOKIE-abc";
    const serialized = JSON.stringify(buildSnapshot(document, TEST_PAGE_URL));
    for (const canary of [...Object.values(CANARIES), "CANARY-COOKIE-abc"]) {
      expect(serialized).not.toContain(canary);
    }
    expect(serialized).not.toMatch(/password/i);
  });

  it("masks numbers that a page echoes back in an error message", () => {
    const passport = document.getElementById("passport") as HTMLInputElement;
    passport.setAttribute("aria-invalid", "true");
    document.getElementById("passport-error")!.textContent = `Passport number ${CANARIES.passport} is not valid.`;
    const snapshot = buildSnapshot(document, TEST_PAGE_URL);
    const field = snapshot.fields.find((f) => f.label === "Passport number");
    expect(field?.error).toBe("Passport number ••• is not valid.");
    expect(JSON.stringify(snapshot)).not.toContain("7654321");
  });

  it.each([
    ["Passport number QQ76543 is not valid.", "Passport number ••• is not valid."],
    ["CNIE AB123456 unknown", "CNIE ••• unknown"],
    ["Call +31 6 1234 5678 now", "Call ••• now"],
    ["Send to canary.person@example.invalid please", "Send to ••• please"],
    ["Step 2 of 2: Your details", "Step 2 of 2: Your details"],
  ])("masks identifiers in page text: %s", (input, expected) => {
    expect(cleanText(input)).toBe(expected);
  });

  it("reports a visible CAPTCHA without touching it, and ignores a hidden one", () => {
    expect(buildSnapshot(document, TEST_PAGE_URL).captchaPresent).toBe(false);
    document.getElementById("step-1")!.hidden = true;
    document.getElementById("step-2")!.hidden = false;
    const snapshot = buildSnapshot(document, TEST_PAGE_URL);
    expect(snapshot.captchaPresent).toBe(true);
    expect(snapshot.fields.map((f) => f.kind)).toEqual(["select", "date"]);
  });

  it("masks identifiers in the URL path", () => {
    expect(maskedPath("/dossier/AB1234567/edit")).toBe("/dossier/•••/edit");
    expect(maskedPath("/index.html")).toBe("/index.html");
    const snapshot = buildSnapshot(document, new URL("http://localhost:8090/case/QQ7654321"));
    expect(snapshot.location).toBe("http://localhost:8090/case/•••");
  });

  it("never reads text typed into editable regions or prefilled controls in labels and alerts", () => {
    const label = document.querySelector("label[for='full-name']")!;
    const prefilled = document.createElement("textarea");
    prefilled.textContent = "Canary Prefilled Person";
    label.append(prefilled);
    const editable = document.createElement("div");
    editable.setAttribute("contenteditable", "true");
    editable.textContent = "Canary Typed Note";
    document.getElementById("summary")!.append("Notice ", editable);
    const serialized = JSON.stringify(buildSnapshot(document, TEST_PAGE_URL));
    expect(serialized).not.toContain("Canary Prefilled Person");
    expect(serialized).not.toContain("Canary Typed Note");
    expect(serialized).toContain("Full name");
  });

  it("caps text length", () => {
    expect(cleanText("a".repeat(500)).length).toBeLessThanOrEqual(160);
  });
});
