// End-to-end: the built MV3 extension in Chromium against the local test
// website (http://localhost:8090, the `copilot-testsite` Compose service).
//
//   (cd ../extension && npm run build) && node extension.e2e.mjs
//
// Phase A loads the extension exactly as built: no host access is granted,
// so no content script may run. Phase B loads a test copy whose manifest
// additionally grants the optional test-site permission up front (Playwright
// cannot click Chrome's permission prompt); the code is identical.
import { cpSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { chromium } from "playwright";

const DIST = resolve(import.meta.dirname, "../extension/dist");
const SITE = "http://localhost:8090/index.html";
const CANARY = { name: "Canary Fullname Zx", email: "canary.person@example.invalid", passport: "QQ76543", password: "Canary-Password-123!" };

const results = [];
function check(name, ok, detail = "") {
  results.push({ name, ok });
  console.log(`${ok ? "PASS" : "FAIL"}  ${name}${detail ? `  (${detail})` : ""}`);
}

async function launch(extensionDir) {
  const profile = mkdtempSync(join(tmpdir(), "ma-e2e-"));
  const context = await chromium.launchPersistentContext(profile, {
    channel: "chromium",
    headless: true,
    args: [`--disable-extensions-except=${extensionDir}`, `--load-extension=${extensionDir}`],
  });
  const worker = context.serviceWorkers()[0] ?? (await context.waitForEvent("serviceworker"));
  const extensionId = new URL(worker.url()).host;
  return { context, worker, extensionId, profile };
}

async function openPanel(context, extensionId) {
  const panel = await context.newPage();
  await panel.goto(`chrome-extension://${extensionId}/sidepanel.html`);
  await panel.getByTestId("independence-banner").waitFor();
  return panel;
}

// --- Phase A: as built, without host access -------------------------------------------
{
  const { context, extensionId, profile } = await launch(DIST);
  try {
    const panel = await openPanel(context, extensionId);
    check("side panel shows the independence banner", (await panel.getByTestId("independence-banner").textContent()).includes("not affiliated"));
    const site = await context.newPage();
    await site.goto(SITE);
    await site.waitForTimeout(1500);
    const text = await panel.locator("#content").textContent();
    check("without the optional host permission no content script runs", text.includes("Open the local test page"));
    check("the panel offers to request access instead", await panel.locator("#grant-access").isVisible());
  } finally {
    await context.close();
    rmSync(profile, { recursive: true, force: true });
  }
}

// --- Phase B: test-site permission granted ------------------------------------------------
const granted = mkdtempSync(join(tmpdir(), "ma-ext-"));
cpSync(DIST, granted, { recursive: true });
const manifest = JSON.parse(readFileSync(join(granted, "manifest.json"), "utf8"));
manifest.host_permissions = manifest.optional_host_permissions;
writeFileSync(join(granted, "manifest.json"), JSON.stringify(manifest));

{
  const { context, worker, extensionId, profile } = await launch(granted);
  const requests = [];
  context.on("request", (request) => requests.push(request.url()));
  try {
    const panel = await openPanel(context, extensionId);
    const site = await context.newPage();
    await site.goto(SITE);
    const fields = panel.locator("[data-testid='fields'] li");
    await fields.first().waitFor({ timeout: 5000 });
    check("test page recognised: fields listed in the side panel", (await fields.count()) === 3, `${await fields.count()} fields`);

    await site.fill("#full-name", CANARY.name);
    await site.fill("#email", CANARY.email);
    await site.fill("#passport", CANARY.passport);
    await site.fill("#account-password", CANARY.password);
    const started = Date.now();
    await site.click("#next");
    await panel.locator("[data-testid='alerts'] li").waitFor({ timeout: 5000 });
    const latency = Date.now() - started;
    check("side panel updates after a DOM change within 1 s", latency < 1000, `${latency} ms`);
    const panelText = await panel.locator("#content").textContent();
    check("validation error shown with the echoed number masked", panelText.includes("Passport number ••• is not valid."));

    const stored = await worker.evaluate(() => chrome.storage.session.get(null));
    const everything = panelText + JSON.stringify(stored);
    const leaked = Object.values(CANARY).filter((c) => everything.includes(c) || everything.includes(c.replace("QQ", "")));
    check("no typed value, password or CSRF token in the panel or extension storage", leaked.length === 0 && !everything.includes("CANARY-CSRF"), leaked.join(","));

    const values = await site.evaluate(() => ["full-name", "email", "passport", "account-password"].map((id) => document.getElementById(id).value));
    check("the extension did not change any field value", JSON.stringify(values) === JSON.stringify([CANARY.name, CANARY.email, CANARY.passport, CANARY.password]));

    await site.fill("#passport", "QQ1234567");
    await site.click("#next");
    await panel.locator("[data-testid='captcha']").waitFor({ timeout: 5000 });
    check("next step recognised and CAPTCHA reported, not touched", (await panel.locator("h2, li").allTextContents()).some((t) => t.includes("Step 2 of 2")));
    check("still on the test page: nothing submitted or navigated", site.url() === SITE);

    const foreign = requests.filter((url) => !url.startsWith("chrome-extension://") && !url.startsWith("http://localhost:8090/"));
    check("no network request other than the test page itself", foreign.length === 0, foreign.slice(0, 3).join(" "));
    await panel.screenshot({ path: resolve(import.meta.dirname, "results/sidepanel.png") });
  } catch (error) {
    check("unexpected error", false, error instanceof Error ? error.message.split("\n")[0] : String(error));
  } finally {
    await context.close();
    rmSync(profile, { recursive: true, force: true });
    rmSync(granted, { recursive: true, force: true });
  }
}

const failed = results.filter((r) => !r.ok).length;
console.log(`\n${results.length - failed} passed, ${failed} failed`);
process.exit(failed ? 1 : 0);
