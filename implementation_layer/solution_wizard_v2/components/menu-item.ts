// The rows of the sidebar's menus. A plain module, so the layout (server) and
// the menus (browser) give their rows the same look.

/** A row of a menu: an icon and a short text. */
export const MENU_ITEM =
  "flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-left text-[13px] text-text-secondary transition-colors duration-150 hover:bg-surface-muted hover:text-text pointer-coarse:py-2.5";

/** A row of the account menu: tall enough for a finger in the phone drawer. */
export const ACCOUNT_MENU_ITEM = `${MENU_ITEM} max-lg:min-h-11 pointer-coarse:min-h-11`;
