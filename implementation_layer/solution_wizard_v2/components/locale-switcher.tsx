import { setLocale } from "@/app/locale-actions";
import { LOCALES, type Locale } from "@/lib/i18n";

// Locale switch fi/en. One form, two submit buttons; the clicked button's
// name/value goes to the server action. Works without client JS.
export function LocaleSwitcher({ locale }: { locale: Locale }) {
  return (
    <form
      action={setLocale}
      className="inline-flex items-center gap-0.5 rounded-md bg-surface-muted border border-border p-0.5 text-xs font-medium"
    >
      {LOCALES.map((l) => (
        <button
          key={l}
          name="locale"
          value={l}
          aria-current={locale === l ? "true" : undefined}
          className={
            locale === l
              ? "px-2 py-0.5 rounded-md bg-surface text-text shadow-xs"
              : "px-2 py-0.5 rounded-md text-text-muted hover:text-text transition-colors"
          }
        >
          {l.toUpperCase()}
        </button>
      ))}
    </form>
  );
}
