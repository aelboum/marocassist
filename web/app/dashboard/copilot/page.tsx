"use client";

import { useEffect, useState } from "react";

import { useReadySession } from "@/components/AuthGate";
import { ApiError, api } from "@/lib/api";
import { useT } from "@/lib/locale-context";

type Device = { id: string; status: string; created_at: string; key_expires_at: string | null };

export default function CopilotPage() {
  const t = useT();
  const { tenantId } = useReadySession();
  const [devices, setDevices] = useState<Device[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .listDevices(tenantId)
      .then(setDevices)
      .catch((e: unknown) => setError(e instanceof ApiError ? e.code : "network_error"));
  }, [tenantId]);

  return (
    <section className="card">
      <h1>{t("copilot")}</h1>
      <p>{t("copilotIntro")}</p>
      {error ? <p role="alert">{t("errorTitle")}</p> : null}
      {devices === null && !error ? <p role="status">{t("loading")}</p> : null}
      {devices && devices.length > 0 ? (
        <ul>
          {devices.map((d) => (
            <li key={d.id}>
              <code>{d.id.slice(0, 8)}</code> — {d.status}
              {d.key_expires_at ? ` — ${new Date(d.key_expires_at).toLocaleString()}` : ""}
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}
