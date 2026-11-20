import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AppShell, NAV_ITEMS } from "@/components/AppShell";
import { ApiError, createApiClient } from "@/lib/api";
import { direction, LOCALES, messageKeys, resolveLocale, t } from "@/lib/i18n";
import { LocaleProvider } from "@/lib/locale-context";
import { useSession } from "@/lib/session";
import { buildCsp } from "@/proxy";
import { Onboarding } from "@/components/Onboarding";
import { CONSULATE_CODES, consulateKey } from "@/lib/i18n";
import { readFileSync } from "node:fs";
import { fireEvent } from "@testing-library/react";

vi.mock("next/navigation", () => ({
  usePathname: () => "/dashboard",
  useRouter: () => ({ refresh: vi.fn() }),
}));

afterEach(cleanup);

function jsonResponse(status: number, body: unknown): Response {
  return new Response(body === undefined ? null : JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("i18n", () => {
  it("prepares nl, fr, ar and en with the same keys", () => {
    const reference = messageKeys("nl");
    for (const locale of LOCALES) expect(messageKeys(locale)).toEqual(reference);
  });

  it("renders Arabic right-to-left and the rest left-to-right", () => {
    expect(direction("ar")).toBe("rtl");
    expect(direction("nl")).toBe("ltr");
    expect(direction("fr")).toBe("ltr");
    expect(direction("en")).toBe("ltr");
  });

  it("falls back to Dutch for unknown or missing locales", () => {
    expect(resolveLocale("de")).toBe("nl");
    expect(resolveLocale(undefined)).toBe("nl");
    expect(resolveLocale("ar")).toBe("ar");
  });

  it("states that the product is not affiliated with the government", () => {
    expect(t("en", "tagline")).toContain("Not affiliated");
    expect(t("nl", "tagline")).toContain("Niet verbonden");
  });
});

describe("api client", () => {
  it("uses relative same-origin requests and never adds an Authorization header", async () => {
    const fetchMock = vi.fn(async () =>
      jsonResponse(200, { product: "marocassist", version: "0.1.0", api_version: "v1" }),
    );
    const client = createApiClient(fetchMock);
    await client.meta();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("/v1/meta");
    expect(init.credentials).toBe("same-origin");
    expect(JSON.stringify(init.headers)).not.toMatch(/authorization/i);
  });

  it("turns an error response into an ApiError with the stable code only", async () => {
    const client = createApiClient(async () => jsonResponse(404, { detail: "workspace_not_found", extra: "x" }));
    await expect(client.ensureWorkspace()).rejects.toMatchObject({ status: 404, code: "workspace_not_found" });
  });

  it("encodes tenant ids into paths", async () => {
    const fetchMock = vi.fn(async () => jsonResponse(200, { locale: "nl" }));
    await createApiClient(fetchMock).readSettings("a/b");
    expect((fetchMock.mock.calls[0] as unknown as [string])[0]).toBe("/v1/tenants/a%2Fb/workspace/settings");
  });
});

function SessionProbe({ client }: { client: ReturnType<typeof createApiClient> }) {
  const { state } = useSession(client);
  return <p data-testid="state">{state.status === "ready" ? `ready:${state.tenantId}` : state.status}</p>;
}

describe("session", () => {
  it("is anonymous when the backend answers 401", async () => {
    const client = createApiClient(async () => jsonResponse(401, { detail: "not_authenticated" }));
    render(<SessionProbe client={client} />);
    await waitFor(() => expect(screen.getByTestId("state").textContent).toBe("anonymous"));
  });

  function backend(onboarded: boolean, current = true) {
    return createApiClient(async (path) => {
      if (path === "/auth/me") return jsonResponse(200, { user_id: "u1" });
      if (path === "/v1/me/workspace") return jsonResponse(200, { tenant_id: "t1", created: false });
      return jsonResponse(200, {
        onboarded,
        privacy_notice_current: current,
        privacy_notice_version: "2026-11-draft",
        consulates: ["nl-amsterdam"],
      });
    });
  }

  it("is ready with the personal workspace after sign-in and onboarding", async () => {
    render(<SessionProbe client={backend(true)} />);
    await waitFor(() => expect(screen.getByTestId("state").textContent).toBe("ready:t1"));
  });

  it("asks for onboarding first, and for a changed privacy notice", async () => {
    render(<SessionProbe client={backend(false)} />);
    await waitFor(() => expect(screen.getByTestId("state").textContent).toBe("onboarding"));
    cleanup();
    render(<SessionProbe client={backend(true, false)} />);
    await waitFor(() => expect(screen.getByTestId("state").textContent).toBe("notice"));
  });

  it("recognises an unverified email address", async () => {
    const client = createApiClient(async (path) =>
      path === "/auth/me" ? jsonResponse(200, { user_id: "u1" }) : jsonResponse(403, { detail: "email_not_verified" }),
    );
    render(<SessionProbe client={client} />);
    await waitFor(() => expect(screen.getByTestId("state").textContent).toBe("unverified"));
  });

  it("reports network errors without crashing", async () => {
    const client = createApiClient(async () => {
      throw new TypeError("network down");
    });
    render(<SessionProbe client={client} />);
    await waitFor(() => expect(screen.getByTestId("state").textContent).toBe("error"));
    expect(new ApiError(500, "x").unauthenticated).toBe(false);
  });
});

describe("app shell", () => {
  it("renders the navigation in the active locale and marks the current page", () => {
    render(
      <LocaleProvider locale="fr">
        <AppShell>
          <p>content</p>
        </AppShell>
      </LocaleProvider>,
    );
    const labels = screen.getAllByRole("link").map((a) => a.textContent);
    for (const item of NAV_ITEMS) expect(labels).toContain(t("fr", item.label));
    expect(screen.getByText(t("fr", "dashboard")).getAttribute("aria-current")).toBe("page");
    expect(screen.getByText("content")).toBeTruthy();
  });
});

describe("content security policy (S-10)", () => {
  it("allows scripts only with the per-request nonce, never inline or eval in production", () => {
    const csp = buildCsp("abc123", { dev: false, https: true });
    expect(csp).toContain("script-src 'self' 'nonce-abc123' 'strict-dynamic'");
    expect(csp).toContain("style-src 'self' 'nonce-abc123'");
    expect(csp).not.toContain("unsafe-inline");
    expect(csp).not.toContain("unsafe-eval");
    expect(csp).toContain("frame-ancestors 'none'");
    expect(csp).toContain("connect-src 'self'");
    expect(csp).toContain("upgrade-insecure-requests");
    expect(buildCsp("n", { dev: true, https: false })).toContain("'unsafe-eval'");
    expect(buildCsp("n", { dev: false, https: false })).not.toContain("upgrade-insecure-requests");
  });
});

describe("contract with the backend", () => {
  const backendProfile = readFileSync("../backend/src/marocassist/accounts/profile.py", "utf-8");

  it("shows the privacy notice version the backend accepts", () => {
    const backendVersion = /PRIVACY_NOTICE_VERSION = "([^"]+)"/.exec(backendProfile)?.[1];
    const page = readFileSync("app/privacy/page.tsx", "utf-8");
    expect(page).toContain(`const VERSION = "${backendVersion}"`);
  });

  it("knows exactly the consulates the backend accepts, with a label in every language", () => {
    const tuple = /CONSULATES: tuple\[str, \.\.\.\] = \(([^)]*)\)/.exec(backendProfile)?.[1] ?? "";
    const backendCodes = [...tuple.matchAll(/"([^"]+)"/g)].map((m) => m[1]);
    expect([...CONSULATE_CODES]).toEqual(backendCodes);
    for (const locale of LOCALES) {
      for (const code of CONSULATE_CODES) expect(t(locale, consulateKey(code)!)).toBeTruthy();
    }
  });
});

describe("onboarding form", () => {
  it("cannot be submitted before the age and privacy boxes are ticked, and asks nothing more", () => {
    render(
      <LocaleProvider locale="nl">
        <Onboarding
          tenantId="t1"
          status={{
            onboarded: false,
            privacy_notice_current: false,
            privacy_notice_version: "2026-11-draft",
            consulates: [...CONSULATE_CODES],
          }}
          onDone={() => undefined}
        />
      </LocaleProvider>,
    );
    const submit = screen.getByRole("button", { name: t("nl", "continue") }) as HTMLButtonElement;
    expect(submit.disabled).toBe(true);
    fireEvent.click(screen.getByLabelText(t("nl", "ageConfirm")));
    expect(submit.disabled).toBe(true);
    fireEvent.click(screen.getByLabelText(new RegExp(t("nl", "privacyAccept"))));
    expect(submit.disabled).toBe(false);
    const names = Array.from(document.querySelectorAll("input, select")).map((el) => el.getAttribute("name"));
    expect(names.sort()).toEqual(["age_confirmed", "consulate", "display_name", "privacy_notice", "product_emails"]);
  });
});
