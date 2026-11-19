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

  return {
    me: () => request<{ user_id: string }>("GET", "/auth/me"),
    logout: () => request<void>("POST", "/auth/logout"),
    meta: () => request<{ product: string; version: string; api_version: string }>("GET", "/v1/meta"),
    ensureWorkspace: () => request<{ tenant_id: string; created: boolean }>("POST", "/v1/me/workspace"),
    readSettings: (tenantId: string) =>
      request<{ locale: string }>("GET", `/v1/tenants/${encodeURIComponent(tenantId)}/workspace/settings`),
    updateSettings: (tenantId: string, locale: string) =>
      request<{ locale: string }>("PUT", `/v1/tenants/${encodeURIComponent(tenantId)}/workspace/settings`, { locale }),
    listDevices: (tenantId: string) =>
      request<Array<{ id: string; status: string; created_at: string; key_expires_at: string | null }>>(
        "GET",
        `/v1/tenants/${encodeURIComponent(tenantId)}/copilot/devices`,
      ),
  };
}

export type ApiClient = ReturnType<typeof createApiClient>;
export const api = createApiClient();

/** Login is a full-page navigation to the backend's OIDC route. */
export const LOGIN_PATH = "/auth/login";
