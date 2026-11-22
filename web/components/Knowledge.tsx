"use client";

import { useState, type FormEvent } from "react";

import { api, type ItemStatus, type SourceCard } from "@/lib/api";
import { consulateKey, type Locale, type MessageKey } from "@/lib/i18n";
import {
  badgeKey,
  bodyBlocks,
  contentDir,
  itemNotice,
  REASON_KEYS,
  REPORT_REASONS,
  safeExternalUrl,
  scopeLabel,
  sourceNotice,
  type ReportReason,
} from "@/lib/knowledge";
import { useLocale, useT } from "@/lib/locale-context";

export function formatDate(locale: Locale, value: string | null): string {
  if (!value) return "";
  const date = new Date(`${value}T00:00:00Z`);
  if (Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat(locale, { dateStyle: "medium", timeZone: "UTC" }).format(date);
}

export function ScopeText({ scope }: { scope: string }) {
  const t = useT();
  const label = scopeLabel(scope);
  let detail = "";
  if (label.key === "kn.scope.consulate" && label.code) {
    const key = consulateKey(label.code);
    detail = key ? t(key) : label.code;
  } else if (label.key === "kn.scope.country" && label.code) {
    detail = label.code === "NL" || label.code === "MA" ? t(`kn.country.${label.code}` as MessageKey) : label.code;
  }
  return <span>{detail ? `${t(label.key)}: ${detail}` : t(label.key)}</span>;
}

export function StatusNotice({ status }: { status: ItemStatus }) {
  const t = useT();
  const key = itemNotice(status);
  if (!key) return null;
  return (
    <p className={`notice notice-${status}`} role="note" data-testid="status-notice">
      {t(key)}
    </p>
  );
}

/** Source cards (content rights section 7): built by the server from the
 * source register; the outbound link opens the official page in a new tab. */
export function SourceCards({ sources }: { sources: SourceCard[] }) {
  const t = useT();
  const locale = useLocale();
  if (sources.length === 0) return null;
  return (
    <section aria-label={t("kn.sources")} className="sources">
      <h2 className="sources-title">{t("kn.sources")}</h2>
      <ol className="source-list">
        {sources.map((source) => {
          const url = safeExternalUrl(source.url);
          const notice = sourceNotice(source.status);
          return (
            <li key={source.source_id} className="source-card" data-testid="source-card">
              <span className={`badge badge-${source.badge}`}>{t(badgeKey(source.badge))}</span>{" "}
              <span className="source-label">[{source.label}]</span>{" "}
              <bdi className="source-title">{source.title}</bdi>
              <span className="muted"> · {source.publisher}</span>
              <div className="muted small">
                <ScopeText scope={source.scope} />
                {source.verified_at ? (
                  <>
                    {" · "}
                    {t("kn.lastVerified")}: {formatDate(locale, source.verified_at)}
                  </>
                ) : null}
              </div>
              {notice ? (
                <p className="notice small" role="note">
                  {t(notice)}
                </p>
              ) : null}
              {url ? (
                <a href={url} target="_blank" rel="noopener noreferrer" className="small" data-testid="source-link">
                  {t("kn.openSource")}
                </a>
              ) : null}
            </li>
          );
        })}
      </ol>
    </section>
  );
}

/** An item body: `## Heading` lines and paragraphs, as plain text in the
 * content's own language and direction. */
export function ItemBody({ body, lang }: { body: string; lang: string }) {
  return (
    <div className="prose" lang={lang} dir={contentDir(lang)}>
      {bodyBlocks(body).map((block, index) =>
        block.kind === "heading" ? <h2 key={index}>{block.text}</h2> : <p key={index}>{block.text}</p>,
      )}
    </div>
  );
}

/** "Report outdated": the item id and a reason code, nothing else. */
export function ReportForm({ tenantId, itemId }: { tenantId: string; itemId: string }) {
  const t = useT();
  const [reason, setReason] = useState<ReportReason>("outdated");
  const [state, setState] = useState<"idle" | "sending" | "sent" | "error">("idle");

  async function submit(event: FormEvent) {
    event.preventDefault();
    setState("sending");
    try {
      await api.reportItem(tenantId, itemId, reason);
      setState("sent");
    } catch {
      setState("error");
    }
  }

  if (state === "sent") {
    return (
      <p role="status" data-testid="report-sent">
        {t("kn.reportThanks")}
      </p>
    );
  }
  return (
    <form className="report stack" onSubmit={(e) => void submit(e)} aria-label={t("kn.report")}>
      <h2 className="sources-title">{t("kn.report")}</h2>
      <label className="field">
        <span>{t("kn.reportReason")}</span>
        <select name="reason" value={reason} onChange={(e) => setReason(e.target.value as ReportReason)}>
          {REPORT_REASONS.map((code) => (
            <option key={code} value={code}>
              {t(REASON_KEYS[code])}
            </option>
          ))}
        </select>
      </label>
      {state === "error" ? <p role="alert">{t("errorTitle")}</p> : null}
      <div>
        <button type="submit" className="button-secondary" disabled={state === "sending"}>
          {t("kn.reportSend")}
        </button>
      </div>
    </form>
  );
}
