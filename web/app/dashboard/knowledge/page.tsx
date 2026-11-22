"use client";

import Link from "next/link";
import { useEffect, useState, type FormEvent } from "react";

import { useReadySession } from "@/components/AuthGate";
import { SourceCards, StatusNotice } from "@/components/Knowledge";
import { api, type SearchResponse } from "@/lib/api";
import { CONSULATE_CODES, consulateKey } from "@/lib/i18n";
import { contentDir } from "@/lib/knowledge";
import { useLocale, useT } from "@/lib/locale-context";

/**
 * Knowledge search. The query stays in component state only: it is not put
 * in the page URL (browser history) and the backend neither stores nor
 * logs it. The consulate filter starts from the profile's consulate.
 */
export default function KnowledgeSearchPage() {
  const t = useT();
  const locale = useLocale();
  const { tenantId } = useReadySession();
  const [query, setQuery] = useState("");
  const [consulate, setConsulate] = useState("");
  const [response, setResponse] = useState<SearchResponse | null>(null);
  const [state, setState] = useState<"idle" | "searching" | "error">("idle");

  useEffect(() => {
    api
      .readProfile(tenantId)
      .then((profile) => setConsulate((current) => current || profile.consulate || ""))
      .catch(() => undefined); // no profile consulate: search all consulates
  }, [tenantId]);

  async function search(event: FormEvent) {
    event.preventDefault();
    if (!query.trim()) return;
    setState("searching");
    try {
      setResponse(await api.searchKnowledge(tenantId, { q: query, lang: locale, consulate: consulate || null }));
      setState("idle");
    } catch {
      setResponse(null);
      setState("error");
    }
  }

  return (
    <div className="stack">
      <form className="card stack" role="search" onSubmit={(e) => void search(e)}>
        <h1>{t("kn.searchTitle")}</h1>
        <label className="field">
          <span>{t("kn.searchLabel")}</span>
          <input
            name="q"
            type="search"
            maxLength={256}
            autoComplete="off"
            placeholder={t("kn.searchPlaceholder")}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </label>
        <label className="field">
          <span>{t("kn.filterConsulate")}</span>
          <select name="consulate" value={consulate} onChange={(e) => setConsulate(e.target.value)}>
            <option value="">{t("kn.filterAll")}</option>
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
        <div>
          <button type="submit" className="button" disabled={state === "searching"}>
            {t("kn.searchButton")}
          </button>
        </div>
        <p className="muted small">{t("kn.disclaimer")}</p>
      </form>

      {state === "searching" ? <p role="status">{t("loading")}</p> : null}
      {state === "error" ? <p role="alert">{t("kn.unavailable")}</p> : null}
      {response && response.results.length === 0 ? <p role="status">{t("kn.noResults")}</p> : null}
      {response && response.results.length > 0 ? (
        <ol className="results stack" aria-label={t("kn.searchTitle")}>
          {response.results.map((result) => (
            <li key={`${result.item_id}/${result.lang}/${result.ordinal}`} className="card" data-testid="search-result">
              <h2 className="result-title" lang={result.lang} dir={contentDir(result.lang)}>
                <Link href={`/dashboard/knowledge/${encodeURIComponent(result.item_id)}?lang=${result.lang}`}>
                  {result.title}
                </Link>
              </h2>
              {result.heading ? (
                <p className="muted small" lang={result.lang} dir={contentDir(result.lang)}>
                  {result.heading}
                </p>
              ) : null}
              <p lang={result.lang} dir={contentDir(result.lang)}>
                {result.snippet}
              </p>
              {result.partial ? <p className="muted small">{t("kn.partial")}</p> : null}
              <StatusNotice status={result.status} />
              <SourceCards sources={result.sources} />
            </li>
          ))}
        </ol>
      ) : null}
    </div>
  );
}
