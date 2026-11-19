"use client";

import { useEffect, useState } from "react";

import { useReadySession } from "@/components/AuthGate";
import { ApiError, api } from "@/lib/api";
import { isLocale, LOCALES } from "@/lib/i18n";
import { useT } from "@/lib/locale-context";

export default function SettingsPage() {
  const t = useT();
  const { tenantId } = useReadySession();
  const [saved, setSaved] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .readSettings(tenantId)
      .then((s) => setSaved(s.locale))
      .catch((e: unknown) => setError(e instanceof ApiError ? e.code : "network_error"));
  }, [tenantId]);

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
    </section>
  );
}
