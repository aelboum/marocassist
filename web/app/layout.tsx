import type { Metadata, Viewport } from "next";
import { cookies } from "next/headers";
import type { ReactNode } from "react";

import { direction, LOCALE_COOKIE, resolveLocale } from "@/lib/i18n";
import { LocaleProvider } from "@/lib/locale-context";

import "./globals.css";

export const metadata: Metadata = {
  title: "MarocAssist",
  description: "Independent help with Moroccan consular procedures. Not affiliated with the Moroccan government.",
};

export const viewport: Viewport = { width: "device-width", initialScale: 1 };

export default async function RootLayout({ children }: { children: ReactNode }) {
  const locale = resolveLocale((await cookies()).get(LOCALE_COOKIE)?.value);
  return (
    <html lang={locale} dir={direction(locale)}>
      <body>
        <LocaleProvider locale={locale}>{children}</LocaleProvider>
      </body>
    </html>
  );
}
