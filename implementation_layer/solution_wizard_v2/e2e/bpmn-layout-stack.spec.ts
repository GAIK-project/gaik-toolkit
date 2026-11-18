import { test, expect, type Page } from "@playwright/test";
import { waitForApiHealthy } from "./helpers/api";
import { draftSteps, openEditor, sessionAtBpmn, writeDraft } from "./helpers/bpmn-stack";
import { centre, drag, flowBetween, focusStep, inLaneBelow, laneAt, onFlow } from "./helpers/bpmn-canvas";

const STACK_E2E = process.env.PLAYWRIGHT_STACK_E2E === "true";

/**
 * Where the user puts shapes and bends flows on the BPMN canvas, against the
 * real stack (UI + wizard_api + Postgres): a layout kept by wizard_api
 * (`PUT /bpmn/layout`) and laid over the diagram it draws again from the
 * blueprint, so a dragged task and a bent flow are where they were left after
 * a page reload. A data object dragged into another lane is refused and
 * nothing is kept (a step dragged there changes lanes: e2e/bpmn-lanes-stack.spec.ts).
 * e2e/bpmn-layout.spec.ts covers the same on the mock store with wizard_api
 * stood in.
 */

/** The invoice's data object, drawn above the upload step. */
const DATA = "DataObjectRef_invoice";

/** Where a shape is drawn, in diagram units (its graphics' translation). */
async function placed(page: Page, id: string) {
  return page.evaluate((id) => {
    const gfx = document.querySelector<SVGGElement>(`.bpmn-editable .djs-element[data-element-id="${id}"]`)!;
    const m = gfx.transform.baseVal.consolidate()!.matrix;
    return { x: Math.round(m.e), y: Math.round(m.f) };
  }, id);
}

/** How a flow is drawn: its line's path. */
const drawn = (page: Page, id: string) =>
  page.locator(`.bpmn-editable .djs-element[data-element-id="${id}"] .djs-visual > path`).first().getAttribute("d");

/** A shape's place in the server's diagram (the "Show data" mode the page opens with). */
async function shapeBounds(page: Page, sessionId: string, id: string) {
  return page.evaluate(
    async ({ sessionId, id }) => {
      const xml = await (await fetch(`/api/sessions/${sessionId}/bpmn`, { cache: "no-store" })).text();
      const doc = new DOMParser().parseFromString(xml, "application/xml");
      const shape = [...doc.getElementsByTagNameNS("*", "BPMNShape")].find((s) => s.getAttribute("bpmnElement") === id);
      const b = shape!.getElementsByTagNameNS("*", "Bounds")[0];
      return { x: Number(b.getAttribute("x")), y: Number(b.getAttribute("y")) };
    },
    { sessionId, id },
  );
}

/** A flow's waypoints in the server's diagram. */
async function edgeWaypoints(page: Page, sessionId: string, id: string) {
  return page.evaluate(
    async ({ sessionId, id }) => {
      const xml = await (await fetch(`/api/sessions/${sessionId}/bpmn`, { cache: "no-store" })).text();
      const doc = new DOMParser().parseFromString(xml, "application/xml");
      const edge = [...doc.getElementsByTagNameNS("*", "BPMNEdge")].find((s) => s.getAttribute("bpmnElement") === id);
      return [...edge!.getElementsByTagNameNS("*", "waypoint")].map((w) => [
        Number(w.getAttribute("x")),
        Number(w.getAttribute("y")),
      ]);
    },
    { sessionId, id },
  );
}

test.describe("BPMN layout (stack)", () => {
  test.skip(!STACK_E2E, "set PLAYWRIGHT_STACK_E2E=true (docker-test.sh --step stack-e2e)");
  test.use({ viewport: { width: 1600, height: 1100 } });

  test.beforeAll(async ({ request }) => {
    await waitForApiHealthy(request);
  });

  test("a task dragged within its lane and a bent flow are where they were left after a reload", async ({
    page,
    request,
  }) => {
    test.setTimeout(240_000);
    const id = await sessionAtBpmn(page, request);
    await writeDraft(request, id);
    await page.reload();
    await openEditor(page);
    const operations: string[] = [];
    page.on("request", (r) => {
      if (r.method() === "POST" && /\/blueprint\/(operations|undo)/.test(r.url())) operations.push(r.url());
    });
    const flow = await flowBetween(page, id, "Activity_extract", "Activity_review");
    const before = await shapeBounds(page, id, "Activity_extract");
    const stepsBefore = await draftSteps(request, id);

    // The extraction step moves left within its lane; the flow out of it is bent.
    await focusStep(page, 1);
    const from = await centre(page, "Activity_extract");
    const to = { x: from.x - 50, y: from.y };
    expect(await laneAt(page, to)).toBe(await laneAt(page, from));
    const saved = page.waitForResponse((r) => r.url().includes("/bpmn/layout") && r.request().method() === "PUT");
    await drag(page, from, to);
    const bend = await onFlow(page, flow);
    await drag(page, bend, { x: bend.x + 40, y: bend.y + 40 });
    const answer = await saved;
    expect(answer.status()).toBe(204);
    const body = answer.request().postDataJSON() as {
      shapes: Record<string, { x: number; y: number }>;
      edges: Record<string, [number, number][]>;
    };
    expect(answer.url()).toContain("data_objects=1");
    expect(body.shapes.Activity_extract.x).toBeLessThan(before.x - 20);
    expect(body.shapes.Activity_extract.y).toBe(before.y);
    expect(body.edges[flow].length).toBeGreaterThan(2);
    const shapeLeft = await placed(page, "Activity_extract");
    const flowLeft = await drawn(page, flow);

    // After a reload the canvas, and the diagram wizard_api draws, have both where they were left.
    await page.reload();
    await openEditor(page);
    expect(await placed(page, "Activity_extract")).toEqual(shapeLeft);
    expect(await drawn(page, flow)).toBe(flowLeft);
    expect(await shapeBounds(page, id, "Activity_extract")).toEqual(body.shapes.Activity_extract);
    expect(await edgeWaypoints(page, id, flow)).toEqual(body.edges[flow]);

    // A layout only: no operation was sent and the blueprint is as it was.
    expect(operations).toEqual([]);
    expect(await draftSteps(request, id)).toEqual(stepsBefore);
  });

  test("a data object dragged into another lane is refused: it goes back and nothing is kept", async ({
    page,
    request,
  }) => {
    test.setTimeout(240_000);
    const id = await sessionAtBpmn(page, request);
    await writeDraft(request, id);
    await page.reload();
    await openEditor(page);
    const layouts: string[] = [];
    page.on("request", (r) => {
      if (r.url().includes("/bpmn/layout")) layouts.push(`${r.method()} ${r.url()}`);
    });
    const before = await shapeBounds(page, id, DATA);

    await focusStep(page, 0);
    const where = await placed(page, DATA);
    const from = await centre(page, DATA);
    const to = await inLaneBelow(page, from);
    expect(await laneAt(page, to)).not.toBe(await laneAt(page, from));
    await drag(page, from, to);
    expect(await placed(page, DATA)).toEqual(where);
    await page.waitForTimeout(1_500);
    expect(layouts).toEqual([]);

    await page.reload();
    await openEditor(page);
    expect(await placed(page, DATA)).toEqual(where);
    expect(await shapeBounds(page, id, DATA)).toEqual(before);
  });
});
