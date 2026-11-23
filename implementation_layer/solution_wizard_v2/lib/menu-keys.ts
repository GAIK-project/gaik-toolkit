/**
 * Which item of a menu a key moves the focus to: the arrows step and wrap
 * around, Home and End go to the ends. `current` is the focused item's index,
 * -1 when the focus is not on an item yet. Null for a key that is not the
 * menu's to handle, and for a menu without items.
 */
export function nextMenuIndex(key: string, current: number, count: number): number | null {
  if (count <= 0) return null;
  switch (key) {
    case "ArrowDown":
      return current < 0 || current >= count - 1 ? 0 : current + 1;
    case "ArrowUp":
      return current <= 0 ? count - 1 : current - 1;
    case "Home":
      return 0;
    case "End":
      return count - 1;
    default:
      return null;
  }
}

/** What the keys move between: the links and buttons of a menu, in reading order. */
export const MENU_ITEMS = "a[href], button:not([disabled])";
