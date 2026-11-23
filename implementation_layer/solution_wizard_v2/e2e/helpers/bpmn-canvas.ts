import { expect, type Page } from "@playwright/test";

/**
 * Pointer work on the BPMN canvas (the modeler, `.bpmn-editable`), on screen:
 * where shapes and lanes are, dragging a shape and bending a flow. Shared by
 * e2e/bpmn-layout.spec.ts and e2e/bpmn-layout-stack.spec.ts.
 */

export const shape = (page: Page, id: string) => page.locator(`.bpmn-editable [data-element-id="${id}"]`).first();

/** Puts a step in the middle of the canvas (its row in the step list), with its properties closed. */
export async function focusStep(page: Page, index: number) {
  await page.getByTestId("flow-step-list").locator("li").nth(index).getByRole("button").first().click();
  await page.getByTestId("bpmn-properties").getByRole("button", { name: "Sulje" }).click();
}

export async function centre(page: Page, id: string) {
  const box = (await shape(page, id).boundingBox())!;
  return { x: box.x + box.width / 2, y: box.y + box.height / 2 };
}

/** The lane whose drawn box holds the point, on screen. */
export async function laneAt(page: Page, point: { x: number; y: number }): Promise<string | null> {
  return page.evaluate(({ x, y }) => {
    let best: { id: string; area: number } | null = null;
    for (const el of document.querySelectorAll('.bpmn-editable .djs-element[data-element-id^="Lane_"]')) {
      const r = el.querySelector(".djs-visual")!.getBoundingClientRect();
      if (x < r.left || x > r.right || y < r.top || y > r.bottom) continue;
      const area = r.width * r.height;
      if (!best || area < best.area) best = { id: el.getAttribute("data-element-id")!, area };
    }
    return best?.id ?? null;
  }, point);
}

/** A point inside the lane drawn below the one that holds `point`, on screen. */
export async function inLaneBelow(page: Page, point: { x: number; y: number }) {
  return page.evaluate(({ x, y }) => {
    const lanes = [...document.querySelectorAll('.bpmn-editable .djs-element[data-element-id^="Lane_"]')].map((el) =>
      el.querySelector(".djs-visual")!.getBoundingClientRect(),
    );
    const own = lanes.find((r) => y >= r.top && y <= r.bottom && x >= r.left && x <= r.right)!;
    const below = lanes.filter((r) => r.top >= own.bottom - 1).sort((a, b) => a.top - b.top)[0];
    return { x, y: below.top + Math.min(50, below.height / 2) };
  }, point);
}

/** The id of the sequence flow from one element to another, read from the server's diagram. */
export async function flowBetween(page: Page, sessionId: string, source: string, target: string): Promise<string> {
  const id = await page.evaluate(
    async ({ sessionId, source, target }) => {
      const xml = await (await fetch(`/api/sessions/${sessionId}/bpmn`, { cache: "no-store" })).text();
      const doc = new DOMParser().parseFromString(xml, "application/xml");
      const flow = [...doc.getElementsByTagNameNS("*", "sequenceFlow")].find(
        (f) => f.getAttribute("sourceRef") === source && f.getAttribute("targetRef") === target,
      );
      return flow?.getAttribute("id") ?? null;
    },
    { sessionId, source, target },
  );
  expect(id, `a flow ${source} → ${target}`).toBeTruthy();
  return id!;
}

/** A point on a flow's drawn line that nothing else covers, on screen: a drag there bends the flow. */
export async function onFlow(page: Page, id: string) {
  const point = await page.evaluate((id) => {
    const path = document.querySelector<SVGPathElement>(
      `.bpmn-editable .djs-element[data-element-id="${id}"] .djs-visual > path`,
    )!;
    const m = path.getScreenCTM()!;
    const length = path.getTotalLength();
    for (const share of [0.3, 0.25, 0.35, 0.2, 0.4, 0.15, 0.6, 0.65, 0.7, 0.75, 0.8]) {
      const p = path.getPointAtLength(length * share);
      const x = p.x * m.a + p.y * m.c + m.e;
      const y = p.x * m.b + p.y * m.d + m.f;
      const hit = document.elementFromPoint(x, y)?.closest("[data-element-id]")?.getAttribute("data-element-id");
      if (hit === id) return { x, y };
    }
    return null;
  }, id);
  expect(point, `a free point on ${id}`).toBeTruthy();
  return point!;
}

export async function drag(page: Page, from: { x: number; y: number }, to: { x: number; y: number }) {
  await page.mouse.move(from.x, from.y);
  await page.mouse.down();
  await page.mouse.move((from.x + to.x) / 2, (from.y + to.y) / 2, { steps: 4 });
  await page.mouse.move(to.x, to.y, { steps: 6 });
  await page.mouse.up();
}

/** Where a shape sits beside another one that does not move, on screen. */
export async function offset(page: Page, id: string, from: string) {
  const a = (await shape(page, id).boundingBox())!;
  const b = (await shape(page, from).boundingBox())!;
  return { x: a.x - b.x, y: a.y - b.y };
}
