/**
 * Which element scrolls a given one up and down, found from the page as it
 * is: the element's ancestors and their computed overflow, not a class name
 * or a known place in the layout. A drag that scrolls its list while the
 * pointer is held near an edge uses this, so it goes on working when the
 * list is moved to another container or the page itself becomes the scroller.
 */

/** What is read of an element; an `HTMLElement` has all of it. */
export type ScrollBox = {
  parentElement: ScrollBox | null;
  scrollTop: number;
  scrollHeight: number;
  clientHeight: number;
};

type OverflowOf = (el: ScrollBox) => string;

const domOverflow: OverflowOf = (el) => getComputedStyle(el as unknown as Element).overflowY;

function scrollsItsContent(overflowY: string): boolean {
  return overflowY === "auto" || overflowY === "scroll" || overflowY === "overlay";
}

function hasRoom(el: ScrollBox, direction: -1 | 1): boolean {
  // A pixel of slack: a scaled page leaves fractions that never close.
  return direction < 0 ? el.scrollTop > 0 : el.scrollTop + el.clientHeight < el.scrollHeight - 1;
}

/**
 * The nearest ancestor that clips `el` and scrolls it: what the element is
 * seen through. Null when no ancestor does, so the window is the view.
 */
export function scrollClip<T extends ScrollBox>(el: T, overflowOf: OverflowOf = domOverflow): T | null {
  for (let node = el.parentElement; node; node = node.parentElement) {
    if (scrollsItsContent(overflowOf(node))) return node as T;
  }
  return null;
}

/**
 * The element to scroll to move `el` in `direction` (-1 up, 1 down): the
 * nearest scrolling ancestor that still has somewhere to go that way, then
 * `page` (the document's scrolling element) if it has. A container that is
 * at its end hands over to the one outside it; null when nothing can move.
 */
export function scrollTarget<T extends ScrollBox>(
  el: T,
  direction: -1 | 1,
  page: T | null,
  overflowOf: OverflowOf = domOverflow,
): T | null {
  for (let node = el.parentElement; node; node = node.parentElement) {
    if (node === page) break;
    if (scrollsItsContent(overflowOf(node)) && hasRoom(node, direction)) return node as T;
  }
  return page && hasRoom(page, direction) ? page : null;
}
