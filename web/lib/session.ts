"use client";

import { useCallback, useEffect, useState } from "react";

import { ApiError, api, type ApiClient } from "@/lib/api";

export type SessionState =
  | { status: "loading" }
  | { status: "anonymous" }
  | { status: "error"; code: string }
  | { status: "ready"; userId: string; tenantId: string };

/**
 * Who is signed in, and their personal workspace. Asks the backend
 * (`/auth/me`, then `POST /v1/me/workspace`, which creates the workspace on
 * first use). The browser holds no token: the HttpOnly session cookie is
 * the credential.
 */
export function useSession(client: ApiClient = api): { state: SessionState; reload: () => void } {
  const [state, setState] = useState<SessionState>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const me = await client.me();
        const workspace = await client.ensureWorkspace();
        if (!cancelled) setState({ status: "ready", userId: me.user_id, tenantId: workspace.tenant_id });
      } catch (error) {
        if (cancelled) return;
        if (error instanceof ApiError && error.unauthenticated) setState({ status: "anonymous" });
        else setState({ status: "error", code: error instanceof ApiError ? error.code : "network_error" });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [client, attempt]);

  const reload = useCallback(() => {
    setState({ status: "loading" });
    setAttempt((n) => n + 1);
  }, []);
  return { state, reload };
}
