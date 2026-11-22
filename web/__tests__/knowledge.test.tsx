import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import ConsulatesPage from "@/app/dashboard/consulates/page";
import KnowledgeSearchPage from "@/app/dashboard/knowledge/page";
import { ItemBody, ReportForm, SourceCards, StatusNotice } from "@/components/Knowledge";
import { api, createApiClient, type Consulate, type SearchResponse, type SourceCard } from "@/lib/api";
import {
  attributeLines,
  bodyBlocks,
  contentDir,
  itemNotice,
  safeExternalUrl,
  scopeLabel,
  sourceNotice,
} from "@/lib/knowledge";
import { LocaleProvider } from "@/lib/locale-context";

vi.mock("next/navigation", () => ({
  usePathname: () => "/dashboard/knowledge",
  useRouter: () => ({ refresh: vi.fn(), push: vi.fn() }),
}));
vi.mock("@/components/AuthGate", () => ({
  useReadySession: () => ({ status: "ready", userId: "u-1", tenantId: "t-1" }),
}));

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

const SOURCE: SourceCard = {
  label: 1,
  source_id: "src-a",
  title: "Passeport biométrique",
  publisher: "MAECAMRE",
  badge: "official",
  scope: "consulate:nl-rotterdam",
  verified_at: "2026-11-01",
  status: "current",
  url: "https://www.consulat.ma/fr/passeport",
  locator: "Tarifs",
};

describe("knowledge presentation rules", () => {
  it("reads only headings and paragraphs from an item body", () => {
    expect(bodyBlocks("## Voorbereiding\n\nEen\ntwee.\n\n<script>x</script>\n## Daarna")).toEqual([
      { kind: "heading", text: "Voorbereiding" },
      { kind: "paragraph", text: "Een twee." },
      { kind: "paragraph", text: "<script>x</script>" },
      { kind: "heading", text: "Daarna" },
    ]);
  });

  it("links only to https URLs without credentials", () => {
    expect(safeExternalUrl("https://www.consulat.ma/fr")).toBe("https://www.consulat.ma/fr");
    expect(safeExternalUrl("http://www.consulat.ma/fr")).toBeNull();
    expect(safeExternalUrl("javascript:alert(1)")).toBeNull();
    expect(safeExternalUrl("https://user:pw@example.test/")).toBeNull();
    expect(safeExternalUrl("/relative")).toBeNull();
  });

  it("never presents expired or withdrawn content without a notice", () => {
    expect(itemNotice("current")).toBeNull();
    expect(itemNotice("expired")).toBe("kn.notice.expired");
    expect(itemNotice("withdrawn")).toBe("kn.notice.withdrawn");
    expect(sourceNotice("unverified")).toBe("kn.notice.unverified");
  });

  it("labels scopes and keeps the content direction", () => {
    expect(scopeLabel("consulate:nl-rotterdam")).toEqual({ key: "kn.scope.consulate", code: "nl-rotterdam" });
    expect(scopeLabel("country:NL")).toEqual({ key: "kn.scope.country", code: "NL" });
    expect(scopeLabel("global").key).toBe("kn.scope.global");
    expect(contentDir("ar")).toBe("rtl");
    expect(contentDir("fr")).toBe("ltr");
  });

  it("formats attribute values without ever showing raw JSON", () => {
    const base = {
      lang: null,
      status: "pending_review",
      independently_confirmed: false,
      verified_at: "2026-11-01",
      source: SOURCE,
    } as const;
    expect(attributeLines({ ...base, attribute: "physical_city", value: "Schiedam" })).toEqual(["Schiedam"]);
    expect(
      attributeLines({
        ...base,
        attribute: "address",
        value: { street: "De Brauwweg 38-44", postcode: "3125 AE", city: "Schiedam" },
      }),
    ).toEqual(["De Brauwweg 38-44", "3125 AE Schiedam"]);
    expect(attributeLines({ ...base, attribute: "contact", value: [1, 2] })).toEqual([]);
  });
});

describe("knowledge api client", () => {
  it("sends the search query in a POST body, never in the URL", async () => {
    const fetchMock = vi.fn(async () => jsonResponse(200, { langs: ["nl"], detected_lang: null, results: [] }));
    const client = createApiClient(fetchMock);
    await client.searchKnowledge("t 1", { q: "paspoort & co", lang: "nl", consulate: null, kinds: ["faq", "procedure"] });
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("/v1/tenants/t%201/knowledge/search");
    expect(init.method).toBe("POST");
    expect(JSON.parse(String(init.body))).toEqual({
      q: "paspoort & co",
      lang: "nl",
      consulate: null,
      kind: ["faq", "procedure"],
    });
  });

  it("builds read URLs with ids and codes only and drops empty parameters", async () => {
    const fetchMock = vi.fn(async () => jsonResponse(200, {}));
    const client = createApiClient(fetchMock);
    await client.readFact("t-1", "fee.passport_renewal.adult", null);
    await client.readItem("t-1", "fixture.passport-renewal", "fr");
    const urls = fetchMock.mock.calls.map((call) => (call as unknown as [string])[0]);
    expect(urls).toEqual([
      "/v1/tenants/t-1/knowledge/facts/fee.passport_renewal.adult",
      "/v1/tenants/t-1/knowledge/items/fixture.passport-renewal?lang=fr",
    ]);
  });

  it("sends a report with the item id and reason code only", async () => {
    const fetchMock = vi.fn(async () => jsonResponse(201, { report_id: "r", created_at: "2026-11-21T00:00:00Z" }));
    await createApiClient(fetchMock).reportItem("t-1", "fixture.passport-renewal", "outdated");
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("/v1/tenants/t-1/knowledge/reports");
    expect(JSON.parse(String(init.body))).toEqual({ item_id: "fixture.passport-renewal", reason_code: "outdated" });
  });
});

