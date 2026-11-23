import { test, expect, type Page, type Route } from "@playwright/test";
import { resetMockSessions } from "./helpers/mock";
import { loginAsDev } from "./helpers/auth";
import { openBpmnView, selectWorkspaceTab, setChatOpen, unlockBpmnEditor } from "./helpers/workspace";
import { centre, drag, flowBetween, focusStep, inLaneBelow, laneAt, offset, onFlow } from "./helpers/bpmn-canvas";

/**
 * Where the user puts shapes and bends flows on the BPMN canvas: a layout
 * (`PUT /bpmn/layout`), not an operation on the blueprint. A drag within a
 * lane and a bent flow are sent together after 800 ms, with no operation, no
 * version and no reload; a drag into a lane no participant stands for is
 * refused; a drag not sent
 * yet goes out before the next operation; no drag starts while an operation
 * is on its way. wizard_api's mapping and layout routes are stood in by the
 * test on the mock store. Without wizard_api the canvas is read-only and a
 * drag sends nothing (e2e/bpmn-editing.spec.ts); that the layout is kept
 * over a reload is in e2e/bpmn-layout-stack.spec.ts.
 */

const STEPS = ["ingest", "extract", "classify", "approve", "export"];

type Sent = { kind: "layout" | "ops" | "reload"; url: string; body?: unknown; at: number };

async function openEditable(page: Page, onOperation: (route: Route) => Promise<void>) {
  const sent: Sent[] = [];
  const mapping: Record<string, { kind: string; blueprint_path: string }> = {
    StartEvent_1: { kind: "start_event", blueprint_path: "derived:start" },
  };
  STEPS.forEach((id, i) => {
    mapping[`Activity_${id}`] = { kind: "user_task", blueprint_path: `workflow.steps[${i}]` };
  });
  await page.route("**/api/sessions/ses_laskut/bpmn/mapping*", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ mapping, has_draft: true }) }),
  );
  await page.route("**/api/sessions/ses_laskut/bpmn/layout*", (route) => {
    sent.push({ kind: "layout", url: route.request().url(), body: route.request().postDataJSON(), at: Date.now() });
    return route.fulfill({ status: 204 });
  });
  await page.route("**/api/sessions/ses_laskut/blueprint/operations", (route) => {
    sent.push({ kind: "ops", url: route.request().url(), body: route.request().postDataJSON(), at: Date.now() });
    return onOperation(route);
  });
  page.on("request", (r) => {
    if (r.method() === "GET" && /\/api\/sessions\/ses_laskut\/bpmn(\?|$)/.test(r.url())) {
      sent.push({ kind: "reload", url: r.url(), at: Date.now() });
    }
  });
  await loginAsDev(page);
  await page.goto("/sessions/ses_laskut");
  await setChatOpen(page, false);
  await selectWorkspaceTab(page, "Työnkulku");
  await openBpmnView(page);
  await unlockBpmnEditor(page);
  await expect(page.getByTestId("bpmn-panel")).toHaveAttribute("data-ops", "on", { timeout: 30_000 });
  await expect(page.locator(".bpmn-editable")).toHaveAttribute("aria-busy", "false");
  await expect(page.locator('.bpmn-editable .djs-palette .entry[data-action="gaik-add-step"]')).toBeVisible();
  return sent;
}

