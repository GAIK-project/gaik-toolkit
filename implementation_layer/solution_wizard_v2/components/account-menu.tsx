"use client";

import Link from "next/link";
import { useEffect, useId, useRef, type KeyboardEvent, type ReactNode } from "react";
import { Icon } from "@/components/icons";
import { ACCOUNT_MENU_ITEM } from "@/components/menu-item";
import { MENU_ITEMS, nextMenuIndex } from "@/lib/menu-keys";

export type AccountMenuLabels = {
  /** The user area's name, and the start of the button's: "Käyttäjä: a@b.fi". */
  account: string;
  privacy: string;
  help: string;
  demos: string;
};

const GAP = 4;
/** The menu is at least this wide, also over the rail's small button. */
const MIN_WIDTH = 208;
/** Where the menu stands until the script has measured its button: over the
 *  sidebar's foot, which is in the window's bottom left corner in the column,
 *  the rail and the drawer alike. */
const UNPLACED = { left: "0.5rem", bottom: "3.5rem" } as const;

/**
 * Who is signed in, as one row at the sidebar's foot, and what belongs to the
 * account behind it: the language, the help page, the privacy notice, the way
 * back to the GAIK demos and signing out. The
 * list is a native popover, like a session row's menu: it is drawn above the
 * sidebar, and Esc, a press elsewhere and the return of focus to the row come
 * with it. The language choice and the sign-out form come from the server as
 * they are.
 */
export function AccountMenu({
  email,
  variant,
  labels,
  demoUrl,
  localeSwitcher,
  signOut,
}: {
  email: string;
  /** "row": the initial, the e-mail and a chevron; "rail": the initial alone. */
  variant: "row" | "rail";
  labels: AccountMenuLabels;
  /** The GAIK demos; null leaves the link out. */
  demoUrl: string | null;
  localeSwitcher: ReactNode;
  signOut: ReactNode;
}) {
  const button = useRef<HTMLButtonElement>(null);
  const menu = useRef<HTMLDivElement>(null);
  const menuId = useId();

  useEffect(() => {
    const list = menu.current;
    const opener = button.current;
    if (!list || !opener) return;
    const close = () => {
      if (list.matches(":popover-open")) list.hidePopover();
    };
    // Placed from the button as it opens: above it, from its left edge, and
    // as wide as the row it opens from.
    const place = (event: Event) => {
      if ((event as ToggleEvent).newState !== "open") return;
      const at = opener.getBoundingClientRect();
      list.style.left = `${Math.max(8, at.left)}px`;
      list.style.bottom = `${window.innerHeight - at.top + GAP}px`;
      list.style.minWidth = `${Math.max(MIN_WIDTH, Math.round(at.width))}px`;
    };
    // Open, the first item has the focus, so the arrow keys work at once.
    // The window changing under the menu closes it.
    const follow = (event: Event) => {
      const open = (event as ToggleEvent).newState === "open";
      window[open ? "addEventListener" : "removeEventListener"]("resize", close);
      if (open) list.querySelector<HTMLElement>(MENU_ITEMS)?.focus();
    };
    list.addEventListener("beforetoggle", place);
    list.addEventListener("toggle", follow);
    return () => {
      list.removeEventListener("beforetoggle", place);
      list.removeEventListener("toggle", follow);
      window.removeEventListener("resize", close);
    };
  }, []);

  const moveFocus = (event: KeyboardEvent<HTMLDivElement>) => {
    const items = Array.from(event.currentTarget.querySelectorAll<HTMLElement>(MENU_ITEMS));
    const next = nextMenuIndex(
      event.key,
      items.findIndex((item) => item === document.activeElement),
      items.length,
    );
    if (next === null) return;
    event.preventDefault();
    items[next].focus();
  };
  // The arrows open the menu from its button, as they do in a menu bar.
  const openByArrow = (event: KeyboardEvent<HTMLButtonElement>) => {
    if (event.key !== "ArrowUp" && event.key !== "ArrowDown") return;
    if (menu.current?.matches(":popover-open")) return;
    event.preventDefault();
    // A press of the button itself, so the menu knows which button opened it.
    event.currentTarget.click();
  };

  const initial = email.trim().charAt(0).toUpperCase() || "?";
  const name = `${labels.account}: ${email}`;

  return (
    <>
      {variant === "row" ? (
        <button
          ref={button}
          type="button"
          popoverTarget={menuId}
          data-testid="account-menu"
          aria-label={name}
          title={email}
          onKeyDown={openByArrow}
          className="flex w-full items-center gap-2 rounded-lg px-1.5 py-1.5 text-left transition-colors duration-150 hover:bg-surface-muted active:bg-surface-muted max-lg:min-h-11 pointer-coarse:min-h-11"
        >
          <span
            aria-hidden
            className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-brand-soft text-[11px] font-semibold text-brand-text"
          >
            {initial}
          </span>
          <span data-testid="user-email" className="min-w-0 flex-1 truncate text-[13px] text-text">
            {email}
          </span>
          {/* The menu opens upward. */}
          <Icon name="chevronDown" size={14} className="rotate-180 text-text-muted" />
        </button>
      ) : (
        <button
          ref={button}
          type="button"
          popoverTarget={menuId}
          data-testid="account-menu"
          aria-label={name}
          title={email}
          onKeyDown={openByArrow}
          className="flex h-7 w-7 items-center justify-center rounded-full bg-brand-soft text-[11px] font-semibold text-brand-text transition-transform duration-150 active:scale-95"
        >
          {initial}
        </button>
      )}
      <div
        ref={menu}
        id={menuId}
        popover="auto"
        data-testid="account-menu-items"
        style={UNPLACED}
        onKeyDown={moveFocus}
        className="row-menu max-w-[calc(100vw-1rem)]"
      >
        {/* The rail shows the initial alone: the menu says whose it is. */}
        {variant === "rail" && (
          <p title={email} className="max-w-64 truncate px-2.5 pb-1.5 pt-1 text-xs text-text-muted">
            {email}
          </p>
        )}
        {localeSwitcher}
        <div role="separator" className="mx-1 my-1 h-px bg-border" />
        <Link href="/help" data-testid="help-link" className={ACCOUNT_MENU_ITEM}>
          <Icon name="info" size={14} />
          {labels.help}
        </Link>
        <Link href="/privacy" data-testid="privacy-link" className={ACCOUNT_MENU_ITEM}>
          <Icon name="shieldCheck" size={14} />
          {labels.privacy}
        </Link>
        {demoUrl && (
          <a href={demoUrl} data-testid="gaik-demos-link" className={ACCOUNT_MENU_ITEM}>
            <Icon name="externalLink" size={14} />
            {labels.demos}
          </a>
        )}
        {signOut}
      </div>
    </>
  );
}
