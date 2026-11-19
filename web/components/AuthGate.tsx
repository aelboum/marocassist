"use client";

import { useRouter } from "next/navigation";
import { createContext, useContext, type ReactNode } from "react";

import { AppShell } from "@/components/AppShell";
import { api, LOGIN_PATH } from "@/lib/api";
import { useT } from "@/lib/locale-context";
import { useSession, type SessionState } from "@/lib/session";

type ReadySession = Extract<SessionState, { status: "ready" }>;
const SessionContext = createContext<ReadySession | null>(null);

export function useReadySession(): ReadySession {
  const session = useContext(SessionContext);
  if (!session) throw new Error("useReadySession outside AuthGate");
  return session;
}

/**
 * Renders the authenticated dashboard shell only for a signed-in user.
 * The check is the backend's (`/auth/me`); hiding UI here is convenience,
 * the backend enforces access on every request.
 */
export function AuthGate({ children }: { children: ReactNode }) {
  const t = useT();
  const { state, reload } = useSession();
  const router = useRouter();

  if (state.status === "loading") {
    return (
      <p role="status" className="center">
        {t("loading")}
      </p>
    );
  }
  if (state.status === "anonymous") {
    return (
      <div className="center card">
        <p>{t("notSignedIn")}</p>
        <a href={LOGIN_PATH} className="button">
          {t("signIn")}
        </a>
      </div>
    );
  }
  if (state.status === "error") {
    return (
      <div role="alert" className="center card">
        <p>{t("errorTitle")}</p>
        <button type="button" onClick={reload} className="button">
          {t("retry")}
        </button>
      </div>
    );
  }

  async function signOut() {
    try {
      await api.logout();
    } finally {
      router.push("/");
      router.refresh();
    }
  }

  return (
    <SessionContext.Provider value={state}>
      <AppShell onSignOut={signOut}>{children}</AppShell>
    </SessionContext.Provider>
  );
}
