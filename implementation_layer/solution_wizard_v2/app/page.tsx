import Link from "next/link";
import { getCurrentUser } from "@/lib/current-user";
import { getI18n, DATE_LOCALE, type Dict, type Locale } from "@/lib/i18n";
import { LocaleSwitcher } from "@/components/locale-switcher";
import { signOut } from "./login/actions";
import { startSession } from "./actions";
import { listSessions, PHASE_COUNT, type WizardSession } from "@/lib/mock-sessions";

function StatusBadge({ session, t }: { session: WizardSession; t: Dict }) {
  if (session.status === "done") {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-[11px] font-medium bg-success-bg border-success-border text-success-text">
        <span className="h-1.5 w-1.5 rounded-full bg-current" />
        {t.done}
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-[11px] font-medium bg-info-bg border-info-border text-info-text">
      <span className="h-1.5 w-1.5 rounded-full bg-current" />
      {t.step} {session.step}/{PHASE_COUNT}
    </span>
  );
}

function formatDate(iso: string, locale: Locale): string {
  return new Date(iso).toLocaleDateString(DATE_LOCALE[locale], {
    day: "numeric",
    month: "numeric",
    year: "numeric",
  });
}

export default async function Home() {
  const user = await getCurrentUser();
  const { locale, t } = await getI18n();
  const sessions = user ? listSessions(user.email) : [];

  return (
    <div className="min-h-screen flex flex-col bg-app">
      <header className="h-[52px] shrink-0 px-5 flex items-center justify-between bg-surface/80 backdrop-blur-sm border-b border-border sticky top-0 z-10">
        <span className="flex items-center gap-2 text-[15px] font-semibold tracking-tight text-text">
          <span className="h-6 w-6 rounded-md bg-brand shadow-xs flex items-center justify-center text-white text-[11px] font-bold">
            G
          </span>
          {t.appName}
        </span>
        <div className="flex items-center gap-4 text-sm text-text-secondary">
          <LocaleSwitcher locale={locale} />
          <span>{user?.email}</span>
          <span className="h-4 w-px bg-border" />
          <form action={signOut}>
            <button className="text-sm font-medium text-text-muted hover:text-danger-text transition-colors">
              {t.signOut}
            </button>
          </form>
        </div>
      </header>

      <main className="flex-1 max-w-3xl w-full mx-auto p-6 space-y-10">
        {/* Uuden session aloitus */}
        <section>
          <h1 className="text-lg font-semibold tracking-tight text-text mb-1">
            {t.sessionsTitle}
          </h1>
          <p className="text-sm leading-relaxed text-text-secondary mb-4">
            {t.sessionsIntro}
          </p>
          <form
            action={startSession}
            className="flex gap-2 bg-surface border border-border rounded-lg p-3 shadow-xs"
          >
            <input
              name="title"
              type="text"
              placeholder={t.newSessionPlaceholder}
              className="flex-1 rounded-md bg-surface border border-border-strong px-3 py-2 text-sm text-text placeholder:text-text-muted shadow-xs transition-colors hover:border-text-muted focus:outline-none focus:border-brand"
            />
            <button
              type="submit"
              className="shrink-0 inline-flex items-center justify-center gap-1.5 rounded-md bg-brand px-4 py-2 text-sm font-medium text-white shadow-xs transition-colors hover:bg-brand-hover active:bg-brand-active"
            >
              {t.startNew}
            </button>
          </form>
        </section>

        {/* Olemassa olevat sessiot */}
        <section>
          <h2 className="text-sm font-semibold text-text-strong mb-3">
            {t.previousSessions} ({sessions.length})
          </h2>
          {sessions.length === 0 ? (
            <p className="text-sm text-text-muted bg-surface border border-border rounded-lg p-6 text-center">
              {t.noSessions}
            </p>
          ) : (
            <ul className="space-y-2.5">
              {sessions.map((s) => (
                <li key={s.id}>
                  <Link
                    href={`/sessions/${s.id}`}
                    className="group block rounded-lg bg-surface border border-border p-4 shadow-xs transition-all duration-150 hover:border-brand-soft-border hover:shadow-md hover:-translate-y-0.5"
                  >
                    <div className="flex items-center justify-between gap-3">
                      <span className="text-sm font-semibold text-text-strong group-hover:text-brand-text transition-colors">
                        {s.title}
                      </span>
                      <StatusBadge session={s} t={t} />
                    </div>
                    <div className="mt-1.5 flex items-center gap-2 text-xs text-text-muted">
                      <span>{t.phases[s.step - 1]}</span>
                      <span className="h-1 w-1 rounded-full bg-border-strong" />
                      <span>
                        {s.versions.length} {t.blueprintVersions}
                      </span>
                      <span className="h-1 w-1 rounded-full bg-border-strong" />
                      <span>
                        {t.updated} {formatDate(s.updatedAt, locale)}
                      </span>
                    </div>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </section>
      </main>
    </div>
  );
}
