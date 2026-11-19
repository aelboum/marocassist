/**
 * Locale preparation for nl / fr / ar / en.
 *
 * Phase 1 ships the mechanism and the navigation strings only; full
 * translations are later work. Arabic is right-to-left: `dir` is set on
 * <html> by the root layout. The chosen locale is kept in a plain,
 * non-sensitive cookie (`ma_locale`) so server rendering uses it.
 */

export const LOCALES = ["nl", "fr", "ar", "en"] as const;
export type Locale = (typeof LOCALES)[number];
export const DEFAULT_LOCALE: Locale = "nl";
export const LOCALE_COOKIE = "ma_locale";

export function isLocale(value: unknown): value is Locale {
  return typeof value === "string" && (LOCALES as readonly string[]).includes(value);
}

export function resolveLocale(value: string | undefined | null): Locale {
  return isLocale(value) ? value : DEFAULT_LOCALE;
}

export function direction(locale: Locale): "rtl" | "ltr" {
  return locale === "ar" ? "rtl" : "ltr";
}

const messages = {
  nl: {
    appName: "MarocAssist",
    tagline: "Hulp bij Marokkaanse consulaire procedures. Niet verbonden aan de Marokkaanse overheid.",
    signIn: "Inloggen",
    signOut: "Uitloggen",
    dashboard: "Overzicht",
    copilot: "Copilot",
    settings: "Instellingen",
    loading: "Laden…",
    errorTitle: "Er ging iets mis",
    retry: "Opnieuw proberen",
    notSignedIn: "Je bent niet ingelogd.",
    workspace: "Je werkruimte",
    language: "Taal",
    copilotIntro: "Koppel de browserextensie om hulp te krijgen op afspraakpagina's. Jij houdt altijd de controle.",
  },
  fr: {
    appName: "MarocAssist",
    tagline: "Aide pour les démarches consulaires marocaines. Non affilié au gouvernement marocain.",
    signIn: "Se connecter",
    signOut: "Se déconnecter",
    dashboard: "Aperçu",
    copilot: "Copilot",
    settings: "Paramètres",
    loading: "Chargement…",
    errorTitle: "Une erreur est survenue",
    retry: "Réessayer",
    notSignedIn: "Vous n'êtes pas connecté.",
    workspace: "Votre espace",
    language: "Langue",
    copilotIntro:
      "Associez l'extension du navigateur pour être guidé sur les pages de rendez-vous. Vous gardez toujours le contrôle.",
  },
  ar: {
    appName: "MarocAssist",
    tagline: "مساعدة في الإجراءات القنصلية المغربية. غير تابع للحكومة المغربية.",
    signIn: "تسجيل الدخول",
    signOut: "تسجيل الخروج",
    dashboard: "نظرة عامة",
    copilot: "المساعد",
    settings: "الإعدادات",
    loading: "جارٍ التحميل…",
    errorTitle: "حدث خطأ",
    retry: "إعادة المحاولة",
    notSignedIn: "لم تقم بتسجيل الدخول.",
    workspace: "مساحتك",
    language: "اللغة",
    copilotIntro: "اربط إضافة المتصفح للحصول على إرشادات في صفحات المواعيد. تبقى أنت المتحكم دائمًا.",
  },
  en: {
    appName: "MarocAssist",
    tagline: "Help with Moroccan consular procedures. Not affiliated with the Moroccan government.",
    signIn: "Sign in",
    signOut: "Sign out",
    dashboard: "Overview",
    copilot: "Copilot",
    settings: "Settings",
    loading: "Loading…",
    errorTitle: "Something went wrong",
    retry: "Try again",
    notSignedIn: "You are not signed in.",
    workspace: "Your workspace",
    language: "Language",
    copilotIntro: "Pair the browser extension to get guidance on appointment pages. You always stay in control.",
  },
} as const satisfies Record<Locale, Record<string, string>>;

export type MessageKey = keyof (typeof messages)["nl"];

export function t(locale: Locale, key: MessageKey): string {
  return messages[locale][key];
}

export function messageKeys(locale: Locale): string[] {
  return Object.keys(messages[locale]).sort();
}
