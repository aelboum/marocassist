"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

import { LanguageSwitcher } from "@/components/LanguageSwitcher";
import type { MessageKey } from "@/lib/i18n";
import { useT } from "@/lib/locale-context";

export const NAV_ITEMS: ReadonlyArray<{ href: string; label: MessageKey }> = [
  { href: "/dashboard", label: "dashboard" },
  { href: "/dashboard/profile", label: "profile" },
  { href: "/dashboard/copilot", label: "copilot" },
  { href: "/dashboard/settings", label: "settings" },
  { href: "/dashboard/account", label: "account" },
];

export function AppShell({ children, onSignOut }: { children: ReactNode; onSignOut?: () => void }) {
  const t = useT();
  const pathname = usePathname();

  return (
    <div className="shell">
      <header className="shell-header">
        <Link href="/" className="brand">
          {t("appName")}
        </Link>
        <nav aria-label="main" className="shell-nav">
          {NAV_ITEMS.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              aria-current={pathname === item.href ? "page" : undefined}
              className="nav-link"
            >
              {t(item.label)}
            </Link>
          ))}
        </nav>
        <div className="shell-actions">
          <LanguageSwitcher />
          {onSignOut ? (
            <button type="button" onClick={onSignOut} className="button-secondary">
              {t("signOut")}
            </button>
          ) : null}
        </div>
      </header>
      <main className="shell-main">{children}</main>
      <footer className="shell-footer">
        {t("tagline")} <Link href="/privacy">{t("privacy")}</Link>
      </footer>
    </div>
  );
}
