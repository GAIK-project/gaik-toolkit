import Link from "next/link";
import { getI18n } from "@/lib/i18n";
import { privacyNotice } from "@/lib/privacy-notice";
import { LocaleSwitcher } from "@/components/locale-switcher";

export default async function PrivacyPage() {
  const { locale } = await getI18n();
  const notice = privacyNotice(locale);

  return (
    <main id="main-content" className="min-h-screen bg-app p-6">
      <article className="mx-auto max-w-2xl space-y-5 rounded-xl border border-border bg-surface p-6 shadow-xs">
        <div className="flex items-start justify-between gap-3">
          <h1 className="text-xl font-semibold tracking-tight text-text">{notice.title}</h1>
          <LocaleSwitcher locale={locale} />
        </div>
        {notice.draftNote && (
          <p
            data-testid="privacy-draft-note"
            className="rounded-lg border border-border bg-app p-3 text-sm text-text-secondary"
          >
            {notice.draftNote}
          </p>
        )}
        {notice.sections.map((section) => (
          <section key={section.heading}>
            <h2 className="mb-1 text-sm font-semibold text-text-strong">{section.heading}</h2>
            {section.text && (
              <p className="text-sm leading-relaxed text-text-secondary">{section.text}</p>
            )}
            {section.items && (
              <ul className="list-disc space-y-1 pl-5 text-sm leading-relaxed text-text-secondary">
                {section.items.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            )}
          </section>
        ))}
        <Link href="/" className="inline-block text-sm font-medium text-brand-text hover:underline">
          {notice.back}
        </Link>
      </article>
    </main>
  );
}
