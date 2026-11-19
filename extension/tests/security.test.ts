import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, resolve } from "node:path";

import { beforeEach, describe, expect, it } from "vitest";

import { acceptSnapshot } from "../src/background/validate";
import { buildSnapshot } from "../src/content/extract";
import { HOST_PERMISSION_PATTERNS, isAllowedUrl } from "../src/shared/allowlist";
import { isPageSnapshot } from "../src/shared/contracts";
import { EXTENSION_ROOT, loadTestPage, TEST_PAGE_URL } from "./helpers";

const manifest = JSON.parse(readFileSync(resolve(EXTENSION_ROOT, "manifest.json"), "utf8")) as Record<string, unknown>;

function sourceFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    return statSync(path).isDirectory() ? sourceFiles(path) : path.endsWith(".ts") ? [path] : [];
  });
}

/** Source code without comments (comments may name what the code must not do). */
function code(file: string): string {
  return readFileSync(file, "utf8")
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/^\s*\/\/.*$/gm, "")
    .replace(/\s\/\/ .*$/gm, "");
}

describe("manifest permissions", () => {
  it("requests only sidePanel, storage and scripting", () => {
    expect(manifest.permissions).toEqual(["sidePanel", "storage", "scripting"]);
  });

  it("has no install-time host access and no static content scripts", () => {
    expect(manifest.host_permissions).toBeUndefined();
    expect(manifest.content_scripts).toBeUndefined();
    expect(manifest.externally_connectable).toBeUndefined();
    expect(manifest.web_accessible_resources).toBeUndefined();
  });

  it("asks for optional host access to the allow-listed test site only", () => {
    expect(manifest.optional_host_permissions).toEqual([...HOST_PERMISSION_PATTERNS]);
    const serialized = JSON.stringify(manifest);
    expect(serialized).not.toContain("<all_urls>");
    expect(serialized).not.toContain("*://*/");
    expect(serialized).not.toContain("consulat.ma");
  });

  it("never asks for cookies, webRequest, debugger, tabs or history", () => {
    const forbidden = ["cookies", "webRequest", "webRequestBlocking", "declarativeNetRequest", "debugger", "tabs", "history", "clipboardRead", "nativeMessaging"];
    for (const permission of forbidden) expect(manifest.permissions).not.toContain(permission);
  });

  it("allows no remote or dynamic code in extension pages", () => {
    const csp = (manifest.content_security_policy as Record<string, string>).extension_pages;
    expect(csp).toContain("script-src 'self'");
    expect(csp).not.toMatch(/unsafe-eval|unsafe-inline|https?:/);
  });

  it("states that it is not affiliated with the government", () => {
    expect(String(manifest.description)).toContain("Not affiliated with the Moroccan government");
  });
});

describe("allowlist", () => {
  it("accepts the local test site only", () => {
    expect(isAllowedUrl("http://localhost:8090/index.html")).toBe(true);
    expect(isAllowedUrl("https://localhost:8090/")).toBe(false);
    expect(isAllowedUrl("http://localhost:8091/")).toBe(false);
    expect(isAllowedUrl("https://rdv.consulat.ma/")).toBe(false);
    expect(isAllowedUrl("http://localhost:8090.evil.example/")).toBe(false);
    expect(isAllowedUrl("not a url")).toBe(false);
    expect(isAllowedUrl(undefined)).toBe(false);
  });
});

describe("service worker message validation", () => {
  const EXTENSION_ID = "abcdefghijklmnopabcdefghijklmnop";
  const sender = { id: EXTENSION_ID, url: "http://localhost:8090/index.html", tab: { id: 7, url: "http://localhost:8090/index.html" } };
  let message: { type: string; snapshot: Record<string, unknown> };

  beforeEach(() => {
    loadTestPage(document);
    message = { type: "snapshot", snapshot: { ...buildSnapshot(document, TEST_PAGE_URL) } };
  });

  it("accepts a valid snapshot from its own content script on an allow-listed tab", () => {
    expect(acceptSnapshot(message, sender, EXTENSION_ID)).not.toBeNull();
  });

  it("rejects other senders and other tabs", () => {
    expect(acceptSnapshot(message, { ...sender, id: "other-extension" }, EXTENSION_ID)).toBeNull();
    expect(acceptSnapshot(message, { ...sender, tab: { id: 7, url: "https://example.org/" } }, EXTENSION_ID)).toBeNull();
    expect(acceptSnapshot(message, { ...sender, tab: undefined }, EXTENSION_ID)).toBeNull();
  });

  it("rejects snapshots with extra fields, values, query strings or the wrong origin", () => {
    expect(acceptSnapshot({ ...message, snapshot: { ...message.snapshot, cookies: "x" } }, sender, EXTENSION_ID)).toBeNull();
    const withValue = { ...message.snapshot, fields: [{ ref: "f0", label: "x", kind: "text", required: false, error: null, value: "secret" }] };
    expect(isPageSnapshot(withValue)).toBe(false);
    expect(acceptSnapshot({ ...message, snapshot: { ...message.snapshot, location: "http://localhost:8090/?q=1" } }, sender, EXTENSION_ID)).toBeNull();
    expect(acceptSnapshot({ ...message, snapshot: { ...message.snapshot, location: "http://localhost:9999/" } }, sender, EXTENSION_ID)).toBeNull();
    expect(acceptSnapshot({ ...message, snapshot: { ...message.snapshot, title: "x".repeat(10_000) } }, sender, EXTENSION_ID)).toBeNull();
    expect(acceptSnapshot({ type: "other" }, sender, EXTENSION_ID)).toBeNull();
  });
});

describe("source code never automates the page", () => {
  const files = sourceFiles(resolve(EXTENSION_ROOT, "src"));
  const forbidden: Array<[RegExp, string]> = [
    [/\.value\s*=(?!=)/, "sets a field value"],
    [/\.checked\s*=(?!=)/, "checks a box"],
    [/\.click\s*\(/, "clicks"],
    [/\.submit\s*\(|requestSubmit/, "submits a form"],
    [/dispatchEvent|new (Mouse|Keyboard|Input)Event/, "synthesises events"],
    [/document\.cookie/, "reads cookies"],
    [/\bfetch\s*\(|XMLHttpRequest|WebSocket|sendBeacon/, "makes network requests"],
    [/innerHTML|outerHTML|insertAdjacentHTML/, "injects markup"],
    [/location\.(assign|replace|href\s*=)/, "navigates"],
    [/\beval\s*\(|new Function/, "runs dynamic code"],
    [/localStorage|indexedDB/, "persists page data"],
  ];

  it.each(forbidden)("no source file matches %s (%s)", (pattern) => {
    const offenders = files.filter((file) => pattern.test(code(file)));
    expect(offenders).toEqual([]);
  });

  it("the content script never reads field values", () => {
    const content = sourceFiles(resolve(EXTENSION_ROOT, "src/content"));
    const offenders = content.filter((file) => /\.(value|checked|selectedIndex|files)\b/.test(code(file)));
    expect(offenders).toEqual([]);
  });
});
