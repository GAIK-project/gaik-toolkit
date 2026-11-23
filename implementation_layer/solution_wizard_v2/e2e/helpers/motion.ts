import type { Page } from "@playwright/test";

/**
 * What started to move on a page: the wizard's rule is that motion answers an
 * action and nothing animates on a page update (a chat reply re-reads the
 * whole page). `recordMotion` notes every CSS animation, every animation
 * started from script and every view transition, with the nearest test id of
 * the element it runs on; hover and focus transitions are not motion in that
 * sense and are left out. Call it before the page is loaded.
 */
export type Move = { kind: "css" | "script" | "view-transition"; name: string; at: string };

type Recorded = Window & { __moves?: Move[] };

export async function recordMotion(page: Page): Promise<void> {
  await page.addInitScript(() => {
    const moves: { kind: string; name: string; at: string }[] = [];
    (window as Window & { __moves?: unknown }).__moves = moves;
    // The test ids from the element outward: "session-card < sidebar".
    const where = (el: unknown) => {
      const ids: string[] = [];
      let at = el instanceof Element ? el.closest("[data-testid]") : null;
      while (at) {
        ids.push(at.getAttribute("data-testid") ?? "");
        at = at.parentElement?.closest("[data-testid]") ?? null;
      }
      return ids.join(" < ");
    };
    document.addEventListener(
      "animationstart",
      (e) => moves.push({ kind: "css", name: e.animationName, at: where(e.target) }),
      true,
    );
    const animate = Element.prototype.animate;
    Element.prototype.animate = function (...args) {
      moves.push({ kind: "script", name: JSON.stringify(args[0]), at: where(this) });
      return animate.apply(this, args);
    };
    const start = document.startViewTransition?.bind(document);
    if (start) {
      document.startViewTransition = (...args: Parameters<typeof start>) => {
        moves.push({ kind: "view-transition", name: "", at: "" });
        return start(...args);
      };
    }
  });
}

/** Forgets what has moved so far, so the next read starts from here. */
export async function forgetMotion(page: Page): Promise<void> {
  await page.evaluate(() => {
    const moves = (window as Recorded).__moves;
    if (moves) moves.length = 0;
  });
}

/** What has moved since the page loaded, or since `forgetMotion`. */
export async function motion(page: Page): Promise<Move[]> {
  return page.evaluate(() => (window as Recorded).__moves ?? []);
}
