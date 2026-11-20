import type { CSSProperties } from "react";
import Image from "next/image";
import Link from "next/link";
import { login } from "./actions";
import { getI18n } from "@/lib/i18n";
import { gaikDemoUrl } from "@/lib/gaik-demo";
import { supabaseAuthEnabled, supabaseSignUpUrl } from "@/lib/supabase-auth";
import { Icon } from "@/components/icons";
import { LocaleSwitcher } from "@/components/locale-switcher";
import { getApiVersion } from "@/lib/wizard-api-client";
import { loginError, loginMessage } from "./notices";

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string; message?: string }>;
}) {
  const params = await searchParams;
  const { locale, t } = await getI18n();
  const webVersion = process.env.NEXT_PUBLIC_APP_VERSION || "dev";
  const apiVersion = (await getApiVersion()) ?? "unknown";
  const error = loginError(t, params.error);
  const message = loginMessage(t, params.message);
  const demoUrl = gaikDemoUrl();
  // The wizard has no sign-up of its own: with Supabase sign-in an account is
  // made in the demo, whose approval also opens the wizard.
  const signUpUrl = supabaseAuthEnabled() ? supabaseSignUpUrl() : null;

  return (
    <main
      id="main-content"
      className="relative flex min-h-screen items-center justify-center bg-surface p-4"
    >
      <div aria-hidden className="start-backdrop" style={{ "--at": "48%" } as CSSProperties} />
      {/* Most people come here from the GAIK demos: the way back is in the
          corner, outside the sign-in itself. */}
      {demoUrl && (
        <a
          href={demoUrl}
          data-testid="gaik-demos-link"
          className="absolute left-4 top-4 z-10 inline-flex min-h-11 items-center gap-1.5 rounded-md px-2 text-sm text-text-muted transition-colors duration-150 hover:text-text"
        >
          <Icon name="arrowLeft" size={14} />
          {t.gaikDemosLink}
        </a>
      )}
      <div className="relative z-10 w-full max-w-sm rounded-xl border border-border bg-surface p-8 shadow-md">
        <div className="absolute right-8 top-8">
          <LocaleSwitcher locale={locale} />
        </div>
        {/* The logo's own drawing names the organisation, the words under it
            the product: together they are the page's heading. */}
        <h1 className="flex flex-col items-start gap-4">
          <Image
            src="/gaik-wordmark.svg"
            alt="GAIK"
            width={882}
            height={303}
            priority
            unoptimized
            className="h-10 w-auto"
          />
          <span className="text-2xl font-semibold tracking-[-0.02em] text-text-strong">
            Solution Wizard
          </span>
        </h1>
        <p className="text-sm leading-relaxed text-text-secondary mt-1.5 mb-6">
          {t.loginSubtitle}
        </p>

        {error && (
          <p
            role="alert"
            className="mb-4 text-sm text-danger-text bg-danger-bg border border-danger-border rounded-md px-3 py-2"
          >
            {error}
          </p>
        )}
        {message && (
          <p
            role="status"
            aria-live="polite"
            className="mb-4 text-sm text-success-text bg-success-bg border border-success-border rounded-md px-3 py-2"
          >
            {message}
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
              suppressHydrationWarning
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
              className="input-field"
            />
          </div>
          <div className="flex gap-2 pt-2">
            <button formAction={login} type="submit" className="btn-brand flex-1">
              {t.login}
            </button>
          </div>
        </form>
        {signUpUrl && (
          <a
            href={signUpUrl}
            data-testid="sign-up-in-demo"
            className="mt-4 inline-block text-sm font-medium text-text-secondary underline hover:text-text"
          >
            {t.signUpInDemo}
          </a>
        )}
        <p className="mt-5 text-xs leading-relaxed text-text-muted" data-testid="login-ai-notice">
          {t.loginAiNotice}
        </p>
        <Link
          href="/privacy"
          data-testid="privacy-link"
          className="mt-2 inline-block text-xs font-medium text-text-muted underline hover:text-text"
        >
          {t.privacyLink}
        </Link>
      </div>

      <p className="absolute bottom-4 z-10 text-xs text-text-muted">
        web {webVersion} · api {apiVersion}
      </p>
    </main>
  );
}
