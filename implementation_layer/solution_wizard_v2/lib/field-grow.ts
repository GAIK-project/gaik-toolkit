// The message field grows with its text. The height it should have is
// measured with the height set to "auto"; the change itself starts from the
// height the field had, so a CSS transition on height (textarea[data-autogrow]
// in globals.css) carries it there instead of the box jumping a line at a time.

type GrowingField = Pick<HTMLTextAreaElement, "offsetHeight" | "scrollHeight"> & {
  style: Pick<CSSStyleDeclaration, "height" | "overflowY">;
};

/**
 * Sets the field's height to fit its text, at most `max` px. `borders` is the
 * sum of the top and bottom border widths: the field is border-box and
 * scrollHeight leaves them out.
 */
export function fitField(el: GrowingField, max: number, borders: (el: GrowingField) => number): void {
  const from = el.offsetHeight;
  el.style.height = "auto";
  const to = Math.min(el.scrollHeight + borders(el), max);
  // Below the cap everything is in view, so there is nothing to scroll: without
  // this a scrollbar flashed beside the text while the box was still growing.
  el.style.overflowY = to < max ? "hidden" : "";
  if (from > 0 && from !== to) {
    // Back to where it was, read once so the browser takes that as the
    // starting point, then on to the new height.
    el.style.height = `${from}px`;
    void el.offsetHeight;
  }
  el.style.height = `${to}px`;
}
