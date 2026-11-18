import { test, expect, type Page, type Route } from "@playwright/test";
import { resetMockSessions } from "./helpers/mock";
import { loginAsDev } from "./helpers/auth";
import {
  openBlueprintEditor,
  openBpmnView,
  selectWorkspaceTab,
  setChatOpen,
  unlockBpmnEditor,
} from "./helpers/workspace";
import { centre, drag, focusStep, inLaneBelow, laneAt } from "./helpers/bpmn-canvas";

/**
 * Lanes on the BPMN canvas on the mock store: who does each step. Without
 * wizard_api the canvas is read-only and offers no lane tools. With the
 * server's mapping stood in (each lane named by its participant), the
 * palette's "Add lane", a lane's Rename and Remove, a step dragged into
 * another lane and the step panel's lane select send their operations; once
 * a lane change is made the step's kept place is dropped, and a refused one
 * keeps it. That the edits are
 * kept over a reload is in e2e/bpmn-lanes-stack.spec.ts.
 */

const STEPS = ["ingest", "extract", "classify", "approve", "export"];

type Sent = { kind: "layout" | "ops"; url: string; body: unknown };

async function openFlow(page: Page) {
  await loginAsDev(page);
  await page.goto("/sessions/ses_laskut");
  await setChatOpen(page, false);
  await selectWorkspaceTab(page, "Työnkulku");
  await openBpmnView(page);
  await expect(page.locator('.bpmn-editable [data-element-id="Activity_classify"]')).toBeVisible({ timeout: 30_000 });
  await expect(page.locator(".bpmn-editable")).toHaveAttribute("aria-busy", "false");
}

/** The lanes of the diagram the mock store draws: element id and name. */
async function drawnLanes(page: Page): Promise<{ id: string; name: string }[]> {
  const xml = await (await page.request.get("/api/sessions/ses_laskut/bpmn?data_objects=1")).text();
  return [...xml.matchAll(/<bpmn:lane id="([^"]+)" name="([^"]*)"/g)].map((m) => ({ id: m[1], name: m[2] }));
}

/** wizard_api's mapping, lanes named by participant, and its layout and operations routes, stood in. */
async function openEditable(page: Page, onOperation: (route: Route) => Promise<void>) {
  const sent: Sent[] = [];
  await loginAsDev(page);
  const lanes = await drawnLanes(page);
  expect(lanes.length).toBeGreaterThan(1);
  const mapping: Record<string, Record<string, string>> = {
    StartEvent_1: { kind: "start_event", blueprint_path: "derived:start" },
  };
  STEPS.forEach((id, i) => {
    mapping[`Activity_${id}`] = { kind: "user_task", blueprint_path: `workflow.steps[${i}]`, performed_by: "" };
  });
  lanes.forEach((lane, i) => {
    mapping[lane.id] = {
      kind: "lane",
      blueprint_path: `business_process.participants[${i}]`,
      participant_id: lane.id.replace(/^Lane_/, ""),
    };
  });
  await page.route("**/api/sessions/ses_laskut/bpmn/mapping*", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ mapping, has_draft: true }) }),
  );
  await page.route("**/api/sessions/ses_laskut/bpmn/layout*", (route) => {
    sent.push({ kind: "layout", url: route.request().url(), body: route.request().postDataJSON() });
    return route.fulfill({ status: 204 });
  });
  await page.route("**/api/sessions/ses_laskut/blueprint/operations", (route) => {
    sent.push({ kind: "ops", url: route.request().url(), body: route.request().postDataJSON() });
    return onOperation(route);
  });
  await openFlow(page);
  await unlockBpmnEditor(page);
  await expect(page.getByTestId("bpmn-panel")).toHaveAttribute("data-ops", "on", { timeout: 30_000 });
  await expect(page.locator('.bpmn-editable .djs-palette .entry[data-action="gaik-add-lane"]')).toBeVisible();
  return { sent, lanes };
}

const refused = (reason: string) => (route: Route) =>
  route.fulfill({
    status: 422,
    contentType: "application/json",
    body: JSON.stringify({ detail: { error: "invalid_operation", message: "no", field: "operations[0].lane_id", code: reason } }),
  });

