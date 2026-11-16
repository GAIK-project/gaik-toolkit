import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { signOut } from "@/app/login/actions";
import { Icon } from "@/components/icons";
import { LocaleSwitcher } from "@/components/locale-switcher";
import { ACCOUNT_MENU_ITEM } from "@/components/menu-item";
import { Sidebar } from "@/components/sidebar";
import type { SessionRow } from "@/components/sidebar-sessions";
import { getCurrentUser } from "@/lib/current-user";
import { gaikDemoUrl } from "@/lib/gaik-demo";
import { getI18n } from "@/lib/i18n";
import { logger } from "@/lib/logger";
import { sessionRows } from "@/lib/session-rows";
import { SIDEBAR_COOKIE } from "@/lib/shell";
import { listSessions } from "@/lib/sessions";

/**
 * The shell of every signed-in page: the sidebar with the user's sessions
 * beside the page. Access is decided in proxy.ts and again in each page and
 * action; the layout only needs to know whose sessions to list.
 */
export default async function AppLayout({ children }: { children: React.ReactNode }) {
  const user = await getCurrentUser();
  if (!user) redirect("/login");
  const { locale, t } = await getI18n();

  // A list that cannot be read must not take the open session down with it.
  let rows: SessionRow[] = [];
  let loadFailed = false;
  try {
    rows = sessionRows(await listSessions(user.email), new Date(), locale, t);
  } catch (err) {
    loadFailed = true;
    logger.error({ err }, "session.list failed");
  }
  const collapsed = (await cookies()).get(SIDEBAR_COOKIE)?.value === "collapsed";

  return (
    // `surface` under everything but the sidebar: while the sidebar folds, the
    // page glides over its own colour.
    <div className="flex h-dvh overflow-hidden bg-surface">
      <Sidebar
        rows={rows}
        email={user.email}
        defaultCollapsed={collapsed}
        loadFailed={loadFailed}
        demoUrl={gaikDemoUrl()}
        localeSwitcher={<LocaleSwitcher locale={locale} variant="menu" label={t.languageLabel} />}
        signOut={
          <form action={signOut}>
            <button type="submit" className={ACCOUNT_MENU_ITEM}>
              <Icon name="logOut" size={14} />
              {t.signOut}
            </button>
          </form>
        }
        labels={{
          sidebar: t.sidebarLabel,
          newSession: t.newSession,
          collapse: t.sidebarCollapse,
          expand: t.sidebarExpand,
          close: t.sidebarClose,
          account: t.accountLabel,
          privacy: t.privacyLink,
          help: t.helpLink,
          demos: t.gaikDemosLink,
          sessions: {
            nav: t.sessionsNav,
            days: {
              today: t.dayToday,
              yesterday: t.dayYesterday,
              week: t.dayThisWeek,
              earlier: t.dayEarlier,
            },
            search: t.searchSessions,
            searchPlaceholder: t.searchSessionsPlaceholder,
            noResults: t.noSearchResults,
            clearSearch: t.clearSearch,
            empty: t.noSessions,
            loadFailed: t.sessionsLoadFailed,
            done: t.done,
            waiting: t.gates.pending,
            rejected: t.gates.rejected,
            updated: t.updated,
            nameLabel: t.sessionNameLabel,
            renameFailed: t.renameFailed,
            menu: {
              actions: t.sessionActions,
              rename: t.renameSession,
              exportShort: t.exportSessionShort,
              exportOpen: t.exportSessionOpen,
              remove: t.deleteSessionOpen,
            },
            remove: {
              open: t.deleteSessionOpen,
              title: t.deleteSessionTitle,
              body: t.deleteSessionBody,
              confirmLabel: t.deleteSessionConfirmLabel,
              confirm: t.deleteSessionConfirm,
              cancel: t.deleteSessionCancel,
              mismatch: t.deleteSessionMismatch,
              busy: t.deleteSessionBusy,
              protected: t.deleteSessionProtected,
              failed: t.deleteSessionFailed,
            },
          },
        }}
      />
      <div data-shell-main className="relative flex min-w-0 flex-1 flex-col bg-surface">
        {children}
      </div>
    </div>
  );
}
