import Image from "next/image";
import { setLocale } from "@/app/locale-actions";
import { Icon } from "@/components/icons";
import { ACCOUNT_MENU_ITEM } from "@/components/menu-item";
import { LOCALES, type Locale } from "@/lib/i18n";

/** Circle flags (HatScripts circle-flags, MIT) in public/flags/. */
const FLAG: Record<Locale, string> = { fi: "fi", en: "gb" };
/** Each language in its own name, as language pickers usually show them. */
const LANGUAGE: Record<Locale, string> = { fi: "Suomi", en: "English" };

// Locale switch fi/en. One form, two submit buttons; the clicked button's
// name/value goes to the server action. Works without client JS.
export function LocaleSwitcher({
  locale,
  variant = "switch",
  label,
}: {
  locale: Locale;
  /** "switch": a small two-part switch for a page's corner; "menu": the two
   *  languages as rows of the sidebar's account menu. */
  variant?: "switch" | "menu";
  /** The choice's name in the menu: "Kieli". */
  label?: string;
}) {
  if (variant === "menu") {
    return (
      <form action={setLocale}>
        <div role="group" aria-label={label}>
          {LOCALES.map((l) => (
            <button
              key={l}
              name="locale"
              value={l}
              lang={l}
              aria-current={locale === l ? "true" : undefined}
              className={`${ACCOUNT_MENU_ITEM} ${locale === l ? "font-medium text-text" : ""}`}
            >
              <Image
                src={`/flags/${FLAG[l]}.svg`}
                alt=""
                width={16}
                height={16}
                unoptimized
                className="h-4 w-4 shrink-0 rounded-full"
              />
              {LANGUAGE[l]}
              {locale === l && <Icon name="check" size={14} className="ml-auto text-brand" />}
            </button>
          ))}
        </div>
      </form>
    );
  }
  return (
    <form
      action={setLocale}
      className="inline-flex items-center gap-0.5 rounded-md border border-border bg-surface-muted p-0.5 text-xs font-medium"
    >
      {LOCALES.map((l) => (
        <button
          key={l}
          name="locale"
          value={l}
          title={LANGUAGE[l]}
          aria-current={locale === l ? "true" : undefined}
          className={`inline-flex items-center gap-1.5 rounded px-2 py-0.5 transition-colors pointer-coarse:py-2.5 ${
            locale === l ? "bg-surface text-text shadow-xs" : "text-text-muted hover:text-text"
          }`}
        >
          <Image
            src={`/flags/${FLAG[l]}.svg`}
            alt=""
            width={14}
            height={14}
            unoptimized
            className={`h-3.5 w-3.5 rounded-full ${locale === l ? "" : "opacity-70"}`}
          />
          {/* Flags alone on a phone; the code stays the button's name. */}
          <span className="max-sm:sr-only">{l.toUpperCase()}</span>
        </button>
      ))}
    </form>
  );
}