/** The session's blueprint, read from the form's JSON: what a made edit answers with. */
async function readBlueprint(page: Page): Promise<unknown> {
  await loginAsDev(page);
  await page.goto("/sessions/ses_laskut");
  await setChatOpen(page, false);
  await openBlueprintEditor(page);
  await page.getByTestId("blueprint-json-toggle").click();
  const blueprint = JSON.parse(await page.getByTestId("blueprint-json-editor").inputValue()) as unknown;
  await page.getByTestId("blueprint-done").click();
  return blueprint;
}

const made = (blueprint: unknown) => (route: Route) =>
  route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({
      session: {
        id: "ses_laskut",
        active_version: (route.request().postDataJSON() as { base_version: number }).base_version,
        blueprint,
      },
      warnings: [],
      needs_attention: [],
      bpmn_changed: true,
    }),
  });

const operations = (sent: Sent[]) =>
  sent.filter((s) => s.kind === "ops").map((s) => (s.body as { operations: unknown[] }).operations);

/** Clicks a lane on its title band, where nothing else is drawn. */
async function clickLane(page: Page, laneId: string) {
  const box = (await page.locator(`.bpmn-editable [data-element-id="${laneId}"]`).first().boundingBox())!;
  await page.mouse.click(box.x + 12, box.y + box.height / 2);
}

