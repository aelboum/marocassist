import { cookies } from "next/headers";
import Link from "next/link";

import { LOCALE_COOKIE, resolveLocale, t } from "@/lib/i18n";

/**
 * Privacy notice, version 2026-11-draft (Phase 2 decision P2-5).
 *
 * DRAFT: not legally reviewed. The controller's identity and contact, the
 * hosting provider and retention periods are placeholders the owner and
 * counsel must complete before any real user signs up
 * (docs/architecture/SECURITY_AND_PRIVACY.md, Q-P1..Q-P8). Dutch is the
 * reference text; other languages show the English version until reviewed
 * translations exist. The version must match PRIVACY_NOTICE_VERSION in
 * backend/src/marocassist/accounts/profile.py (checked by a web test).
 */

const VERSION = "2026-11-draft";

const nl = {
  title: "Privacyverklaring",
  sections: [
    [
      "Wie wij zijn",
      "MarocAssist is een onafhankelijke dienst die helpt bij Marokkaanse consulaire procedures. Wij zijn niet verbonden aan de Marokkaanse overheid of een consulaat. Verwerkingsverantwoordelijke: [naam en contactgegevens — in te vullen door de eigenaar].",
    ],
    [
      "Welke gegevens wij verwerken",
      "Je e-mailadres en wachtwoord worden beheerd door onze inlogdienst; MarocAssist zelf slaat je e-mailadres niet op. Wij bewaren: een optionele weergavenaam, je consulaat, je taal, je toestemmingen, je verzoek om verwijdering en de lijst van gekoppelde browserextensies. Wij vragen geen geboortedatum, nationaliteit of documentnummers.",
    ],
    [
      "Waarom",
      "Om de dienst te leveren (uitvoering van de overeenkomst) en, alleen als je daarvoor kiest, om je e-mail te sturen over nieuwe functies (toestemming, altijd in te trekken in Instellingen).",
    ],
    [
      "Beveiliging en logboeken",
      "Wijzigingen aan je toestemmingen, profiel en account worden vastgelegd in een beveiligingslogboek zonder de inhoud van je gegevens. Technische logboeken bevatten geen persoonsgegevens.",
    ],
    [
      "Bewaren en verwijderen",
      "Je kunt in Account je gegevens downloaden en je account laten verwijderen. Wij verwijderen je account en gegevens binnen 30 dagen. Beveiligingslogboeken worden bewaard volgens [bewaartermijn — in te vullen na juridisch advies].",
    ],
    [
      "Delen",
      "Wij verkopen je gegevens niet. Wij gebruiken in deze fase geen AI-aanbieders. Hosting vindt plaats in de Europese Unie bij [hostingpartij — in te vullen].",
    ],
    [
      "Je rechten",
      "Je hebt recht op inzage, correctie, verwijdering, overdraagbaarheid en bezwaar. Je kunt een klacht indienen bij de Autoriteit Persoonsgegevens.",
    ],
  ],
};

const en = {
  title: "Privacy notice",
  sections: [
    [
      "Who we are",
      "MarocAssist is an independent service that helps with Moroccan consular procedures. We are not affiliated with the Moroccan government or any consulate. Controller: [name and contact details — to be completed by the owner].",
    ],
    [
      "What we process",
      "Your email address and password are managed by our sign-in service; MarocAssist itself does not store your email address. We keep: an optional display name, your consulate, your language, your consents, your deletion request and the list of paired browser extensions. We do not ask for your date of birth, nationality or document numbers.",
    ],
    [
      "Why",
      "To provide the service (performance of the contract) and, only if you choose so, to email you about new features (consent, which you can withdraw at any time in Settings).",
    ],
    [
      "Security and logs",
      "Changes to your consents, profile and account are recorded in a security log without the content of your data. Technical logs contain no personal data.",
    ],
    [
      "Retention and deletion",
      "In Account you can download your data and have your account deleted. We delete your account and data within 30 days. Security logs are kept according to [retention period — to be completed after legal advice].",
    ],
    [
      "Sharing",
      "We do not sell your data. In this phase we use no AI providers. Hosting takes place in the European Union with [hosting provider — to be completed].",
    ],
    [
      "Your rights",
      "You have the right of access, rectification, erasure, portability and objection. You can lodge a complaint with the Dutch Data Protection Authority (Autoriteit Persoonsgegevens).",
    ],
  ],
};

export default async function PrivacyPage() {
  const locale = resolveLocale((await cookies()).get(LOCALE_COOKIE)?.value);
  const text = locale === "nl" ? nl : en;
  return (
    <main className="shell-main prose">
      <p>
        <Link href="/">{t(locale, "appName")}</Link>
      </p>
      <h1>{text.title}</h1>
      <p role="note" data-testid="privacy-draft">
        <strong>{t(locale, "draftNotice")}</strong> Version {VERSION}.
      </p>
      {text.sections.map(([heading, body]) => (
        <section key={heading}>
          <h2>{heading}</h2>
          <p>{body}</p>
        </section>
      ))}
    </main>
  );
}
