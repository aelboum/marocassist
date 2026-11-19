"use client";

import { useT } from "@/lib/locale-context";

// Error boundary for every route. Shows no error details: they can contain
// data, and the request id is in the backend's logs.
export default function GlobalRouteError({ reset }: { error: Error; reset: () => void }) {
  const t = useT();
  return (
    <div role="alert" className="center card">
      <p>{t("errorTitle")}</p>
      <button type="button" className="button" onClick={reset}>
        {t("retry")}
      </button>
    </div>
  );
}
