// End-to-end: curated knowledge (Phase 3 WP E) through the real single-origin
// edge: search, source click-through, the expired notice, an item page with
// "report outdated", and the consulate page showing Rotterdam in Schiedam as
// pending review. Fixture content only.
//
//   docker compose up -d --build        (stack running, OIDC_CLIENT_ID set)
//   cd backend && uv run python -m tests.publish_e2e_fixtures
//   cd e2e && npm ci && npx playwright install chromium && node knowledge.e2e.mjs
//
// Reads the local ZITADEL admin login from ../.env inside this process; the
// password is never printed. Outbound source links are answered by a stub,
// so no request leaves the machine. Development stack only.
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

async function signIn(page) {
  await page.goto(`${ORIGIN}/dashboard`);
  await page.getByRole("link", { name: "Inloggen", exact: true }).click();
  await page.waitForURL(/zitadel\.localhost:8081/);
  const loginName =
    process.env.E2E_LOGIN_NAME ?? `${env.ZITADEL_FIRSTINSTANCE_ADMIN_USERNAME}@marocassist-local.zitadel.localhost`;
  await page.locator("#loginName").fill(loginName);
  await page.locator("#submit-button").click();
  await page.locator("#password").fill(env.ZITADEL_FIRSTINSTANCE_ADMIN_PASSWORD);
  await page.locator("#submit-button").click();
  for (let i = 0; i < 5 && !page.url().startsWith(ORIGIN); i++) {
    const skip = page.locator("button[name='skip'], #skip-button, button:has-text('Skip'), button:has-text('Overslaan')");
    if (await skip.first().isVisible().catch(() => false)) await skip.first().click();
    await page.waitForTimeout(1000);
  }
  await page.waitForURL(`${ORIGIN}/dashboard`, { timeout: 15000 });
  const onboarding = page.getByTestId("onboarding-form");
  await Promise.race([onboarding.waitFor(), page.getByTestId("tenant-id").waitFor()]);
  if (await onboarding.isVisible()) {
    await page.locator("input[name=age_confirmed]").check();
    await page.locator("input[name=privacy_notice]").check();
    await page.getByRole("button", { name: "Doorgaan" }).click();
    await page.getByTestId("tenant-id").waitFor();
  }
}

async function search(page, query, consulate = "") {
  await page.goto(`${ORIGIN}/dashboard/knowledge`);
  await page.locator("select[name=consulate]").selectOption(consulate);
  await page.locator("input[name=q]").fill(query);
  await page.getByRole("button", { name: "Zoeken", exact: true }).click();
  await page.getByTestId("search-result").first().waitFor({ timeout: 10000 });
}

const browser = await chromium.launch();
const context = await browser.newContext({ locale: "nl-NL" });
await context.addCookies([{ name: "ma_locale", value: "nl", url: ORIGIN }]);
// Outbound official links: answered locally, never fetched from the internet.
await context.route(/^https:\/\/(www\.consulat\.ma|www\.rijksoverheid\.nl)\//, (route) =>
  route.fulfill({ status: 200, contentType: "text/html", body: "<title>stub</title>stub" }),
);
const page = await context.newPage();
try {
  await signIn(page);
  check("signed in and onboarded", true);

  await search(page, "paspoort verlengen");
  const first = page.getByTestId("search-result").first();
  const title = (await first.locator(".result-title").textContent())?.trim() ?? "";
  check("search finds the passport renewal item", /paspoort/i.test(title), title);
  check("the query is not in the page URL", !page.url().includes("paspoort"));

  const link = first.getByTestId("source-link").first();
  check(
    "source link opens in a new tab without opener",
    (await link.getAttribute("target")) === "_blank" && (await link.getAttribute("rel")) === "noopener noreferrer",
  );
  const [popup] = await Promise.all([context.waitForEvent("page"), link.click()]);
  await popup.waitForLoadState();
  const opener = await popup.evaluate(() => window.opener === null);
  check("source click-through reaches the official https page", popup.url().startsWith("https://www.consulat.ma/"), popup.url());
  check("the official page cannot reach back to MarocAssist", opener);
  await popup.close();

  await search(page, "consulaat bezoek", "nl-rotterdam");
  const visit = page.getByTestId("search-result").first();
  const notice = (await visit.getByTestId("status-notice").textContent().catch(() => "")) ?? "";
  check("expired content shows the not-recently-verified notice", notice.includes("Niet recent gecontroleerd"), notice);

  await visit.locator(".result-title a").click();
  await page.getByTestId("knowledge-item").waitFor();
  check("item page keeps the expired notice", await page.getByTestId("status-notice").isVisible());
  await page.locator("select[name=reason]").selectOption("outdated");
  await page.getByRole("button", { name: "Melden", exact: true }).click();
  await page.getByTestId("report-sent").waitFor();
  check("report outdated is accepted", true);

  await page.goto(`${ORIGIN}/dashboard/consulates`);
  const city = page.getByTestId("attribute-physical_city");
  await city.waitFor();
  const cityText = (await city.textContent()) ?? "";
  check("Rotterdam shows location Schiedam", cityText.includes("Schiedam"));
  check("Schiedam is labelled pending review", cityText.includes("Nog niet onafhankelijk bevestigd"));
  check("missing opening hours point to the official source", await page.getByTestId("missing-opening_hours").isVisible());

  await context.addCookies([{ name: "ma_locale", value: "ar", url: ORIGIN }]);
  await page.goto(`${ORIGIN}/dashboard/consulates`);
  await page.getByTestId("attribute-physical_city").waitFor();
  check("the consulate page renders right-to-left in Arabic", (await page.locator("html").getAttribute("dir")) === "rtl");
  await page.screenshot({ path: resolve(RESULTS, "consulates-ar.png"), fullPage: true });
} catch (error) {
  check("unexpected error", false, error instanceof Error ? error.message.split("\n")[0] : String(error));
  await page.screenshot({ path: resolve(RESULTS, "knowledge-failure.png") }).catch(() => {});
} finally {
  await browser.close();
}
const failed = results.filter((r) => !r.ok).length;
console.log(`\n${results.length - failed} passed, ${failed} failed`);
process.exit(failed ? 1 : 0);
