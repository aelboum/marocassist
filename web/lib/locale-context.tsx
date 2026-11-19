"use client";

import { createContext, useContext, type ReactNode } from "react";

import { DEFAULT_LOCALE, type Locale, type MessageKey, t } from "@/lib/i18n";

const LocaleContext = createContext<Locale>(DEFAULT_LOCALE);

export function LocaleProvider({ locale, children }: { locale: Locale; children: ReactNode }) {
  return <LocaleContext.Provider value={locale}>{children}</LocaleContext.Provider>;
}

export function useLocale(): Locale {
  return useContext(LocaleContext);
}

export function useT(): (key: MessageKey) => string {
  const locale = useLocale();
  return (key) => t(locale, key);
}
