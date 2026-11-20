"use client";

import { useCallback, useEffect, useState } from "react";

import { ApiError, api, type ApiClient, type OnboardingStatus } from "@/lib/api";

export type SessionState =
  | { status: "loading" }
  | { status: "anonymous" }
  | { status: "unverified" }
  | { status: "error"; code: string }
  | { status: "onboarding"; userId: string; tenantId: string; onboarding: OnboardingStatus }
  | { status: "notice"; userId: string; tenantId: string; onboarding: OnboardingStatus }
  | { status: "ready"; userId: string; tenantId: string };

/**
 * Who is signed in, their personal workspace and whether onboarding is
 * done. Asks the backend: `/auth/me`, then `POST /v1/me/workspace` (which
 * creates the workspace on first use and refuses an unverified email
 * address), then the onboarding status. The browser holds no token: the
 * HttpOnly session cookie is the credential, and every decision here is
 * enforced again by the backend.
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
        const onboarding = await client.onboardingStatus(workspace.tenant_id);
        if (cancelled) return;
        const base = { userId: me.user_id, tenantId: workspace.tenant_id };
        if (!onboarding.onboarded) setState({ status: "onboarding", ...base, onboarding });
        else if (!onboarding.privacy_notice_current) setState({ status: "notice", ...base, onboarding });
        else setState({ status: "ready", ...base });
      } catch (error) {
        if (cancelled) return;
        if (error instanceof ApiError && error.unauthenticated) setState({ status: "anonymous" });
        else if (error instanceof ApiError && error.code === "email_not_verified") setState({ status: "unverified" });
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