describe("knowledge components", () => {
  it("renders source cards with badge, scope, date and a safe outbound link", () => {
    render(
      <LocaleProvider locale="nl">
        <SourceCards
          sources={[SOURCE, { ...SOURCE, source_id: "src-b", label: 2, url: "javascript:alert(1)", status: "expired" }]}
        />
      </LocaleProvider>,
    );
    const cards = screen.getAllByTestId("source-card");
    expect(cards).toHaveLength(2);
    expect(cards[0]?.textContent).toContain("Officieel");
    expect(cards[0]?.textContent).toContain("Consulaat-generaal Rotterdam");
    const links = screen.getAllByTestId("source-link");
    expect(links).toHaveLength(1);
    expect(links[0]?.getAttribute("href")).toBe("https://www.consulat.ma/fr/passeport");
    expect(links[0]?.getAttribute("target")).toBe("_blank");
    expect(links[0]?.getAttribute("rel")).toBe("noopener noreferrer");
    expect(cards[1]?.textContent).toContain("Niet recent gecontroleerd");
  });

  it("shows the expired notice and nothing for current content", () => {
    const { rerender } = render(
      <LocaleProvider locale="en">
        <StatusNotice status="current" />
      </LocaleProvider>,
    );
    expect(screen.queryByTestId("status-notice")).toBeNull();
    rerender(
      <LocaleProvider locale="en">
        <StatusNotice status="expired" />
      </LocaleProvider>,
    );
    expect(screen.getByTestId("status-notice").textContent).toContain("Not recently verified");
  });

  it("renders body text as text in its own language and direction", () => {
    const { container } = render(<ItemBody body={"## عنوان\n\n<img src=x onerror=alert(1)>"} lang="ar" />);
    const root = container.firstElementChild as HTMLElement;
    expect(root.getAttribute("dir")).toBe("rtl");
    expect(root.getAttribute("lang")).toBe("ar");
    expect(container.querySelector("img")).toBeNull();
    expect(root.textContent).toContain("<img src=x onerror=alert(1)>");
  });

  it("submits a report and thanks the user", async () => {
    const spy = vi.spyOn(api, "reportItem").mockResolvedValue({ report_id: "r", created_at: "x" });
    render(
      <LocaleProvider locale="nl">
        <ReportForm tenantId="t-1" itemId="fixture.passport-renewal" />
      </LocaleProvider>,
    );
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "broken_link" } });
    fireEvent.click(screen.getByRole("button", { name: "Melden" }));
    await waitFor(() => expect(screen.getByTestId("report-sent")).toBeTruthy());
    expect(spy).toHaveBeenCalledWith("t-1", "fixture.passport-renewal", "broken_link");
  });
});

describe("knowledge pages", () => {
  it("searches with the profile consulate and shows results with their notices", async () => {
    vi.spyOn(api, "readProfile").mockResolvedValue({
      display_name: null,
      consulate: "nl-rotterdam",
      residence_country: "NL",
      onboarded_at: "2026-11-01T00:00:00Z",
    });
    const response: SearchResponse = {
      langs: ["nl"],
      detected_lang: "nl",
      results: [
        {
          item_id: "fixture.passport-renewal",
          lang: "nl",
          ordinal: 0,
          kind: "procedure",
          status: "expired",
          partial: true,
          title: "Paspoort verlengen",
          heading: "Voorbereiding",
          snippet: "U maakt eerst een afspraak",
          sources: [SOURCE],
        },
      ],
    };
    const search = vi.spyOn(api, "searchKnowledge").mockResolvedValue(response);
    render(
      <LocaleProvider locale="nl">
        <KnowledgeSearchPage />
      </LocaleProvider>,
    );
    await waitFor(() => expect((screen.getByRole("combobox") as HTMLSelectElement).value).toBe("nl-rotterdam"));
    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "paspoort verlengen" } });
    fireEvent.click(screen.getByRole("button", { name: "Zoeken" }));
    const result = await screen.findByTestId("search-result");
    expect(search).toHaveBeenCalledWith("t-1", { q: "paspoort verlengen", lang: "nl", consulate: "nl-rotterdam" });
    expect(result.textContent).toContain("Paspoort verlengen");
    expect(result.textContent).toContain("Niet recent gecontroleerd");
    expect(result.textContent).toContain("Niet alle zoekwoorden gevonden");
    expect(screen.getByRole("link", { name: "Paspoort verlengen" }).getAttribute("href")).toBe(
      "/dashboard/knowledge/fixture.passport-renewal?lang=nl",
    );
  });

  it("shows Rotterdam in Schiedam as not yet independently confirmed", async () => {
    const consulate: Consulate = {
      code: "nl-rotterdam",
      country: "NL",
      kind: "consulate_general",
      active: true,
      display_name: "Consulaat-generaal Rotterdam",
      attributes: [
        {
          attribute: "physical_city",
          lang: null,
          value: "Schiedam",
          status: "pending_review",
          independently_confirmed: false,
          verified_at: "2026-11-01",
          source: { ...SOURCE, publisher: "Rijksoverheid", url: "https://www.rijksoverheid.nl/x" },
        },
      ],
      missing: ["opening_hours"],
    };
    vi.spyOn(api, "listConsulates").mockResolvedValue([consulate]);
    render(
      <LocaleProvider locale="nl">
        <ConsulatesPage />
      </LocaleProvider>,
    );
    const city = await screen.findByTestId("attribute-physical_city");
    expect(city.textContent).toContain("Schiedam");
    expect(screen.getByTestId("attribute-pending").textContent).toContain("Nog niet onafhankelijk bevestigd");
    expect(screen.getByTestId("missing-opening_hours").textContent).toContain("Zie de officiële bron");
  });
});
