"use client";

import { useEffect, useState } from "react";

import { useReadySession } from "@/components/AuthGate";
import { ApiError, api, type Device } from "@/lib/api";
import { useLocale, useT } from "@/lib/locale-context";

export default function CopilotPage() {
  const t = useT();
  const locale = useLocale();
  const { tenantId } = useReadySession();
  const [devices, setDevices] = useState<Device[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .listDevices(tenantId)
      .then(setDevices)
      .catch((e: unknown) => setError(e instanceof ApiError ? e.code : "network_error"));
  }, [tenantId]);

  async function revoke(deviceId: string) {
    try {
      await api.revokeDevice(tenantId, deviceId);
      setDevices(await api.listDevices(tenantId));
    } catch (e) {
      setError(e instanceof ApiError ? e.code : "network_error");
    }
  }

  return (
    <section className="card">
      <h1>{t("copilot")}</h1>
      <p>{t("copilotIntro")}</p>
      {error ? <p role="alert">{t("errorTitle")}</p> : null}
      {devices === null && !error ? <p role="status">{t("loading")}</p> : null}
      <h2>{t("devices")}</h2>
      {devices && devices.length === 0 ? <p>{t("noDevices")}</p> : null}
      {devices && devices.length > 0 ? (
        <ul data-testid="device-list">
          {devices.map((d) => (
            <li key={d.id}>
              <code>{d.id.slice(0, 8)}</code>
              {d.key_expires_at ? ` — ${t("validUntil")} ${new Date(d.key_expires_at).toLocaleString(locale)}` : ""}{" "}
              <button type="button" className="button-secondary" onClick={() => void revoke(d.id)}>
                {t("revoke")}
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}
