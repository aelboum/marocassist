"use client";

import { useEffect, useState } from "react";

import { useReadySession } from "@/components/AuthGate";
import { api, type DeletionRequest } from "@/lib/api";
import { useLocale, useT } from "@/lib/locale-context";

/**
 * Account rights: download a copy of the data, request deletion. The
 * export is fetched with the session cookie and handed to the browser as
 * a local file; nothing is sent anywhere else.
 */
export default function AccountPage() {
  const t = useT();
  const locale = useLocale();
  const { tenantId } = useReadySession();
  const [deletion, setDeletion] = useState<DeletionRequest | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [error, setError] = useState(false);

  useEffect(() => {
    api
      .readDeletionRequest(tenantId)
      .then(setDeletion)
      .catch(() => setError(true));
  }, [tenantId]);

  async function download() {
    try {
      const data = await api.exportAccount(tenantId);
      const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }));
      const link = document.createElement("a");
      link.href = url;
      link.download = "marocassist-export.json";
      link.click();
      URL.revokeObjectURL(url);
    } catch {
      setError(true);
    }
  }

  async function requestDeletion() {
    try {
      setDeletion(await api.requestDeletion(tenantId));
      setConfirming(false);
    } catch {
      setError(true);
    }
  }

  return (
    <div className="stack">
      {error ? <p role="alert">{t("errorTitle")}</p> : null}
      <section className="card stack">
        <h1>{t("exportTitle")}</h1>
        <p>{t("exportBody")}</p>
        <button type="button" className="button" data-testid="export-account" onClick={() => void download()}>
          {t("exportButton")}
        </button>
      </section>
      <section className="card stack">
        <h2>{t("deleteTitle")}</h2>
        {deletion?.requested && deletion.requested_at ? (
          <p role="status" data-testid="deletion-requested">
            {t("deleteRequested")} {new Date(deletion.requested_at).toLocaleDateString(locale)}
          </p>
        ) : (
          <>
            <p>{t("deleteBody")}</p>
            {confirming ? (
              <button
                type="button"
                className="button-danger"
                data-testid="delete-confirm"
                onClick={() => void requestDeletion()}
              >
                {t("deleteConfirm")}
              </button>
            ) : (
              <button type="button" className="button-secondary" onClick={() => setConfirming(true)}>
                {t("deleteTitle")}
              </button>
            )}
          </>
        )}
      </section>
    </div>
  );
}