test.describe("BPMN layout", () => {
  test.use({ viewport: { width: 1600, height: 1100 } });
  test.beforeEach(async ({ request }) => {
    await resetMockSessions(request);
  });

  test("a drag within its lane and a bent flow go out together as one layout after 800 ms, with no operation and no reload", async ({
    page,
  }) => {
    test.setTimeout(90_000);
    const sent = await openEditable(page, (route) => route.fulfill({ status: 500, body: "not in this test" }));
    const flow = await flowBetween(page, "ses_laskut", "Activity_classify", "Activity_approve");
    await focusStep(page, 2);
    const start = sent.length;

    // Classification moves right within the AI lane.
    const from = await centre(page, "Activity_classify");
    const lane = await laneAt(page, from);
    expect(lane).toBeTruthy();
    const to = { x: from.x + 40, y: from.y };
    expect(await laneAt(page, to)).toBe(lane);
    const before = await offset(page, "Activity_classify", "Activity_ingest");
    await drag(page, from, to);
    const after = await offset(page, "Activity_classify", "Activity_ingest");
    expect(after.x - before.x).toBeGreaterThan(20);

    // The flow out of it is bent, before the first change has gone out.
    const bend = await onFlow(page, flow);
    await page.mouse.move(bend.x, bend.y);
    await page.waitForTimeout(150);
    await drag(page, bend, { x: bend.x + 40, y: bend.y + 40 });
    const lastDrop = Date.now();

    await expect.poll(() => sent.filter((s) => s.kind === "layout").length, { timeout: 5_000 }).toBe(1);
    await page.waitForTimeout(1_200);
    const mine = sent.slice(start);
    const layouts = mine.filter((s) => s.kind === "layout");
    expect(layouts).toHaveLength(1);
    // Debounced: not before 800 ms after the last change.
    expect(layouts[0].at - lastDrop).toBeGreaterThanOrEqual(700);
    // The drawing with its data objects, as the canvas shows it.
    expect(layouts[0].url).toContain("data_objects=1");
    const body = layouts[0].body as {
      shapes: Record<string, { x: number; y: number }>;
      edges: Record<string, [number, number][]>;
    };
    expect(Object.keys(body.shapes)).toEqual(["Activity_classify"]);
    expect(body.edges[flow].length).toBeGreaterThan(2);
    // A layout only: no operation, and the diagram is not read again.
    expect(mine.filter((s) => s.kind !== "layout")).toEqual([]);
    // The canvas keeps the shape where it was left.
    expect(await offset(page, "Activity_classify", "Activity_ingest")).toEqual(after);

    // Without the data objects the drawing is another one: its layout goes to that mode.
    await page.getByTestId("bpmn-show-data").click();
    await expect(page.getByTestId("bpmn-show-data")).toHaveAttribute("aria-pressed", "false");
    await expect(page.locator(".bpmn-editable")).toHaveAttribute("aria-busy", "false");
    await expect(page.locator('.bpmn-editable .djs-palette .entry[data-action="gaik-add-step"]')).toBeVisible();
    await focusStep(page, 2);
    const next = sent.length;
    const at = await centre(page, "Activity_classify");
    await drag(page, at, { x: at.x + 30, y: at.y });
    await expect.poll(() => sent.slice(next).filter((s) => s.kind === "layout").length, { timeout: 5_000 }).toBe(1);
    const compact = sent.slice(next).find((s) => s.kind === "layout")!;
    expect(compact.url).toContain("data_objects=0");
    expect(Object.keys((compact.body as { shapes: object }).shapes)).toEqual(["Activity_classify"]);
  });

  // The mapping here names no lane's participant: a step dragged into a lane the mapping
  // names is put in it (set_step_lane, e2e/bpmn-lanes.spec.ts).
  test("a drag into a lane the mapping names no participant for is refused: the shape goes back and nothing is sent", async ({
    page,
  }) => {
    test.setTimeout(90_000);
    const sent = await openEditable(page, (route) => route.fulfill({ status: 500, body: "not in this test" }));
    await focusStep(page, 2);
    const start = sent.length;
    const from = await centre(page, "Activity_classify");
    const to = await inLaneBelow(page, from);
    expect(await laneAt(page, to)).not.toBe(await laneAt(page, from));
    const before = await offset(page, "Activity_classify", "Activity_ingest");
    await drag(page, from, to);
    expect(await offset(page, "Activity_classify", "Activity_ingest")).toEqual(before);
    await page.waitForTimeout(1_500);
    expect(sent.slice(start)).toEqual([]);
  });

  test("a step drawn outside its own lane can be dragged back into it, and not within the lane it is drawn in", async ({
    page,
  }) => {
    test.setTimeout(90_000);
    // The diagram draws Classification in the reviewers' lane, while the AI lane lists it (flowNodeRef):
    // a place kept from before the step changed lanes.
    await page.route("**/api/sessions/ses_laskut/bpmn", async (route) => {
      const res = await route.fetch();
      const xml = await res.text();
      const boundsOf = (id: string) => {
        const m = new RegExp(`bpmnElement="${id}"[^>]*>[^<]*<[^>]*Bounds x="([0-9.]+)" y="([0-9.]+)"`).exec(xml);
        expect(m, id).toBeTruthy();
        return { x: m![1], y: Number(m![2]) };
      };
      const task = boundsOf("Activity_classify");
      const drop = boundsOf("Lane_reviewer").y - boundsOf("Lane_genai").y;
      const moved = xml.replace(
        new RegExp(`(bpmnElement="Activity_classify"[^>]*>[^<]*<[^>]*Bounds x="[0-9.]+" y=")[0-9.]+`),
        `$1${task.y + drop}`,
      );
      await route.fulfill({ response: res, body: moved });
    });
    const sent = await openEditable(page, (route) => route.fulfill({ status: 500, body: "not in this test" }));
    await focusStep(page, 2);
    const from = await centre(page, "Activity_classify");
    expect(await laneAt(page, from)).toBe("Lane_reviewer");
    const before = await offset(page, "Activity_classify", "Activity_ingest");
    const start = sent.length;

    // Within the lane it is drawn in: refused.
    await drag(page, from, { x: from.x + 40, y: from.y });
    expect(await offset(page, "Activity_classify", "Activity_ingest")).toEqual(before);

    // Back up into the AI lane: moved and kept.
    // A free spot in the AI lane, where the drop lands on the lane itself and not on a flow.
    const to = await page.evaluate((from) => {
      const lane = document
        .querySelector('.bpmn-editable .djs-element[data-element-id="Lane_genai"] .djs-visual')!
        .getBoundingClientRect();
      for (const dy of [60, 90, 120, 150]) {
        for (const dx of [0, -40, 40, -80, 80, -120, 120, -160, 160]) {
          const x = from.x + dx;
          const y = lane.top + dy;
          const hit = document.elementFromPoint(x, y)?.closest("[data-element-id]")?.getAttribute("data-element-id");
          if (hit === "Lane_genai") return { x, y };
        }
      }
      return null;
    }, from);
    expect(to, "a free spot in the AI lane").toBeTruthy();
    expect(await laneAt(page, to!)).toBe("Lane_genai");
    await drag(page, from, to!);
    expect((await offset(page, "Activity_classify", "Activity_ingest")).y).toBeLessThan(before.y - 50);
    await expect.poll(() => sent.slice(start).filter((s) => s.kind === "layout").length, { timeout: 5_000 }).toBe(1);
    const body = sent.slice(start).find((s) => s.kind === "layout")!.body as { shapes: object };
    expect(Object.keys(body.shapes)).toEqual(["Activity_classify"]);
  });

  test("a drag not sent yet goes out before the next operation, and no drag starts while an operation is on its way", async ({
    page,
  }) => {
    test.setTimeout(90_000);
    let release: () => void = () => {};
    const held = new Promise<void>((resolve) => (release = resolve));
    const sent = await openEditable(page, async (route) => {
      await held;
      await route.fulfill({
        status: 422,
        contentType: "application/json",
        body: JSON.stringify({ error: "invalid_operation", message: "no" }),
      });
    });
    await focusStep(page, 2);
    const start = sent.length;
    const from = await centre(page, "Activity_classify");
    await drag(page, from, { x: from.x + 30, y: from.y });
    // At once, before the 800 ms are up: the step goes later.
    await page.locator('.djs-context-pad .entry[data-action="move-later"]').click();
    await expect.poll(() => sent.slice(start).map((s) => s.kind)).toEqual(["layout", "ops"]);

    // While that edit is on its way, a drag does nothing and is not sent.
    const before = await offset(page, "Activity_extract", "Activity_ingest");
    const at = await centre(page, "Activity_extract");
    await drag(page, at, { x: at.x + 30, y: at.y });
    expect(await offset(page, "Activity_extract", "Activity_ingest")).toEqual(before);
    release();
    await expect(page.getByTestId("bpmn-status")).toContainText("Muutosta ei voitu tehdä.");
    await page.waitForTimeout(1_500);
    expect(sent.slice(start).filter((s) => s.kind === "layout")).toHaveLength(1);
  });
});
