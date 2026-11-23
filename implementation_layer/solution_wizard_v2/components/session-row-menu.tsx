"use client";

import { useEffect, useRef, type KeyboardEvent } from "react";
import { Icon } from "@/components/icons";
import { MENU_ITEM as ITEM } from "@/components/menu-item";
import { fillTemplate } from "@/lib/chat-template";
import { MENU_ITEMS, nextMenuIndex } from "@/lib/menu-keys";

export type RowMenuLabels = {
  /** The button's name; "{title}" is the session's name. */
  actions: string;
  rename: string;
  /** "Lataa ZIP": the short text of the download, and its full name. */
  exportShort: string;
  exportOpen: string;
  remove: string;
};

const GAP = 4;
/** Below this much room under the button the menu opens upward. */
const ROOM_BELOW = 152;

/**
 * A session row's actions behind one button: rename, download, delete.
 * The list is a native popover, so it is drawn above the sidebar's scroll box,
 * and Esc, a press elsewhere and the return of focus to the button come with
 * it. It holds three plain controls in reading order: Tab moves between them,
 * and so do the arrow keys, Home and End.
 */
export function SessionRowMenu({
  sessionId,
  title,
  labels,
  onRename,
  onDelete,
}: {
  sessionId: string;
  title: string;
  labels: RowMenuLabels;
  onRename: () => void;
  onDelete: () => void;
}) {
  const button = useRef<HTMLButtonElement>(null);
  const menu = useRef<HTMLDivElement>(null);
  const menuId = `session-menu-${sessionId}`;

  useEffect(() => {
    const list = menu.current;
    const opener = button.current;
    if (!list || !opener) return;
    const close = () => {
      if (list.matches(":popover-open")) list.hidePopover();
    };
    // Placed from the button as it opens: under it and in line with its right
    // edge, above it when the window has no room below.
    const place = (event: Event) => {
      if ((event as ToggleEvent).newState !== "open") return;
      const at = opener.getBoundingClientRect();
      const below = window.innerHeight - at.bottom;
      list.style.right = `${Math.max(8, window.innerWidth - at.right)}px`;
      if (below < ROOM_BELOW && at.top > below) {
        list.style.top = "auto";
        list.style.bottom = `${window.innerHeight - at.top + GAP}px`;
      } else {
        list.style.top = `${at.bottom + GAP}px`;
        list.style.bottom = "auto";
      }
    };
    // The menu stands where its button was; when the list scrolls or the
    // window changes under it, it closes instead of pointing at another row.
    // Only a scroll that moves the button counts: the chat's log scrolls with
    // every word of a reply, and the menu must stay open through that.
    const scrolled = (event: Event) => {
      if (event.target instanceof Node && event.target.contains(opener)) close();
    };
    const follow = (event: Event) => {
      const open = (event as ToggleEvent).newState === "open";
      const method = open ? "addEventListener" : "removeEventListener";
      window[method]("resize", close);
      document[method]("scroll", scrolled, true);
      // Open, the first item has the focus, so the arrow keys work at once.
      if (open) list.querySelector<HTMLElement>(MENU_ITEMS)?.focus();
    };
    list.addEventListener("beforetoggle", place);
    list.addEventListener("toggle", follow);
    return () => {
      list.removeEventListener("beforetoggle", place);
      list.removeEventListener("toggle", follow);
      window.removeEventListener("resize", close);
      document.removeEventListener("scroll", scrolled, true);
    };
  }, []);

  const hide = () => menu.current?.hidePopover();
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
  const name = fillTemplate(labels.actions, { title });

  return (
    <>
      <button
        ref={button}
        type="button"
        popoverTarget={menuId}
        data-testid="session-actions"
        aria-label={name}
        title={name}
        className="session-row-actions absolute right-1 top-1 flex h-7 w-7 items-center justify-center rounded-md text-text-muted transition-[background-color,color,opacity] duration-150 hover:bg-surface-muted hover:text-text pointer-coarse:h-9 pointer-coarse:w-9"
      >
        <Icon name="ellipsis" size={16} />
      </button>
      <div ref={menu} id={menuId} popover="auto" onKeyDown={moveFocus} className="row-menu">
        <button
          type="button"
          data-testid="rename-session"
          onClick={() => {
            hide();
            onRename();
          }}
          className={ITEM}
        >
          <Icon name="pencil" size={14} />
          {labels.rename}
        </button>
        <a
          href={`/api/sessions/${sessionId}/export`}
          data-testid="export-session"
          aria-label={`${labels.exportOpen}: ${title}`}
          onClick={hide}
          className={ITEM}
        >
          <Icon name="download" size={14} />
          {labels.exportShort}
        </a>
        <button
          type="button"
          data-testid="delete-session-open"
          aria-label={`${labels.remove}: ${title}`}
          onClick={() => {
            hide();
            onDelete();
          }}
          className={`${ITEM} hover:bg-danger-bg hover:text-danger-text`}
        >
          <Icon name="trash2" size={14} />
          {labels.remove}
        </button>
      </div>
    </>
  );
}
