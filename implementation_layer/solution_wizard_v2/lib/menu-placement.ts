/** The space between the card and the menu, in px (mt-2 / mb-2). */
export const MENU_GAP = 8;

export type MenuPlacement = { below: boolean; maxHeight: number | null };

/**
 * Which side of the message card a choice's menu opens on (components/chat-start).
 * Under the card where the window has room for the whole menu, as on the start
 * view, where the field stands mid-page and a menu over it hid the page's
 * heading; over it where only that side has room, as in a chat whose field is
 * at the bottom of the window; where neither has, the side with more, and the
 * menu keeps to the window and scrolls (a short window, a phone's keyboard).
 */
export function menuPlacement(
  card: { top: number; bottom: number },
  menuHeight: number,
  windowHeight: number,
): MenuPlacement {
  const room = { below: windowHeight - card.bottom - MENU_GAP, above: card.top - MENU_GAP };
  const below = room.below >= menuHeight ? true : room.above >= menuHeight ? false : room.below > room.above;
  const fits = below ? room.below : room.above;
  return { below, maxHeight: fits < menuHeight ? Math.max(fits - MENU_GAP, 0) : null };
}
