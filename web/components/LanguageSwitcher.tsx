"use client";

import { useRouter } from "next/navigation";

import { LOCALE_COOKIE, LOCALES, type Locale } from "@/lib/i18n";
import { useLocale, useT } from "@/lib/locale-context";

const LABELS: Record<Locale, string> = { nl: "Nederlands", fr: "Français", ar: "العربية", en: "English" };

export function LanguageSwitcher() {
  const locale = useLocale();
  const t = useT();
  const router = useRouter();

  function choose(next: Locale) {
    // Not sensitive: only the language code. One year, this origin only.
    document.cookie = `${LOCALE_COOKIE}=${next}; Path=/; Max-Age=31536000; SameSite=Lax`;
    router.refresh();
  }

  return (
    <label className="language">
      <span>{t("language")}</span>
      <select value={locale} onChange={(event) => choose(event.target.value as Locale)} aria-label={t("language")}>
        {LOCALES.map((code) => (
          <option key={code} value={code} lang={code}>
            {LABELS[code]}
          </option>
        ))}
      </select>
    </label>
  );
}
