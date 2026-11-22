"use client";

import { useEffect, useState } from "react";

import { useReadySession } from "@/components/AuthGate";
import { formatDate } from "@/components/Knowledge";
import { api, type Consulate, type ConsulateAttribute } from "@/lib/api";
import { ATTRIBUTE_KEYS, attributeLines, safeExternalUrl } from "@/lib/knowledge";
import { useLocale, useT } from "@/lib/locale-context";

function AttributeRow({ attribute }: { attribute: ConsulateAttribute }) {
  const t = useT();
  const locale = useLocale();
  const url = safeExternalUrl(attribute.source.url);
  const lines = attributeLines(attribute);
  return (
    <div className="attribute" data-testid={`attribute-${attribute.attribute}`}>
      <dt>{t(ATTRIBUTE_KEYS[attribute.attribute] ?? "kn.attr.contact")}</dt>
      <dd>
        {lines.map((line) => (
          // The row keeps the page direction; the value is isolated inside it.
          <div key={line}>
            <bdi>{line}</bdi>
          </div>
        ))}
        {attribute.status === "pending_review" ? (
          <p className="notice small" role="note" data-testid="attribute-pending">
            {t("kn.attr.pending")}
          </p>
        ) : null}
        {attribute.status === "expired" ? (
          <p className="notice small" role="note">
            {t("kn.attr.expired")}
          </p>
        ) : null}
        <span className="muted small">
          {t("kn.lastVerified")}: {formatDate(locale, attribute.verified_at)}
          {url ? (
            <>
              {" · "}
              <a href={url} target="_blank" rel="noopener noreferrer">
                {attribute.source.publisher}
              </a>
            </>
          ) : null}
        </span>
      </dd>
    </div>
  );
}

/** Consulates with a status per attribute (owner decision P3-D5): an
 * attribute confirmed by one source only says so; missing data is never
 * filled in. */
export default function ConsulatesPage() {
  const t = useT();
  const locale = useLocale();
  const { tenantId } = useReadySession();
  const [consulates, setConsulates] = useState<Consulate[] | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api
      .listConsulates(tenantId, locale)
      .then((loaded) => {
        if (!cancelled) setConsulates(loaded);
      })
      .catch(() => {
        if (!cancelled) setError(true);
      });
    return () => {
      cancelled = true;
    };
  }, [tenantId, locale]);

  if (error) return <p role="alert">{t("errorTitle")}</p>;
  if (!consulates) return <p role="status">{t("loading")}</p>;
  return (
    <div className="stack">
      <h1>{t("kn.consulatesTitle")}</h1>
      <p className="muted small">{t("kn.disclaimer")}</p>
      {consulates.map((consulate) => {
        const shown = consulate.attributes.filter((a) => a.attribute !== "display_name");
        return (
          <section key={consulate.code} className="card stack" data-testid={`consulate-${consulate.code}`}>
            <h2>
              <bdi>{consulate.display_name ?? consulate.code}</bdi>
            </h2>
            <dl className="attributes">
              {shown.map((attribute) => (
                <AttributeRow key={`${attribute.attribute}/${attribute.lang ?? ""}`} attribute={attribute} />
              ))}
              {consulate.missing.map((name) => (
                <div key={name} className="attribute" data-testid={`missing-${name}`}>
                  <dt>{t(ATTRIBUTE_KEYS[name] ?? "kn.attr.contact")}</dt>
                  <dd className="muted">{t("kn.attr.missing")}</dd>
                </div>
              ))}
            </dl>
          </section>
        );
      })}
    </div>
  );
}
