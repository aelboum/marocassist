/**
 * The one HTTP client for the MarocAssist backend.
 *
 * - Relative URLs only: the browser sees one origin (SaaS-OS ADR-0024), so
 *   the session cookie is sent automatically and no CORS is involved.
 * - The session is an HttpOnly cookie set by SaaS-OS; this code never
 *   sees, stores or forwards a token.
 * - Every non-2xx response becomes an `ApiError` with the status and the
 *   backend's stable error code, never the raw body text.
 */

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
  ) {
    super(`API request failed: ${status} ${code}`);
    this.name = "ApiError";
  }

  get unauthenticated(): boolean {
    return this.status === 401;
  }
}

type FetchLike = (input: string, init?: RequestInit) => Promise<Response>;

async function errorCode(response: Response): Promise<string> {
  try {
    const body: unknown = await response.json();
    if (body && typeof body === "object") {
      const record = body as Record<string, unknown>;
      if (typeof record.error === "string") return record.error;
      if (typeof record.detail === "string") return record.detail;
    }
  } catch {
    // Non-JSON error body: fall through to the generic code.
  }
  return "http_error";
}

export function createApiClient(fetchImpl: FetchLike = (input, init) => fetch(input, init)) {
  async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
    if (!path.startsWith("/v1/") && !path.startsWith("/auth/")) {
      throw new Error("API paths must be relative /v1/ or /auth/ paths");
    }
    const response = await fetchImpl(path, {
      method,
      credentials: "same-origin",
      headers: body === undefined ? { Accept: "application/json" } : { Accept: "application/json", "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
      cache: "no-store",
    });
    if (!response.ok) {
      throw new ApiError(response.status, await errorCode(response));
    }
    if (response.status === 204) return undefined as T;
    return (await response.json()) as T;
  }

  const tenant = (tenantId: string, suffix: string) => `/v1/tenants/${encodeURIComponent(tenantId)}/${suffix}`;
  const knowledge = (tenantId: string, suffix: string, params?: Record<string, string | string[] | null | undefined>) => {
    const query = new URLSearchParams();
    for (const [key, value] of Object.entries(params ?? {})) {
      if (value === null || value === undefined || value === "") continue;
      for (const item of Array.isArray(value) ? value : [value]) query.append(key, item);
    }
    const qs = query.toString();
    return tenant(tenantId, `knowledge/${suffix}${qs ? `?${qs}` : ""}`);
  };

  return {
    me: () => request<{ user_id: string }>("GET", "/auth/me"),
    logout: () => request<void>("POST", "/auth/logout"),
    meta: () => request<{ product: string; version: string; api_version: string }>("GET", "/v1/meta"),
    ensureWorkspace: () => request<{ tenant_id: string; created: boolean }>("POST", "/v1/me/workspace"),
    readSettings: (tenantId: string) => request<{ locale: string }>("GET", tenant(tenantId, "workspace/settings")),
    updateSettings: (tenantId: string, locale: string) =>
      request<{ locale: string }>("PUT", tenant(tenantId, "workspace/settings"), { locale }),
    onboardingStatus: (tenantId: string) => request<OnboardingStatus>("GET", tenant(tenantId, "onboarding")),
    completeOnboarding: (tenantId: string, body: OnboardingInput) =>
      request<{ onboarded: boolean; created: boolean }>("POST", tenant(tenantId, "onboarding"), body),
    readProfile: (tenantId: string) => request<Profile>("GET", tenant(tenantId, "profile")),
    updateProfile: (tenantId: string, body: { display_name: string | null; consulate: string | null }) =>
      request<Profile>("PUT", tenant(tenantId, "profile"), body),
    readConsents: (tenantId: string) => request<Consent[]>("GET", tenant(tenantId, "consents")),
    setConsent: (tenantId: string, purpose: string, granted: boolean, version: string) =>
      request<Consent[]>("PUT", tenant(tenantId, `consents/${encodeURIComponent(purpose)}`), { granted, version }),
    exportAccount: (tenantId: string) => request<Record<string, unknown>>("GET", tenant(tenantId, "account/export")),
    readDeletionRequest: (tenantId: string) =>
      request<DeletionRequest>("GET", tenant(tenantId, "account/deletion-request")),
    requestDeletion: (tenantId: string) => request<DeletionRequest>("POST", tenant(tenantId, "account/deletion-request")),
    listDevices: (tenantId: string) => request<Device[]>("GET", tenant(tenantId, "copilot/devices")),
    revokeDevice: (tenantId: string, deviceId: string) =>
      request<void>("DELETE", tenant(tenantId, `copilot/devices/${encodeURIComponent(deviceId)}`)),
    // POST so the query never appears in a URL, browser history or access log.
    searchKnowledge: (tenantId: string, params: SearchParams) =>
      request<SearchResponse>("POST", knowledge(tenantId, "search"), {
        q: params.q,
        lang: params.lang,
        consulate: params.consulate ?? null,
        ...(params.kinds?.length ? { kind: params.kinds } : {}),
      }),
    readItem: (tenantId: string, itemId: string, lang?: string) =>
      request<KnowledgeItem>("GET", knowledge(tenantId, `items/${encodeURIComponent(itemId)}`, { lang })),
    readFact: (tenantId: string, factKey: string, consulate?: string | null) =>
      request<Fact>("GET", knowledge(tenantId, `facts/${encodeURIComponent(factKey)}`, { consulate })),
    listConsulates: (tenantId: string, lang?: string) =>
      request<Consulate[]>("GET", knowledge(tenantId, "consulates", { lang })),
    readConsulate: (tenantId: string, code: string, lang?: string) =>
      request<Consulate>("GET", knowledge(tenantId, `consulates/${encodeURIComponent(code)}`, { lang })),
    reportItem: (tenantId: string, itemId: string, reasonCode: string) =>
      request<{ report_id: string; created_at: string }>("POST", knowledge(tenantId, "reports"), {
        item_id: itemId,
        reason_code: reasonCode,
      }),
  };
}

