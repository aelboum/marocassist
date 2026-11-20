// End-to-end: OIDC login through SaaS-OS and the local ZITADEL, then the
// authenticated dashboard, personal workspace, settings and tenant isolation
// through the real single-origin edge.
//
//   docker compose up -d        (stack running, OIDC_CLIENT_ID set)
//   cd e2e && npm ci && npx playwright install chromium && node login.e2e.mjs
//
// Reads the local ZITADEL admin login from ../.env inside this process; the
// password is never printed. Development stack only.
import { mkdirSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { chromium } from "playwright";

const ORIGIN = "http://localhost:8080";
const RESULTS = resolve(import.meta.dirname, "results");
mkdirSync(RESULTS, { recursive: true });
const env = Object.fromEntries(
  readFileSync(resolve(import.meta.dirname, "../.env"), "utf8")
    .split("\n")
    .filter((line) => line.includes("=") && !line.startsWith("#"))
    .map((line) => [line.slice(0, line.indexOf("=")), line.slice(line.indexOf("=") + 1).trim()]),
);

const results = [];
function check(name, ok, detail = "") {
  results.push({ name, ok });
  console.log(`${ok ? "PASS" : "FAIL"}  ${name}${detail ? `  (${detail})` : ""}`);
}

const browser = await chromium.launch();
const context = await browser.newContext({ locale: "nl-NL" });
const page = await context.newPage();
try {
  await page.goto(`${ORIGIN}/dashboard`);
  await page.getByRole("link", { name: "Inloggen", exact: true }).waitFor();
  check("anonymous dashboard shows the sign-in link", true);

  await page.getByRole("link", { name: "Inloggen", exact: true }).click();
  await page.waitForURL(/zitadel\.localhost:8081/);
  check("sign-in redirects to the identity provider", true, new URL(page.url()).host);

  // ZITADEL login names are <username>@<org>.<external domain>
  // (org "marocassist-local" in docker-compose.yml).
  const loginName =
    process.env.E2E_LOGIN_NAME ?? `${env.ZITADEL_FIRSTINSTANCE_ADMIN_USERNAME}@marocassist-local.zitadel.localhost`;
  await page.locator("#loginName").fill(loginName);
  await page.locator("#submit-button").click();
  await page.locator("#password").fill(env.ZITADEL_FIRSTINSTANCE_ADMIN_PASSWORD);
  await page.locator("#submit-button").click();
  for (let i = 0; i < 5 && !page.url().startsWith(ORIGIN); i++) {
    // Local ZITADEL may offer optional second-factor setup: skip it.
    const skip = page.locator("button[name='skip'], #skip-button, button:has-text('Skip'), button:has-text('Overslaan')");
    if (await skip.first().isVisible().catch(() => false)) await skip.first().click();
    await page.waitForTimeout(1000);
  }
  await page.waitForURL(`${ORIGIN}/dashboard`, { timeout: 15000 });
  check("callback returns to /dashboard on the single origin", true);

  const cookies = await context.cookies(ORIGIN);
  const session = cookies.find((c) => c.name === "saas_os_session");
  check("session cookie is HttpOnly and SameSite=Lax", Boolean(session?.httpOnly) && session?.sameSite === "Lax");
  const visibleToScript = await page.evaluate(() => document.cookie.includes("saas_os_session"));
  check("session cookie is not readable by page JavaScript", !visibleToScript);

  // Phase 2: a first sign-in onboards before the dashboard (the admin's
  // email is verified by the bootstrap). A re-run finds it done.
  const onboarding = page.getByTestId("onboarding-form");
  await Promise.race([onboarding.waitFor(), page.getByTestId("tenant-id").waitFor()]);
  if (await onboarding.isVisible()) {
    await page.locator("input[name=age_confirmed]").check();
    await page.locator("input[name=privacy_notice]").check();
    await page.getByRole("button", { name: "Doorgaan" }).click();
  }
  check("first sign-in goes through onboarding", true);
  const tenantId = (await page.getByTestId("tenant-id").textContent())?.trim();
  check("dashboard shows the personal workspace", /^[0-9a-f-]{36}$/.test(tenantId ?? ""), tenantId?.slice(0, 8));

  await page.goto(`${ORIGIN}/dashboard/settings`);
  const select = page.getByTestId("workspace-locale");
  await select.waitFor();
  await select.selectOption("fr");
  await page.waitForTimeout(500);
  const stored = await page.evaluate(async (t) => (await fetch(`/v1/tenants/${t}/workspace/settings`)).json(), tenantId);
  check("settings round-trip through the backend", stored.locale === "fr");

  const foreign = await page.evaluate(async () => (await fetch(`/v1/tenants/${crypto.randomUUID()}/workspace/settings`)).status);
  check("another tenant's workspace is 404", foreign === 404);

  const crossOrigin = await page.evaluate(async () => {
    try {
      const r = await fetch("http://localhost:8000/v1/me/workspace", { method: "POST", credentials: "include" });
      return r.status;
    } catch {
      return "blocked";
    }
  });
  check("no CORS: a cross-origin call to the backend is blocked", crossOrigin === "blocked", String(crossOrigin));

  await page.goto(`${ORIGIN}/dashboard`);
  await page.locator(".shell-actions button").click();
  await page.waitForURL(`${ORIGIN}/`);
  const after = await page.evaluate(async () => (await fetch("/auth/me")).status);
  check("sign-out ends the session", after === 401);

  await context.addCookies([{ name: "ma_locale", value: "ar", url: ORIGIN }]);
  await page.goto(`${ORIGIN}/`);
  const html = page.locator("html");
  check("Arabic renders right-to-left", (await html.getAttribute("dir")) === "rtl" && (await html.getAttribute("lang")) === "ar");
  await page.screenshot({ path: resolve(RESULTS, "home-ar.png") });
} catch (error) {
  check("unexpected error", false, error instanceof Error ? error.message.split("\n")[0] : String(error));
  await page.screenshot({ path: resolve(RESULTS, "login-failure.png") }).catch(() => {});
} finally {
  await browser.close();
}
const failed = results.filter((r) => !r.ok).length;
console.log(`\n${results.length - failed} passed, ${failed} failed`);
process.exit(failed ? 1 : 0);
