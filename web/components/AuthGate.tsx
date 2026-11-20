"use client";

import { useRouter } from "next/navigation";
import { createContext, useContext, type ReactNode } from "react";

import { AppShell } from "@/components/AppShell";
import { NoticeUpdate, Onboarding } from "@/components/Onboarding";
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

  async function signOut(next?: string) {
    try {
      await api.logout();
    } catch {
      // Already signed out or the backend is unreachable: navigate anyway.
    }
    if (next) {
      window.location.assign(next); // full navigation to the OIDC login route
      return;
    }
    router.push("/");
    router.refresh();
  }

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
        </a>{" "}
        {/* Registration is on the identity provider's sign-in page. */}
        <a href={LOGIN_PATH} className="button-secondary">
          {t("signUp")}
        </a>
      </div>
    );
  }
  if (state.status === "unverified") {
    // The identity provider has not confirmed the address yet. Signing out
    // and in again picks up the confirmation (SaaS-OS reads it per sign-in).
    return (
      <div className="center card stack" data-testid="email-unverified">
        <h1>{t("verifyTitle")}</h1>
        <p>{t("verifyBody")}</p>
        <button type="button" className="button" onClick={() => void signOut(LOGIN_PATH)}>
          {t("signInAgain")}
        </button>
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


  if (state.status === "onboarding") {
    return (
      <AppShell onSignOut={() => void signOut()}>
        <Onboarding tenantId={state.tenantId} status={state.onboarding} onDone={reload} />
      </AppShell>
    );
  }
  if (state.status === "notice") {
    return (
      <AppShell onSignOut={() => void signOut()}>
        <NoticeUpdate tenantId={state.tenantId} version={state.onboarding.privacy_notice_version} onDone={reload} />
      </AppShell>
    );
  }

  return (
    <SessionContext.Provider value={state}>
      <AppShell onSignOut={() => void signOut()}>{children}</AppShell>
    </SessionContext.Provider>
  );
}
