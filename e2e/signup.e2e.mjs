// End-to-end: the Phase 2 account lifecycle through the real stack
// (single-origin edge, SaaS-OS, local ZITADEL, Mailpit).
//
//   docker compose up -d        (fresh stack, OIDC_CLIENT_ID set)
//   cd e2e && npm ci && npx playwright install chromium && node signup.e2e.mjs
//
// Sign up with a new, random test address (reserved .test domain), confirm
// it with the code from Mailpit, onboard, edit the profile, change a
// consent, download the export, request deletion, sign out, check that the
// old session is dead, request a password reset, and finally scan the
// application logs for the personal values used. Development stack only;
// nothing leaves this machine.
import { execFileSync } from "node:child_process";
import { mkdirSync } from "node:fs";
import { resolve } from "node:path";
import { chromium } from "playwright";

const ORIGIN = "http://localhost:8080";
const MAILPIT = "http://localhost:8025";
const RESULTS = resolve(import.meta.dirname, "results");
mkdirSync(RESULTS, { recursive: true });

const run = Math.random().toString(36).slice(2, 10);
const EMAIL = `e2e-${run}@example.test`;
const FIRST = `Zarqa${run}`;
const LAST = `Canary${run}`;
const DISPLAY = `Display${run}`;
const PASSWORD = `E2e-${run}-Pw!9x`;
const PLANTED = `planted-${run}`;

const results = [];
function check(name, ok, detail = "") {
  results.push({ name, ok });
  console.log(`${ok ? "PASS" : "FAIL"}  ${name}${detail ? `  (${detail})` : ""}`);
}

async function mailFor(address, subjectPattern) {
  for (let i = 0; i < 20; i++) {
    const search = await (await fetch(`${MAILPIT}/api/v1/search?query=${encodeURIComponent(`to:${address}`)}`)).json();
    const hit = (search.messages ?? []).find((m) => subjectPattern.test(m.Subject));
    if (hit) return (await fetch(`${MAILPIT}/api/v1/message/${hit.ID}`)).json();
    await new Promise((r) => setTimeout(r, 500));
  }
  return null;
}

async function skipOptionalSteps(page) {
  for (let i = 0; i < 6 && !page.url().startsWith(ORIGIN); i++) {
    const skip = page.locator("button[name='skip'], #skip-button, button:has-text('Overslaan'), button:has-text('Skip')");
    const next = page.locator("#submit-button, button[type=submit]:has-text('Volgende'), button[type=submit]:has-text('Next')");
    if (await skip.first().isVisible().catch(() => false)) await skip.first().click();
    else if (await next.first().isVisible().catch(() => false)) await next.first().click(); // "user activated: next"
    await page.waitForTimeout(1000);
  }
}

async function readDownload(download) {
  const stream = await download.createReadStream();
  let text = "";
  for await (const chunk of stream) text += chunk;
  return text;
}

const browser = await chromium.launch();
const context = await browser.newContext({ locale: "nl-NL", acceptDownloads: true });
const page = await context.newPage();
const cspViolations = [];
page.on("console", (message) => {
  if (/Content Security Policy|Refused to (execute|load|apply)/i.test(message.text())) cspViolations.push(message.text());
});