test.describe("BPMN lanes", () => {
  test.use({ viewport: { width: 1600, height: 1100 } });
  test.beforeEach(async ({ request }) => {
    await resetMockSessions(request);
  });

  test("without wizard_api the lane tools are not offered: no Add lane, no lane pad, no lane select", async ({ page }) => {
    test.setTimeout(90_000);
    const writes: string[] = [];
    page.on("request", (r) => {
      if (r.method() !== "GET" && /blueprint\/operations|bpmn\/layout/.test(r.url())) writes.push(r.url());
    });
    await openFlow(page);
    await expect(page.getByTestId("bpmn-panel")).toHaveAttribute("data-ops", "off");
    await expect(page.locator('.djs-palette .entry[data-action="gaik-add-lane"]')).toHaveCount(0);
    const lane = (await drawnLanes(page))[0];
    await clickLane(page, lane.id);
    await expect(page.locator('.djs-context-pad .entry[data-action^="gaik-lane-"]')).toHaveCount(0);
    // A step's panel has no lane select.
    await page.getByTestId("flow-step-list").locator("li").nth(2).getByRole("button").first().click();
    await expect(page.getByTestId("bpmn-step-panel")).toBeVisible();
    await expect(page.getByTestId("bpmn-step-lane")).toHaveCount(0);
    // A step dragged into the lane below stays and nothing is sent.
    await page.getByTestId("bpmn-properties").getByRole("button", { name: "Sulje" }).click();
    const from = await centre(page, "Activity_classify");
    await drag(page, from, await inLaneBelow(page, from));
    await page.waitForTimeout(1_000);
    expect(writes).toEqual([]);
  });

  test("Add lane, a lane's Rename and Remove send their operations, and a lane in use says why it stays", async ({
    page,
  }) => {
    test.setTimeout(90_000);
    const { sent, lanes } = await openEditable(page, refused("lane_in_use"));

    await page.locator('.bpmn-editable .djs-palette .entry[data-action="gaik-add-lane"]').click();
    await expect.poll(() => operations(sent).length).toBe(1);
    expect(operations(sent)[0]).toEqual([{ op: "add_lane", name: "Uusi kaista" }]);
    await expect(page.locator(".bpmn-editable")).toHaveAttribute("aria-busy", "false");

    const lane = lanes[1];
    await clickLane(page, lane.id);
    const pad = page.locator(".djs-context-pad");
    await expect(pad.locator(".entry")).toHaveCount(2);
    await expect(pad.locator('.entry[data-action="gaik-lane-rename"]')).toHaveAttribute("title", "Nimeä kaista uudelleen");
    await pad.locator('.entry[data-action="gaik-lane-remove"]').click();
    await expect.poll(() => operations(sent).length).toBe(2);
    expect(operations(sent)[1]).toEqual([{ op: "remove_lane", lane_id: lane.id.replace(/^Lane_/, "") }]);
    await expect(page.getByTestId("bpmn-status")).toContainText("Kaistaa ei poistettu: siinä on vaiheita.");

    // Renamed in place: rename_lane with the lane's participant. (Picked again: a click on
    // the lane still selected opens no pad.)
    await expect(page.locator(".bpmn-editable")).toHaveAttribute("aria-busy", "false");
    await clickLane(page, lanes[0].id);
    await clickLane(page, lane.id);
    await page.locator('.djs-context-pad .entry[data-action="gaik-lane-rename"]').click();
    const editor = page.locator(".djs-direct-editing-parent");
    await expect(editor).toBeVisible();
    await page.keyboard.press("ControlOrMeta+a");
    await page.keyboard.type("Tarkastajat");
    await page.mouse.click(5, 5);
    await expect.poll(() => operations(sent).length).toBe(3);
    expect(operations(sent)[2]).toEqual([
      { op: "rename_lane", lane_id: lane.id.replace(/^Lane_/, ""), name: "Tarkastajat" },
    ]);
  });

  test("a step dragged into another lane sends set_step_lane, and once it is made its kept place goes in both drawings", async ({
    page,
  }) => {
    test.setTimeout(120_000);
    const blueprint = await readBlueprint(page);
    const { sent } = await openEditable(page, made(blueprint));
    await focusStep(page, 2);
    const from = await centre(page, "Activity_classify");
    const to = await inLaneBelow(page, from);
    const target = await laneAt(page, to);
    expect(target).not.toBe(await laneAt(page, from));
    await drag(page, from, to);

    // The operation first; the kept place goes only once it is made.
    await expect.poll(() => sent.map((s) => s.kind)).toEqual(["ops", "layout", "layout"]);
    expect(operations(sent)[0]).toEqual([
      { op: "set_step_lane", step_id: "classify", lane_id: target!.replace(/^Lane_/, "") },
    ]);
    const [zero, one] = sent.filter((s) => s.kind === "layout");
    expect([zero.url, one.url].map((u) => /data_objects=(\d)/.exec(u)![1])).toEqual(["0", "1"]);
    const reset = zero.body as { shapes: Record<string, null>; edges: Record<string, null> };
    expect(reset.shapes).toEqual({ Activity_classify: null });
    expect(Object.keys(reset.edges).length).toBeGreaterThan(0);
    expect(Object.values(reset.edges).every((v) => v === null)).toBe(true);
    expect(one.body).toEqual(zero.body);
    await expect(page.getByTestId("bpmn-status")).toContainText("Tallennettu");
  });

  test("a refused lane change keeps the step's kept place: no layout is sent", async ({ page }) => {
    test.setTimeout(90_000);
    const { sent } = await openEditable(page, refused("not_found"));
    await focusStep(page, 2);
    const from = await centre(page, "Activity_classify");
    await drag(page, from, await inLaneBelow(page, from));
    await expect.poll(() => operations(sent).length).toBe(1);
    await expect(page.getByTestId("bpmn-status")).toContainText("Muutosta ei");
    await page.waitForTimeout(1_500);
    expect(sent.map((s) => s.kind)).toEqual(["ops"]);
  });

  test("the step panel's lane select lists the lanes by name and sends set_step_lane", async ({ page }) => {
    test.setTimeout(90_000);
    const { sent, lanes } = await openEditable(page, refused("not_found"));
    await page.getByTestId("flow-step-list").locator("li").nth(2).getByRole("button").first().click();
    const select = page.getByTestId("bpmn-step-lane");
    await expect(select).toBeEnabled();
    await expect(select).toHaveValue("");
    const options = await select.locator("option").allTextContents();
    expect(options).toEqual(["Tyypin oletuskaista", ...lanes.map((l) => l.name)]);
    const pick = lanes[lanes.length - 1];
    await select.selectOption(pick.id.replace(/^Lane_/, ""));
    await expect.poll(() => operations(sent).length).toBe(1);
    expect(operations(sent)[0]).toEqual([
      { op: "set_step_lane", step_id: "classify", lane_id: pick.id.replace(/^Lane_/, "") },
    ]);
    // Refused: the step's kept place stays.
    await expect(page.getByTestId("bpmn-status")).toContainText("Muutosta ei");
    expect(sent.filter((s) => s.kind === "layout")).toHaveLength(0);
  });
});
