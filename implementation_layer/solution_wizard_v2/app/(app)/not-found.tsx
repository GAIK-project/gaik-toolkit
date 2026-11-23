import Link from "next/link";
import { Icon } from "@/components/icons";
import { getI18n } from "@/lib/i18n";

/**
 * A session that is not there, or is someone else's: said inside the shell, so
 * the sidebar with the user's own sessions stays beside it.
 */
export default async function SessionNotFound() {
  const { t } = await getI18n();
  return (
    <main
      id="main-content"
      className="flex min-h-0 flex-1 flex-col items-center justify-center gap-4 overflow-y-auto bg-surface px-4 pb-[10dvh] text-center"
    >
      <h1 className="text-lg font-semibold tracking-tight text-text">{t.sessionNotFound}</h1>
      <Link href="/" className="btn-secondary">
        <Icon name="squarePen" size={16} />
        {t.newSession}
      </Link>
    </main>
  );
}