try {
  // --- Sign up --------------------------------------------------------------------------
  await context.addCookies([{ name: "saas_os_session", value: PLANTED, url: ORIGIN }]);
  const first = await page.goto(`${ORIGIN}/dashboard`);
  const csp = first?.headers()["content-security-policy"] ?? "";
  check(
    "pages carry a nonce CSP without unsafe-inline or unsafe-eval",
    /script-src 'self' 'nonce-[A-Za-z0-9+/=]+' 'strict-dynamic'/.test(csp) && !/unsafe-(inline|eval)/.test(csp),
  );
  const second = await page.request.get(`${ORIGIN}/dashboard`);
  const nonceOf = (header) => /'nonce-([^']+)'/.exec(header ?? "")?.[1];
  check("the nonce is fresh per request", nonceOf(second.headers()["content-security-policy"]) !== nonceOf(csp));

  await page.getByRole("link", { name: "Account aanmaken" }).click();
  await page.waitForURL(/zitadel\.localhost:8081/);
  await page.locator("button[name=register]").click();
  await page.locator("#firstname").fill(FIRST);
  await page.locator("#lastname").fill(LAST);
  await page.locator("#email").fill(EMAIL);
  await page.locator("#register-password").fill(PASSWORD);
  await page.locator("#register-password-confirmation").fill(PASSWORD);
  await page.locator("#register-button").click();
  await page.locator("#code").waitFor();
  check("registration asks for the emailed confirmation code", true);

  const mail = await mailFor(EMAIL, /.*/);
  const code = /\(Code ([A-Z0-9]+)\)/.exec(mail?.Text ?? "")?.[1];
  check("the confirmation email arrives in Mailpit", Boolean(code));
  await page.locator("#code").fill(code ?? "");
  await page.locator("#init-button").click();
  await skipOptionalSteps(page);
  await page.waitForURL(`${ORIGIN}/dashboard`, { timeout: 20000 });
  check("after confirmation the user lands on the dashboard", true);

  const session = (await context.cookies(ORIGIN)).find((c) => c.name === "saas_os_session");
  check("sign-in replaces a planted session cookie (no fixation)", Boolean(session) && session.value !== PLANTED);
  check("session cookie is HttpOnly and SameSite=Lax", Boolean(session?.httpOnly) && session?.sameSite === "Lax");

  // --- Onboarding ------------------------------------------------------------------------
  await page.getByTestId("onboarding-form").waitFor();
  check("a new account is asked to onboard first", true);
  await page.locator("input[name=display_name]").fill(DISPLAY);
  await page.locator("select[name=consulate]").selectOption("nl-utrecht");
  await page.locator("input[name=age_confirmed]").check();
  await page.locator("input[name=privacy_notice]").check();
  await page.getByRole("button", { name: "Doorgaan" }).click();
  const tenantId = (await page.getByTestId("tenant-id").textContent({ timeout: 15000 }))?.trim() ?? "";
  check("onboarding completes and shows the workspace", /^[0-9a-f-]{36}$/.test(tenantId));

  // --- Profile and consent -------------------------------------------------------------
  await page.goto(`${ORIGIN}/dashboard/profile`);
  const name = page.locator("input[name=display_name]");
  await name.waitFor();
  check("profile shows the onboarding data", (await name.inputValue()) === DISPLAY);
  await name.fill(`${DISPLAY}x`);
  await page.getByRole("button", { name: "Opslaan" }).click();
  await page.getByText("Opgeslagen").waitFor();
  check("profile change is saved", true);

  await page.goto(`${ORIGIN}/dashboard/settings`);
  const emails = page.getByTestId("consent-product-emails");
  await emails.waitFor();
  const before = await emails.isChecked();
  await emails.click();
  await page.waitForTimeout(500);
  const consents = await page.evaluate(async (t) => (await fetch(`/v1/tenants/${t}/consents`)).json(), tenantId);
  const productEmails = consents.find((c) => c.purpose === "product_emails");
  check("consent change round-trips through the backend", productEmails?.granted === !before);

  // --- Export and deletion request ------------------------------------------------------
  await page.goto(`${ORIGIN}/dashboard/account`);
  const [download] = await Promise.all([page.waitForEvent("download"), page.getByTestId("export-account").click()]);
  const exported = JSON.parse(await readDownload(download));
  check(
    "data export contains the profile and consents",
    exported.profile?.display_name === `${DISPLAY}x` && exported.consents?.length === 2 && exported.workspace_id === tenantId,
  );
  await page.getByRole("button", { name: "Account verwijderen" }).click();
  await page.getByTestId("delete-confirm").click();
  await page.getByTestId("deletion-requested").waitFor();
  check("deletion request is recorded and shown", true);
  const again = await page.evaluate(
    async (t) => (await fetch(`/v1/tenants/${t}/account/deletion-request`, { method: "POST" })).status,
    tenantId,
  );
  check("a repeated deletion request is idempotent", again === 200);

  // --- Sign out -------------------------------------------------------------------------------
  const oldSession = (await context.cookies(ORIGIN)).find((c) => c.name === "saas_os_session")?.value;
  await page.goto(`${ORIGIN}/dashboard`);
  await page.locator(".shell-actions button").click();
  await page.waitForURL(`${ORIGIN}/`);
  check("sign-out ends the session", (await page.evaluate(async () => (await fetch("/auth/me")).status)) === 401);
  await context.addCookies([{ name: "saas_os_session", value: oldSession ?? "", url: ORIGIN }]);
  check("the old session cookie no longer works", (await page.evaluate(async () => (await fetch("/auth/me")).status)) === 401);

  // --- Identity-provider session after sign-out (finding P2-F1) ---------------------------
  // SaaS-OS's sign-out revokes the MarocAssist session only; the identity
  // provider's own session stays, so "sign in" on the same browser returns
  // without a password. Recorded here so a fix upstream is noticed.
  await page.goto(`${ORIGIN}/auth/login`);
  await page.waitForTimeout(3000);
  const silent = page.url().startsWith(ORIGIN);
  // Informational, not a pass/fail criterion: see the Phase 2 report.
  console.log(`INFO  P2-F1 sign-in after sign-out without password: ${silent ? "yes (gap open)" : "no (gap closed)"}`);

  // --- Password reset (fresh browser: no identity-provider session) -------------------------
  const fresh = await browser.newContext({ locale: "nl-NL" });
  const resetPage = await fresh.newPage();
  await resetPage.goto(`${ORIGIN}/auth/login`);
  await resetPage.waitForURL(/zitadel\.localhost:8081/);
  await resetPage.locator("#loginName").fill(EMAIL);
  await resetPage.locator("#submit-button").click();
  await resetPage.locator("#password").waitFor();
  await resetPage
    .locator("a[href*='password/reset'], a:has-text('Wachtwoord vergeten'), a:has-text('vergeten'), button[name='resetPassword']")
    .first()
    .click();
  const reset = await mailFor(EMAIL, /wachtwoord|password/i);
  check("password reset sends an email", Boolean(reset), reset?.Subject);
  await fresh.close();

  check("no CSP violations were reported by the browser", cspViolations.length === 0, cspViolations[0]?.slice(0, 80));
} catch (error) {
  check("unexpected error", false, error instanceof Error ? error.message.split("\n")[0] : String(error));
  await page.screenshot({ path: resolve(RESULTS, "signup-failure.png") }).catch(() => {});
} finally {
  await browser.close();
}

// --- No personal values in application logs --------------------------------------------------
const logs = execFileSync("docker", ["compose", "logs", "--no-color", "backend", "worker", "web", "edge", "migrate"], {
  cwd: resolve(import.meta.dirname, ".."),
  encoding: "utf8",
  maxBuffer: 64 * 1024 * 1024,
});
const leaked = [EMAIL, FIRST, LAST, DISPLAY, PASSWORD].filter((value) => logs.includes(value));
check("application logs contain none of the personal values used", leaked.length === 0, `${leaked.length} found`);

const failed = results.filter((r) => !r.ok).length;
console.log(`\n${results.length - failed} passed, ${failed} failed`);
process.exit(failed ? 1 : 0);
