"use client";

import Image from "next/image";
import Link from "next/link";
import { useParams, usePathname } from "next/navigation";
import { useEffect, useId, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { AccountMenu } from "@/components/account-menu";
import { DeleteSessionDialog } from "@/components/delete-session-dialog";
import { Icon } from "@/components/icons";
import {
  SidebarSessions,
  type SessionListLabels,
  type SessionRow,
} from "@/components/sidebar-sessions";
import { GLIDE_EASING, mayAnimate } from "@/lib/motion";
import { FOCUS_START_EVENT, SIDEBAR_COOKIE } from "@/lib/shell";

export type SidebarLabels = {
  /** The sidebar's name as a landmark. */
  sidebar: string;
  newSession: string;
  collapse: string;
  expand: string;
  close: string;
  /** The user area's name, and the start of its button's: "Käyttäjä: a@b.fi". */
  account: string;
  privacy: string;
  help: string;
  demos: string;
  sessions: SessionListLabels;
};

const MARK = { src: "/gaik-mark.png", width: 133, height: 96 } as const;

/**
 * The shell's one client component: the sessions, a new session and the
 * signed-in user, beside every page of the wizard. On a desktop it is a column
 * that folds to a rail; below 1024 px it is a drawer over the page. Its foot is
 * one row that says who is signed in and opens the account's menu; the
 * language choice and the sign-out form in it come from the server as they are.
 */
export function Sidebar({
  rows,
  email,
  labels,
  defaultCollapsed,
  loadFailed,
  demoUrl,
  localeSwitcher,
  signOut,
}: {
  rows: SessionRow[];
  email: string;
  labels: SidebarLabels;
  /** From the cookie, so the server renders the width the viewer left it at. */
  defaultCollapsed: boolean;
  /** The sessions could not be read; the page beside the sidebar still works. */
  loadFailed: boolean;
  /** The GAIK demos the account menu links back to; null leaves the link out. */
  demoUrl: string | null;
  localeSwitcher: ReactNode;
  signOut: ReactNode;
}) {
  const panelId = useId();
  const pathname = usePathname();
  const activeId = useParams<{ id?: string }>().id ?? null;

  // --- The desktop column: full or folded to a rail.
  const [collapsed, setCollapsed] = useState(defaultCollapsed);
  const collapseButton = useRef<HTMLButtonElement>(null);
  const expandButton = useRef<HTMLButtonElement>(null);
  // The button that was pressed is gone with its side; its counterpart takes
  // the focus, as the chat dock's rail button does.
  const focusToggle = useRef(false);
  const fold = (next: boolean) => {
    focusToggle.current = true;
    setCollapsed(next);
    document.cookie = `${SIDEBAR_COOKIE}=${next ? "collapsed" : "expanded"}; path=/; max-age=31536000; samesite=lax`;
  };
  useEffect(() => {
    if (!focusToggle.current) return;
    focusToggle.current = false;
    (collapsed ? expandButton : collapseButton).current?.focus();
  }, [collapsed]);

  // The column takes its new width at once; what is seen is the page gliding
  // to its new place from where it stood, and the side that appeared fading
  // in. Only when the fold itself changed (a press), on the desktop layout,
  // and before the paint, so the new layout is never seen standing still.
  const aside = useRef<HTMLElement>(null);
  const panel = useRef<HTMLDivElement>(null);
  const rail = useRef<HTMLDivElement>(null);
  const lastWidth = useRef<number | null>(null);
  const wasCollapsed = useRef(collapsed);
  useLayoutEffect(() => {
    const column = aside.current;
    if (!column) return;
    const before = lastWidth.current;
    const width = column.offsetWidth;
    lastWidth.current = width;
    const folded = wasCollapsed.current !== collapsed;
    wasCollapsed.current = collapsed;
    if (!folded || before === null || before === width) return;
    if (!window.matchMedia("(min-width: 1024px)").matches) return;
    const page = document.querySelector("[data-shell-main]");
    if (!mayAnimate(page)) return;
    const timing: KeyframeAnimationOptions = { duration: 240, easing: GLIDE_EASING };
    page.animate([{ transform: `translateX(${before - width}px)` }, { transform: "none" }], timing);
    (collapsed ? rail : panel).current?.animate([{ opacity: 0 }, { opacity: 1 }], timing);
  }, [collapsed]);

  // --- The drawer below the desktop layout.
  const [drawerOpen, setDrawerOpen] = useState(false);
  const opener = useRef<HTMLButtonElement>(null);
  const closeButton = useRef<HTMLButtonElement>(null);
  const focusOpener = useRef(false);
  // Another page: the drawer has done its job.
  const [seenPath, setSeenPath] = useState(pathname);
  if (seenPath !== pathname) {
    setSeenPath(pathname);
    setDrawerOpen(false);
  }
  useEffect(() => {
    if (!drawerOpen) {
      if (focusOpener.current) opener.current?.focus();
      focusOpener.current = false;
      return;
    }
    // The page under the drawer is out of reach until the drawer closes.
    const page = document.querySelector("[data-shell-main]");
    page?.setAttribute("inert", "");
    closeButton.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape" || e.defaultPrevented) return;
      // A row's menu and the delete question close on their own Esc.
      if (document.querySelector("dialog[open], :popover-open")) return;
      focusOpener.current = true;
      setDrawerOpen(false);
    };
    // Widened to the desktop layout, the sidebar is a column again.
    const desktop = window.matchMedia("(min-width: 1024px)");
    const onDesktop = () => {
      if (desktop.matches) setDrawerOpen(false);
    };
    window.addEventListener("keydown", onKey);
    desktop.addEventListener("change", onDesktop);
    return () => {
      page?.removeAttribute("inert");
      window.removeEventListener("keydown", onKey);
      desktop.removeEventListener("change", onDesktop);
    };
  }, [drawerOpen]);
  const closeDrawer = () => {
    focusOpener.current = true;
    setDrawerOpen(false);
  };

  // --- The delete question, asked from a row's menu.
  const [deleting, setDeleting] = useState<{ id: string; title: string } | null>(null);
  const newSessionLink = useRef<HTMLAnchorElement>(null);
  // Once the list no longer has the session, there is nothing left to confirm.
  const asked = deleting && rows.some((row) => row.id === deleting.id) ? deleting : null;
  // The deleted row took its menu button with it, and the question leaves with
  // the row, in the same render, without a close event of its own. The focus
  // would be left on the page's body: "New session" takes it, unless the
  // start view the deleted open session leads to has taken it already.
  const deletedId = deleting && !asked ? deleting.id : null;
  useEffect(() => {
    if (!deletedId) return;
    requestAnimationFrame(() => {
      if (document.activeElement === document.body) newSessionLink.current?.focus();
    });
  }, [deletedId]);

  // "New session" on the start view itself leads nowhere new: the field there
  // takes the cursor instead.
  const startAgain = () => {
    if (pathname !== "/") return;
    setDrawerOpen(false);
    window.dispatchEvent(new Event(FOCUS_START_EVENT));
  };
  const accountLabels = {
    account: labels.account,
    privacy: labels.privacy,
    help: labels.help,
    demos: labels.demos,
  };

  return (
    <>
      <button
        ref={opener}
        type="button"
        data-testid="sidebar-open"
        aria-label={labels.expand}
        title={labels.expand}
        aria-expanded={drawerOpen}
        aria-controls={panelId}
        inert={drawerOpen}
        onClick={() => setDrawerOpen(true)}
        className="icon-btn fixed left-2 top-2 z-[32] lg:hidden"
      >
        <Icon name="panelLeftOpen" size={18} />
      </button>
      {/* Always there, so it can fade both ways; closed, it is out of reach. */}
      <div
        aria-hidden
        data-open={drawerOpen || undefined}
        onClick={closeDrawer}
        className="sidebar-scrim fixed inset-0 z-40 lg:hidden"
      />

      <aside
        ref={aside}
        aria-label={labels.sidebar}
        data-testid="sidebar"
        data-open={drawerOpen || undefined}
        data-collapsed={collapsed || undefined}
        // A link in the drawer leads to a page; the drawer steps aside for it,
        // also when the link is to the page already open.
        onClick={(e) => {
          if (drawerOpen && e.target instanceof Element && e.target.closest("a[href]")) {
            setDrawerOpen(false);
          }
        }}
        className={`sidebar flex shrink-0 flex-col border-r border-border bg-app max-lg:fixed max-lg:inset-y-0 max-lg:left-0 max-lg:z-40 max-lg:w-[min(20rem,86vw)] ${
          collapsed ? "lg:w-[3.25rem]" : "lg:w-[var(--width-sidebar)]"
        }`}
      >
        {/* Everything, in the full column and in the drawer. A folded column
            shows the rail below instead, on a desktop only. */}
        <div
          ref={panel}
          id={panelId}
          className={`min-h-0 flex-1 flex-col ${collapsed ? "flex lg:hidden" : "flex"}`}
        >
          <div className="flex h-12 shrink-0 items-center justify-between gap-2 pl-3.5 pr-2">
            <Link
              href="/"
              aria-label="GAIK Solution Wizard"
              className="flex min-w-0 items-center gap-2 rounded-md pointer-coarse:py-2"
            >
              <Image {...MARK} alt="" unoptimized priority className="h-[22px] w-auto" />
              {/* The start view says the name under its logo; there the mark
                  alone is the way home. */}
              {pathname !== "/" && (
                <span className="truncate text-[13.5px] font-semibold text-text">Solution Wizard</span>
              )}
            </Link>
            {!collapsed && (
              <button
                ref={collapseButton}
                type="button"
                data-testid="sidebar-toggle"
                aria-expanded
                aria-controls={panelId}
                aria-label={labels.collapse}
                title={labels.collapse}
                onClick={() => fold(true)}
                className="icon-btn max-lg:hidden"
              >
                <Icon name="panelLeftClose" size={18} />
              </button>
            )}
            <button
              ref={closeButton}
              type="button"
              aria-label={labels.close}
              title={labels.close}
              onClick={closeDrawer}
              className="icon-btn lg:hidden"
            >
              <Icon name="x" size={18} />
            </button>
          </div>

          <div className="shrink-0 px-2 pb-3 pt-1">
            <Link
              ref={newSessionLink}
              href="/"
              data-testid="new-session"
              onClick={startAgain}
              className="btn-secondary w-full justify-start px-3"
            >
              <Icon name="squarePen" size={16} />
              {labels.newSession}
            </Link>
          </div>

          <SidebarSessions
            rows={rows}
            activeId={activeId}
            loadFailed={loadFailed}
            labels={labels.sessions}
            onDelete={setDeleting}
          />

          <div
            role="group"
            aria-label={labels.account}
            className="shrink-0 border-t border-border p-2"
          >
            <AccountMenu
              email={email}
              variant="row"
              labels={accountLabels}
              demoUrl={demoUrl}
              localeSwitcher={localeSwitcher}
              signOut={signOut}
            />
          </div>
        </div>

        {collapsed && (
          <div ref={rail} className="hidden h-full flex-col items-center gap-1 py-2 lg:flex">
            <Link
              href="/"
              aria-label="GAIK Solution Wizard"
              title="GAIK Solution Wizard"
              className="flex h-8 w-9 items-center justify-center rounded-md"
            >
              <Image {...MARK} alt="" unoptimized priority className="h-[20px] w-auto" />
            </Link>
            <button
              ref={expandButton}
              type="button"
              data-testid="sidebar-toggle"
              aria-expanded={false}
              aria-controls={panelId}
              aria-label={labels.expand}
              title={labels.expand}
              onClick={() => fold(false)}
              className="icon-btn"
            >
              <Icon name="panelLeftOpen" size={18} />
            </button>
            <Link
              href="/"
              aria-label={labels.newSession}
              title={labels.newSession}
              onClick={startAgain}
              className="icon-btn"
            >
              <Icon name="squarePen" size={18} />
            </Link>
            <span className="flex-1" />
            <AccountMenu
              email={email}
              variant="rail"
              labels={accountLabels}
              demoUrl={demoUrl}
              localeSwitcher={localeSwitcher}
              signOut={signOut}
            />
          </div>
        )}
      </aside>

      {asked && (
        <DeleteSessionDialog
          key={asked.id}
          sessionId={asked.id}
          title={asked.title}
          current={asked.id === activeId}
          labels={labels.sessions.remove}
          // Cancel and Esc: the browser puts the focus back on the row's button.
          onClose={() => setDeleting(null)}
        />
      )}
    </>
  );
}
