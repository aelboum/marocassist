"use client";

import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

import { useReadySession } from "@/components/AuthGate";
import { formatDate, ItemBody, ReportForm, ScopeText, SourceCards, StatusNotice } from "@/components/Knowledge";
import { ApiError, api, type KnowledgeItem } from "@/lib/api";
import { contentDir } from "@/lib/knowledge";
import { useLocale, useT } from "@/lib/locale-context";

function ItemView() {
  const t = useT();
  const locale = useLocale();
  const { tenantId } = useReadySession();
  const params = useParams<{ itemId: string }>();
  const searchParams = useSearchParams();
  const itemId = decodeURIComponent(params.itemId);
  const lang = searchParams.get("lang") ?? locale;
  const [item, setItem] = useState<KnowledgeItem | null>(null);
  const [state, setState] = useState<"loading" | "ready" | "missing" | "error">("loading");

  useEffect(() => {
    let cancelled = false;
    api
      .readItem(tenantId, itemId, lang)
      .then((loaded) => {
        if (cancelled) return;
        setItem(loaded);
        setState("ready");
      })
      .catch((error: unknown) => {
        if (cancelled) return;
        setState(error instanceof ApiError && (error.status === 404 || error.status === 422) ? "missing" : "error");
      });
    return () => {
      cancelled = true;
    };
  }, [tenantId, itemId, lang]);

  const back = (
    <p>
      <Link href="/dashboard/knowledge">{t("kn.backToSearch")}</Link>
    </p>
  );
  if (state === "loading") return <p role="status">{t("loading")}</p>;
  if (state === "missing") {
    return (
      <section className="card">
        <p role="alert">{t("kn.notFound")}</p>
        {back}
      </section>
    );
  }
  if (state === "error" || !item) {
    return (
      <section className="card">
        <p role="alert">{t("errorTitle")}</p>
        {back}
      </section>
    );
  }

  return (
    <article className="card stack" data-testid="knowledge-item">
      {back}
      {item.title && item.lang ? (
        <h1 lang={item.lang} dir={contentDir(item.lang)}>
          {item.title}
        </h1>
      ) : null}
      <StatusNotice status={item.status} />
      {item.status === "withdrawn" && item.superseded_by ? (
        <p>
          <Link href={`/dashboard/knowledge/${encodeURIComponent(item.superseded_by)}`}>{t("kn.supersededBy")}</Link>
        </p>
      ) : null}
      {item.lang && item.lang !== locale && item.status !== "withdrawn" ? (
        <p className="muted small">{t("kn.otherLanguage")}</p>
      ) : null}
      <p className="muted small">
        {item.consulate_scope.length > 0 ? (
          item.consulate_scope.map((code) => (
            <span key={code}>
              <ScopeText scope={`consulate:${code}`} />{" "}
            </span>
          ))
        ) : (
          <ScopeText scope="global" />
        )}
        {item.verified_at ? ` · ${t("kn.lastVerified")}: ${formatDate(locale, item.verified_at)}` : null}
      </p>
      {item.body && item.lang ? <ItemBody body={item.body} lang={item.lang} /> : null}
      <SourceCards sources={item.sources} />
      <p className="muted small">{t("kn.disclaimer")}</p>
      {item.status !== "withdrawn" ? <ReportForm tenantId={tenantId} itemId={item.item_id} /> : null}
    </article>
  );
}

export default function KnowledgeItemPage() {
  return (
    <Suspense fallback={null}>
      <ItemView />
    </Suspense>
  );
}
