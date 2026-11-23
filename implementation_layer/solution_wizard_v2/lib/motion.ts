/**
 * Movement the shell starts from script (the Web Animations API), at the
 * moment a layout changes: the sidebar folding, the first message's field
 * landing in its session, the chat docking beside the workspace. One curve for
 * all of them; the stylesheet has the same one as `--ease-glide`.
 */
export const GLIDE_EASING = "cubic-bezier(0.16, 1, 0.3, 1)";

/** False when the viewer asked for reduced motion, or the browser cannot animate. */
export function mayAnimate(el: Element | null | undefined): el is HTMLElement {
  return (
    el instanceof HTMLElement &&
    typeof el.animate === "function" &&
    !window.matchMedia("(prefers-reduced-motion: reduce)").matches
  );
}
