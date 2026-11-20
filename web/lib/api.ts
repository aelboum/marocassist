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

export type ApiClient = ReturnType<typeof createApiClient>;
export const api = createApiClient();

/** Login is a full-page navigation to the backend's OIDC route. */
export const LOGIN_PATH = "/auth/login";
