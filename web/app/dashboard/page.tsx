"use client";

import { useReadySession } from "@/components/AuthGate";
import { useT } from "@/lib/locale-context";

export default function DashboardPage() {
  const t = useT();
  const session = useReadySession();
  return (
    <section className="card">
      <h1>{t("dashboard")}</h1>
      <p>
        {t("workspace")}: <code data-testid="tenant-id">{session.tenantId}</code>
      </p>
    </section>
  );
}
