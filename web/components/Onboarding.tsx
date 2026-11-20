"use client";

import Link from "next/link";
import { useState, type FormEvent } from "react";

import { ApiError, api, type OnboardingStatus } from "@/lib/api";
import { consulateKey } from "@/lib/i18n";
import { useLocale, useT } from "@/lib/locale-context";

/**
 * First-run form: optional display name, consulate, 18+ confirmation,
 * privacy notice and optional product emails. Nothing else is asked
 * (data minimisation). The backend validates every field again.
 */
export function Onboarding({
  tenantId,
  status,
  onDone,
}: {
  tenantId: string;
  status: OnboardingStatus;
  onDone: () => void;
}) {
  const t = useT();
  const locale = useLocale();
  const [displayName, setDisplayName] = useState("");
  const [consulate, setConsulate] = useState("");
  const [adult, setAdult] = useState(false);
  const [notice, setNotice] = useState(false);
  const [emails, setEmails] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!adult || !notice) return;
    setBusy(true);
    try {
      await api.completeOnboarding(tenantId, {
        display_name: displayName.trim() || null,
        consulate: consulate || null,
        locale,
        age_confirmed: true,
        privacy_notice_version: status.privacy_notice_version,
        product_emails: emails,
      });
      onDone();
    } catch (e) {
      setError(e instanceof ApiError ? e.code : "network_error");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="card stack" onSubmit={(e) => void submit(e)} data-testid="onboarding-form">
      <h1>{t("welcomeTitle")}</h1>
      <p>{t("welcomeBody")}</p>
      <label className="field">
        <span>{t("displayName")}</span>
        <input
          name="display_name"
          maxLength={80}
          autoComplete="nickname"
          value={displayName}
          onChange={(e) => setDisplayName(e.target.value)}
        />
      </label>
      <label className="field">
        <span>{t("consulate")}</span>
        <select name="consulate" value={consulate} onChange={(e) => setConsulate(e.target.value)}>
          <option value="">{t("consulateNone")}</option>
          {status.consulates.map((code) => {
            const key = consulateKey(code);
            return (
              <option key={code} value={code}>
                {key ? t(key) : code}
              </option>
            );
          })}
        </select>
      </label>
      <label className="check">
        <input type="checkbox" name="age_confirmed" checked={adult} onChange={(e) => setAdult(e.target.checked)} />
        <span>{t("ageConfirm")}</span>
      </label>
      <label className="check">
        <input type="checkbox" name="privacy_notice" checked={notice} onChange={(e) => setNotice(e.target.checked)} />
        <span>
          {t("privacyAccept")}{" "}
          <Link href="/privacy" target="_blank" rel="noopener">
            {t("privacyLink")}
          </Link>
        </span>
      </label>
      <label className="check">
        <input type="checkbox" name="product_emails" checked={emails} onChange={(e) => setEmails(e.target.checked)} />
        <span>{t("productEmails")}</span>
      </label>
      {error ? <p role="alert">{t("errorTitle")}</p> : null}
      <button type="submit" className="button" disabled={!adult || !notice || busy}>
        {t("continue")}
      </button>
    </form>
  );
}

/** Shown when the privacy notice changed after the user accepted it. */
export function NoticeUpdate({
  tenantId,
  version,
  onDone,
}: {
  tenantId: string;
  version: string;
  onDone: () => void;
}) {
  const t = useT();
  const [error, setError] = useState(false);

  async function accept() {
    try {
      await api.setConsent(tenantId, "privacy_notice", true, version);
      onDone();
    } catch {
      setError(true);
    }
  }

  return (
    <div className="card stack">
      <h1>{t("noticeUpdatedTitle")}</h1>
      <p>{t("noticeUpdatedBody")}</p>
      <Link href="/privacy" target="_blank" rel="noopener">
        {t("privacyLink")}
      </Link>
      {error ? <p role="alert">{t("errorTitle")}</p> : null}
      <button type="button" className="button" onClick={() => void accept()}>
        {t("accept")}
      </button>
    </div>
  );
}
