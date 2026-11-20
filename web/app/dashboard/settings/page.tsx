"use client";

import { useEffect, useState } from "react";

import { useReadySession } from "@/components/AuthGate";
import { ApiError, api, type Consent } from "@/lib/api";
import { isLocale, LOCALES } from "@/lib/i18n";
import { useT } from "@/lib/locale-context";

export default function SettingsPage() {
  const t = useT();
  const { tenantId } = useReadySession();
  const [saved, setSaved] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [consents, setConsents] = useState<Consent[] | null>(null);

  useEffect(() => {
    api
      .readSettings(tenantId)
      .then((s) => setSaved(s.locale))
      .catch((e: unknown) => setError(e instanceof ApiError ? e.code : "network_error"));
    api
      .readConsents(tenantId)
      .then(setConsents)
      .catch((e: unknown) => setError(e instanceof ApiError ? e.code : "network_error"));
  }, [tenantId]);

  async function toggleEmails(consent: Consent, granted: boolean) {
    try {
      setConsents(await api.setConsent(tenantId, consent.purpose, granted, consent.current_version));
      setError(null);
    } catch (e) {
      setError(e instanceof ApiError ? e.code : "network_error");
    }
  }

  const emails = consents?.find((c) => c.purpose === "product_emails");

  async function update(locale: string) {
    if (!isLocale(locale)) return;
    try {
      setSaved((await api.updateSettings(tenantId, locale)).locale);
      setError(null);
    } catch (e) {
      setError(e instanceof ApiError ? e.code : "network_error");
    }
  }

  return (
    <section className="card">
      <h1>{t("settings")}</h1>
      {error ? <p role="alert">{t("errorTitle")}</p> : null}
      {saved === null && !error ? (
        <p role="status">{t("loading")}</p>
      ) : (
        <label className="language">
          <span>{t("language")}</span>
          <select data-testid="workspace-locale" value={saved ?? ""} onChange={(e) => void update(e.target.value)}>
            {LOCALES.map((code) => (
              <option key={code} value={code}>
                {code}
              </option>
            ))}
          </select>
        </label>
      )}
      <h2>{t("consents")}</h2>
      {emails ? (
        <label className="check">
          <input
            type="checkbox"
            data-testid="consent-product-emails"
            checked={emails.granted}
            onChange={(e) => void toggleEmails(emails, e.target.checked)}
          />
          <span>{t("productEmails")}</span>
        </label>
      ) : null}
    </section>
  );
}
