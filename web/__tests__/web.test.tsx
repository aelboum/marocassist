import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AppShell, NAV_ITEMS } from "@/components/AppShell";
import { ApiError, createApiClient } from "@/lib/api";
import { direction, LOCALES, messageKeys, resolveLocale, t } from "@/lib/i18n";
import { LocaleProvider } from "@/lib/locale-context";
import { useSession } from "@/lib/session";

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

  it("is ready with the personal workspace after sign-in", async () => {
    const client = createApiClient(async (path) =>
      path === "/auth/me" ? jsonResponse(200, { user_id: "u1" }) : jsonResponse(200, { tenant_id: "t1", created: false }),
    );
    render(<SessionProbe client={client} />);
    await waitFor(() => expect(screen.getByTestId("state").textContent).toBe("ready:t1"));
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
