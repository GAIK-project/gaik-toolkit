import { login, signup } from "./actions";
import { DEV_AUTH, DEV_CREDENTIALS } from "@/lib/auth";
import { getI18n } from "@/lib/i18n";
import { LocaleSwitcher } from "@/components/locale-switcher";

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string; message?: string }>;
}) {
  const params = await searchParams;
  const { locale, t } = await getI18n();

  return (
    <main
      id="main-content"
      className="relative min-h-screen flex items-center justify-center bg-app p-4"
    >
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(60%_50%_at_50%_0%,rgba(13,148,136,0.07),transparent)]" />

      <div className="relative w-full max-w-sm bg-surface rounded-xl border border-border shadow-md p-8">
        <div className="flex items-start justify-between">
          <h1 className="text-2xl font-semibold tracking-tight text-text">
            {t.appName}
          </h1>
          <LocaleSwitcher locale={locale} />
        </div>
        <p className="text-sm leading-relaxed text-text-secondary mt-1.5 mb-6">
          {t.loginSubtitle}
        </p>

        {DEV_AUTH && (
          <p className="mb-4 text-xs text-warning-text bg-warning-bg border border-warning-border rounded-md px-3 py-2">
            {t.devHintPre} <strong>{DEV_CREDENTIALS.email}</strong> /{" "}
            <strong>{DEV_CREDENTIALS.password}</strong> {t.devHintPost}
          </p>
        )}

        {params.error && (
          <p
            role="alert"
            className="mb-4 text-sm text-danger-text bg-danger-bg border border-danger-border rounded-md px-3 py-2"
          >
            {params.error}
          </p>
        )}
        {params.message && (
          <p
            role="status"
            aria-live="polite"
            className="mb-4 text-sm text-success-text bg-success-bg border border-success-border rounded-md px-3 py-2"
          >
            {params.message}
          </p>
        )}

        <form className="space-y-4">
          <div>
            <label className="field-label" htmlFor="email">
              {t.email}
            </label>
            <input
              id="email"
              name="email"
              type="email"
              required
              autoComplete="email"
              defaultValue={DEV_AUTH ? DEV_CREDENTIALS.email : undefined}
              className="input-field"
            />
          </div>
          <div>
            <label className="field-label" htmlFor="password">
              {t.password}
            </label>
            <input
              id="password"
              name="password"
              type="password"
              required
              autoComplete="current-password"
              defaultValue={DEV_AUTH ? DEV_CREDENTIALS.password : undefined}
              className="input-field"
            />
          </div>
          <div className="flex gap-2 pt-2">
            <button formAction={login} type="submit" className="btn-brand flex-1">
              {t.login}
            </button>
            <button formAction={signup} type="submit" className="btn-secondary flex-1">
              {t.signup}
            </button>
          </div>
        </form>
      </div>
    </main>
  );
}
