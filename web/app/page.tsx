import Link from "next/link";
import { cookies } from "next/headers";

import { LOGIN_PATH } from "@/lib/api";
import { LOCALE_COOKIE, resolveLocale, t } from "@/lib/i18n";

export default async function HomePage() {
  const locale = resolveLocale((await cookies()).get(LOCALE_COOKIE)?.value);
  return (
    <main className="center">
      <h1>{t(locale, "appName")}</h1>
      <p>{t(locale, "tagline")}</p>
      <p style={{ display: "flex", gap: 12, justifyContent: "center", flexWrap: "wrap" }}>
        <a className="button" href={LOGIN_PATH}>
          {t(locale, "signIn")}
        </a>
        <Link className="button-secondary" href="/dashboard">
          {t(locale, "dashboard")}
        </Link>
      </p>
    </main>
  );
}
