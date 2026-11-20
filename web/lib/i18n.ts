/**
 * UI strings for nl / fr / ar / en.
 *
 * Arabic is right-to-left: `dir` is set on <html> by the root layout. The
 * chosen locale is kept in a plain, non-sensitive cookie (`ma_locale`) so
 * server rendering uses it. Dutch is the reference text; the French and
 * Arabic texts need a native-speaker review before beta (Phase 2 report).
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
    signUp: "Account aanmaken",
    signOut: "Uitloggen",
    dashboard: "Overzicht",
    copilot: "Copilot",
    settings: "Instellingen",
    profile: "Profiel",
    account: "Account",
    privacy: "Privacy",
    loading: "Laden…",
    errorTitle: "Er ging iets mis",
    retry: "Opnieuw proberen",
    save: "Opslaan",
    saved: "Opgeslagen",
    notSignedIn: "Je bent niet ingelogd.",
    workspace: "Je werkruimte",
    language: "Taal",
    copilotIntro: "Koppel de browserextensie om hulp te krijgen op afspraakpagina's. Jij houdt altijd de controle.",
    verifyTitle: "Bevestig eerst je e-mailadres",
    verifyBody:
      "We hebben je een e-mail gestuurd met een bevestigingscode. Bevestig je adres en log daarna opnieuw in.",
    signInAgain: "Opnieuw inloggen",
    welcomeTitle: "Welkom bij MarocAssist",
    welcomeBody: "Nog een paar gegevens. We vragen alleen wat nodig is.",
    displayName: "Hoe mogen we je noemen? (optioneel)",
    consulate: "Je consulaat",
    consulateNone: "Weet ik nog niet",
    ageConfirm: "Ik ben 18 jaar of ouder.",
    privacyAccept: "Ik heb de privacyverklaring gelezen en ga ermee akkoord.",
    privacyLink: "Privacyverklaring lezen",
    productEmails: "Stuur me e-mail over nieuwe functies en wijzigingen in procedures (optioneel).",
    continue: "Doorgaan",
    noticeUpdatedTitle: "De privacyverklaring is gewijzigd",
    noticeUpdatedBody: "Lees de nieuwe versie en ga akkoord om MarocAssist te blijven gebruiken.",
    accept: "Akkoord",
    consents: "Toestemmingen",
    devices: "Gekoppelde apparaten",
    noDevices: "Nog geen apparaten gekoppeld.",
    revoke: "Ontkoppelen",
    validUntil: "geldig tot",
    exportTitle: "Je gegevens downloaden",
    exportBody: "Download een kopie van alles wat MarocAssist over je account bewaart (JSON).",
    exportButton: "Download mijn gegevens",
    deleteTitle: "Account verwijderen",
    deleteBody:
      "We verwijderen je account en alle gegevens binnen 30 dagen. Je kunt tot dan nog inloggen. Dit kan niet ongedaan worden gemaakt.",
    deleteConfirm: "Ja, verwijder mijn account",
    deleteRequested: "Je verzoek is ontvangen op",
    draftNotice: "Concept, nog niet juridisch getoetst.",
    "consulate.nl-amsterdam": "Consulaat-generaal Amsterdam",
    "consulate.nl-den-bosch": "Consulaat-generaal 's-Hertogenbosch",
    "consulate.nl-rotterdam": "Consulaat-generaal Rotterdam",
    "consulate.nl-utrecht": "Consulaat-generaal Utrecht",
  },
  fr: {
    appName: "MarocAssist",
    tagline: "Aide pour les démarches consulaires marocaines. Non affilié au gouvernement marocain.",
    signIn: "Se connecter",
    signUp: "Créer un compte",
    signOut: "Se déconnecter",
    dashboard: "Aperçu",
    copilot: "Copilot",
    settings: "Paramètres",
    profile: "Profil",
    account: "Compte",
    privacy: "Confidentialité",
    loading: "Chargement…",
    errorTitle: "Une erreur est survenue",
    retry: "Réessayer",
    save: "Enregistrer",
    saved: "Enregistré",
    notSignedIn: "Vous n'êtes pas connecté.",
    workspace: "Votre espace",
    language: "Langue",
    copilotIntro:
      "Associez l'extension du navigateur pour être guidé sur les pages de rendez-vous. Vous gardez toujours le contrôle.",
    verifyTitle: "Confirmez d'abord votre adresse e-mail",
    verifyBody:
      "Nous vous avons envoyé un e-mail avec un code de confirmation. Confirmez votre adresse, puis reconnectez-vous.",
    signInAgain: "Se reconnecter",
    welcomeTitle: "Bienvenue sur MarocAssist",
    welcomeBody: "Encore quelques informations. Nous ne demandons que le nécessaire.",
    displayName: "Comment souhaitez-vous être appelé ? (facultatif)",
    consulate: "Votre consulat",
    consulateNone: "Je ne sais pas encore",
    ageConfirm: "J'ai 18 ans ou plus.",
    privacyAccept: "J'ai lu la politique de confidentialité et je l'accepte.",
    privacyLink: "Lire la politique de confidentialité",
    productEmails:
      "Envoyez-moi des e-mails sur les nouvelles fonctions et les changements de procédures (facultatif).",
    continue: "Continuer",
    noticeUpdatedTitle: "La politique de confidentialité a changé",
    noticeUpdatedBody: "Lisez la nouvelle version et acceptez-la pour continuer à utiliser MarocAssist.",
    accept: "J'accepte",
    consents: "Consentements",
    devices: "Appareils associés",
    noDevices: "Aucun appareil associé pour l'instant.",
    revoke: "Dissocier",
    validUntil: "valable jusqu'au",
    exportTitle: "Télécharger vos données",
    exportBody: "Téléchargez une copie de tout ce que MarocAssist conserve sur votre compte (JSON).",
    exportButton: "Télécharger mes données",
    deleteTitle: "Supprimer le compte",
    deleteBody:
      "Nous supprimons votre compte et toutes vos données dans un délai de 30 jours. Vous pouvez encore vous connecter d'ici là. Cette action est irréversible.",
    deleteConfirm: "Oui, supprimer mon compte",
    deleteRequested: "Votre demande a été reçue le",
    draftNotice: "Projet, pas encore validé juridiquement.",
    "consulate.nl-amsterdam": "Consulat général d'Amsterdam",
    "consulate.nl-den-bosch": "Consulat général de Bois-le-Duc ('s-Hertogenbosch)",
    "consulate.nl-rotterdam": "Consulat général de Rotterdam",
    "consulate.nl-utrecht": "Consulat général d'Utrecht",
  },
  ar: {
    appName: "MarocAssist",
    tagline: "مساعدة في الإجراءات القنصلية المغربية. غير تابع للحكومة المغربية.",
    signIn: "تسجيل الدخول",
    signUp: "إنشاء حساب",
    signOut: "تسجيل الخروج",
    dashboard: "نظرة عامة",
    copilot: "المساعد",
    settings: "الإعدادات",
    profile: "الملف الشخصي",
    account: "الحساب",
    privacy: "الخصوصية",
    loading: "جارٍ التحميل…",
    errorTitle: "حدث خطأ",
    retry: "إعادة المحاولة",
    save: "حفظ",
    saved: "تم الحفظ",
    notSignedIn: "لم تقم بتسجيل الدخول.",
    workspace: "مساحتك",
    language: "اللغة",
    copilotIntro: "اربط إضافة المتصفح للحصول على إرشادات في صفحات المواعيد. تبقى أنت المتحكم دائمًا.",
    verifyTitle: "أكّد بريدك الإلكتروني أولًا",
    verifyBody: "أرسلنا إليك رسالة تحتوي على رمز التأكيد. أكّد عنوانك ثم سجّل الدخول من جديد.",
    signInAgain: "تسجيل الدخول من جديد",
    welcomeTitle: "مرحبًا بك في MarocAssist",
    welcomeBody: "بعض المعلومات فقط. لا نطلب إلا ما هو ضروري.",
    displayName: "بأي اسم نناديك؟ (اختياري)",
    consulate: "قنصليتك",
    consulateNone: "لا أعرف بعد",
    ageConfirm: "عمري 18 سنة أو أكثر.",
    privacyAccept: "قرأت سياسة الخصوصية وأوافق عليها.",
    privacyLink: "قراءة سياسة الخصوصية",
    productEmails: "أرسلوا لي رسائل حول الميزات الجديدة وتغييرات الإجراءات (اختياري).",
    continue: "متابعة",
    noticeUpdatedTitle: "تم تغيير سياسة الخصوصية",
    noticeUpdatedBody: "اقرأ النسخة الجديدة ووافق عليها لمواصلة استخدام MarocAssist.",
    accept: "أوافق",
    consents: "الموافقات",
    devices: "الأجهزة المرتبطة",
    noDevices: "لا توجد أجهزة مرتبطة بعد.",
    revoke: "إلغاء الربط",
    validUntil: "صالح حتى",
    exportTitle: "تنزيل بياناتك",
    exportBody: "نزّل نسخة من كل ما يحتفظ به MarocAssist عن حسابك (JSON).",
    exportButton: "تنزيل بياناتي",
    deleteTitle: "حذف الحساب",
    deleteBody: "نحذف حسابك وجميع بياناتك خلال 30 يومًا. يمكنك تسجيل الدخول حتى ذلك الحين. لا يمكن التراجع عن ذلك.",
    deleteConfirm: "نعم، احذف حسابي",
    deleteRequested: "تم استلام طلبك في",
    draftNotice: "مسودة، لم تخضع بعد لمراجعة قانونية.",
    "consulate.nl-amsterdam": "القنصلية العامة في أمستردام",
    "consulate.nl-den-bosch": "القنصلية العامة في دن بوس",
    "consulate.nl-rotterdam": "القنصلية العامة في روتردام",
    "consulate.nl-utrecht": "القنصلية العامة في أوتريخت",
  },
  en: {
    appName: "MarocAssist",
    tagline: "Help with Moroccan consular procedures. Not affiliated with the Moroccan government.",
    signIn: "Sign in",
    signUp: "Create an account",
    signOut: "Sign out",
    dashboard: "Overview",
    copilot: "Copilot",
    settings: "Settings",
    profile: "Profile",
    account: "Account",
    privacy: "Privacy",
    loading: "Loading…",
    errorTitle: "Something went wrong",
    retry: "Try again",
    save: "Save",
    saved: "Saved",
    notSignedIn: "You are not signed in.",
    workspace: "Your workspace",
    language: "Language",
    copilotIntro: "Pair the browser extension to get guidance on appointment pages. You always stay in control.",
    verifyTitle: "Please confirm your email address first",
    verifyBody: "We sent you an email with a confirmation code. Confirm your address, then sign in again.",
    signInAgain: "Sign in again",
    welcomeTitle: "Welcome to MarocAssist",
    welcomeBody: "Just a few details. We only ask for what is needed.",
    displayName: "What should we call you? (optional)",
    consulate: "Your consulate",
    consulateNone: "I don't know yet",
    ageConfirm: "I am 18 years or older.",
    privacyAccept: "I have read and accept the privacy notice.",
    privacyLink: "Read the privacy notice",
    productEmails: "Email me about new features and changes to procedures (optional).",
    continue: "Continue",
    noticeUpdatedTitle: "The privacy notice has changed",
    noticeUpdatedBody: "Read the new version and accept it to keep using MarocAssist.",
    accept: "Accept",
    consents: "Consents",
    devices: "Paired devices",
    noDevices: "No devices paired yet.",
    revoke: "Unpair",
    validUntil: "valid until",
    exportTitle: "Download your data",
    exportBody: "Download a copy of everything MarocAssist keeps about your account (JSON).",
    exportButton: "Download my data",
    deleteTitle: "Delete account",
    deleteBody:
      "We delete your account and all your data within 30 days. You can still sign in until then. This cannot be undone.",
    deleteConfirm: "Yes, delete my account",
    deleteRequested: "Your request was received on",
    draftNotice: "Draft, not yet legally reviewed.",
    "consulate.nl-amsterdam": "Consulate-General Amsterdam",
    "consulate.nl-den-bosch": "Consulate-General 's-Hertogenbosch",
    "consulate.nl-rotterdam": "Consulate-General Rotterdam",
    "consulate.nl-utrecht": "Consulate-General Utrecht",
  },
} as const satisfies Record<Locale, Record<string, string>>;

export type MessageKey = keyof (typeof messages)["nl"];

export function t(locale: Locale, key: MessageKey): string {
  return messages[locale][key];
}

export function messageKeys(locale: Locale): string[] {
  return Object.keys(messages[locale]).sort();
}

export const CONSULATE_CODES = ["nl-amsterdam", "nl-den-bosch", "nl-rotterdam", "nl-utrecht"] as const;

export function consulateKey(code: string): MessageKey | null {
  return (CONSULATE_CODES as readonly string[]).includes(code) ? (`consulate.${code}` as MessageKey) : null;
}
