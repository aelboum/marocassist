import { readFileSync } from "node:fs";
import { resolve } from "node:path";

export const EXTENSION_ROOT = resolve(import.meta.dirname, "..");
export const TEST_PAGE_URL = new URL("http://localhost:8090/index.html?step=1#top");

/** Load the local test page's markup into the jsdom document (scripts are not run). */
export function loadTestPage(document: Document): void {
  const html = readFileSync(resolve(EXTENSION_ROOT, "testsite/index.html"), "utf8");
  const parsed = new DOMParser().parseFromString(html, "text/html");
  document.title = parsed.title;
  document.body.replaceChildren(...Array.from(parsed.body.childNodes).map((n) => document.importNode(n, true)));
}

export const CANARIES = {
  name: "Canary Fullname Zx",
  email: "canary.person@example.invalid",
  passport: "QQ7654321",
  password: "Canary-Password-123!",
  csrf: "CANARY-CSRF-9f8e7d6c5b4a",
};

/** Fill the test page as a user would. */
export function fillCanaries(document: Document): void {
  (document.getElementById("full-name") as HTMLInputElement).value = CANARIES.name;
  (document.getElementById("email") as HTMLInputElement).value = CANARIES.email;
  (document.getElementById("passport") as HTMLInputElement).value = CANARIES.passport;
  (document.getElementById("account-password") as HTMLInputElement).value = CANARIES.password;
}