export type OnboardingStatus = {
  onboarded: boolean;
  privacy_notice_current: boolean;
  privacy_notice_version: string;
  consulates: string[];
};
export type OnboardingInput = {
  display_name: string | null;
  consulate: string | null;
  locale: string;
  age_confirmed: boolean;
  privacy_notice_version: string;
  product_emails: boolean;
};
export type Profile = {
  display_name: string | null;
  consulate: string | null;
  residence_country: string;
  onboarded_at: string | null;
};
export type Consent = {
  purpose: string;
  version: string;
  granted: boolean;
  source: string;
  decided_at: string;
  current_version: string;
};
export type DeletionRequest = { requested: boolean; requested_at: string | null };
export type Device = { id: string; status: string; created_at: string; key_expires_at: string | null };

// Knowledge (Phase 3), mirroring packages/contracts/openapi.json.
export type ItemStatus = "current" | "expired" | "withdrawn";
export type SourceCard = {
  label: number;
  source_id: string;
  title: string;
  publisher: string;
  badge: "official" | "secondary" | "explanation";
  scope: string;
  verified_at: string | null;
  status: "current" | "expired" | "withdrawn" | "unverified";
  url: string;
  locator: string | null;
};
export type SearchParams = { q: string; lang: string; consulate?: string | null; kinds?: string[] };
export type SearchResult = {
  item_id: string;
  lang: string;
  ordinal: number;
  kind: string;
  status: ItemStatus;
  partial: boolean;
  title: string;
  heading: string | null;
  snippet: string;
  sources: SourceCard[];
};
export type SearchResponse = { langs: string[]; detected_lang: string | null; results: SearchResult[] };
export type KnowledgeItem = {
  item_id: string;
  kind: string;
  status: ItemStatus;
  version: number;
  review_due_at: string;
  superseded_by: string | null;
  country_scope: string[];
  consulate_scope: string[];
  lang: string | null;
  available_langs: string[];
  title: string | null;
  body: string | null;
  verified_at: string | null;
  sources: SourceCard[];
};
export type FactValue = {
  fact_id: string;
  scope: string;
  value: unknown;
  unit: string | null;
  status: "current" | "expired" | "under_review";
  valid_from: string;
  valid_until: string | null;
  verified_at: string;
  sources: SourceCard[];
};
export type Fact = {
  fact_key: string;
  consulate: string | null;
  scope: string | null;
  status: "current" | "expired" | "under_review" | "conflict" | null;
  needs_consulate: boolean;
  consulates: string[];
  values: FactValue[];
};
export type ConsulateAttribute = {
  attribute: string;
  lang: string | null;
  value: unknown;
  status: "verified" | "pending_review" | "expired";
  independently_confirmed: boolean;
  verified_at: string;
  source: SourceCard;
};
export type Consulate = {
  code: string;
  country: string;
  kind: string;
  active: boolean;
  display_name: string | null;
  attributes: ConsulateAttribute[];
  missing: string[];
};

export type ApiClient = ReturnType<typeof createApiClient>;
export const api = createApiClient();

/** Login is a full-page navigation to the backend's OIDC route. */
export const LOGIN_PATH = "/auth/login";
