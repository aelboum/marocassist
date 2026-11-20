"use client";

import { useEffect, useState, type FormEvent } from "react";

import { useReadySession } from "@/components/AuthGate";
import { api } from "@/lib/api";
import { CONSULATE_CODES, consulateKey } from "@/lib/i18n";
import { useT } from "@/lib/locale-context";

export default function ProfilePage() {
  const t = useT();
  const { tenantId } = useReadySession();
  const [loaded, setLoaded] = useState(false);
  const [displayName, setDisplayName] = useState("");
  const [consulate, setConsulate] = useState("");
  const [status, setStatus] = useState<"idle" | "saved" | "error">("idle");

  useEffect(() => {
    api
      .readProfile(tenantId)
      .then((profile) => {
        setDisplayName(profile.display_name ?? "");
        setConsulate(profile.consulate ?? "");
        setLoaded(true);
      })
      .catch(() => setStatus("error"));
  }, [tenantId]);

  async function save(event: FormEvent) {
    event.preventDefault();
    try {
      const profile = await api.updateProfile(tenantId, {
        display_name: displayName.trim() || null,
        consulate: consulate || null,
      });
      setDisplayName(profile.display_name ?? "");
      setStatus("saved");
    } catch {
      setStatus("error");
    }
  }

  if (!loaded && status !== "error") return <p role="status">{t("loading")}</p>;

  return (
    <form className="card stack" onSubmit={(e) => void save(e)}>
      <h1>{t("profile")}</h1>
      <label className="field">
        <span>{t("displayName")}</span>
        <input
          name="display_name"
          maxLength={80}
          autoComplete="nickname"
          value={displayName}
          onChange={(e) => {
            setDisplayName(e.target.value);
            setStatus("idle");
          }}
        />
      </label>
      <label className="field">
        <span>{t("consulate")}</span>
        <select
          name="consulate"
          value={consulate}
          onChange={(e) => {
            setConsulate(e.target.value);
            setStatus("idle");
          }}
        >
          <option value="">{t("consulateNone")}</option>
          {CONSULATE_CODES.map((code) => {
            const key = consulateKey(code);
            return (
              <option key={code} value={code}>
                {key ? t(key) : code}
              </option>
            );
          })}
        </select>
      </label>
      {status === "error" ? <p role="alert">{t("errorTitle")}</p> : null}
      {status === "saved" ? <p role="status">{t("saved")}</p> : null}
      <button type="submit" className="button">
        {t("save")}
      </button>
    </form>
  );
}
