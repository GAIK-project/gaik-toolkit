import { test, expect, type Page, type Route } from "@playwright/test";
import { resetMockSessions } from "./helpers/mock";
import { loginAsDev } from "./helpers/auth";
import { openBpmnView, selectWorkspaceTab, setChatOpen, unlockBpmnEditor } from "./helpers/workspace";

/**
 * Data objects on the BPMN canvas on the mock store. Without wizard_api the
 * canvas is read-only: a data object has no tools and is not renamed in
 * place. With the server's mapping stood in (each data object's artifact,
 * `data_object`), a data object's pad renames it in place
 * (`rename_data_object`) and starts a line to a step, which is `link_data`
 * (from the data object: the step uses it); deleting a data association is
 * `unlink_data`. A refusal says why in the UI language. That the edits are
 * kept over a reload is in e2e/bpmn-data-objects-stack.spec.ts.
 */

const STEPS = ["ingest", "extract", "classify", "approve", "export"];

type Drawn = {
  /** Data object reference ids. */
  objects: string[];
  /** Data associations: id, task, data object and its kind. */
  links: { id: string; task: string; data: string; role: "input" | "output" }[];
};

/** The data objects and their associations the mock store draws. */
async function drawnData(page: Page): Promise<Drawn> {
  const xml = await (await page.request.get("/api/sessions/ses_laskut/bpmn?data_objects=1")).text();
  return page.evaluate((text) => {
    const doc = new DOMParser().parseFromString(text, "application/xml");
    const all = [...doc.getElementsByTagName("*")];
    const objects = all.filter((e) => e.localName === "dataObjectReference").map((e) => e.getAttribute("id") ?? "");
    const links: Drawn["links"] = [];
    for (const e of all) {
      if (e.localName !== "dataInputAssociation" && e.localName !== "dataOutputAssociation") continue;
      const input = e.localName === "dataInputAssociation";
      const ref = [...e.children].find((c) => c.localName === (input ? "sourceRef" : "targetRef"));
      links.push({
        id: e.getAttribute("id") ?? "",
        task: e.parentElement?.getAttribute("id") ?? "",
        data: ref?.textContent?.trim() ?? "",
        role: input ? "input" : "output",
      });
    }
    return { objects, links };
  }, xml);
}

const artifactOf = (dataObjectId: string) => dataObjectId.replace(/^DataObjectRef_/, "");

async function openFlow(page: Page) {
  await loginAsDev(page);
  await page.goto("/sessions/ses_laskut");
  await setChatOpen(page, false);
  await selectWorkspaceTab(page, "Työnkulku");
  await openBpmnView(page);
  await expect(page.locator('.bpmn-editable [data-element-id="Activity_classify"]')).toBeVisible({ timeout: 30_000 });
  await expect(page.locator(".bpmn-editable")).toHaveAttribute("aria-busy", "false");
}

/** wizard_api's mapping (steps and data objects) and operations route, stood in. */
async function openEditable(page: Page, onOperation: (route: Route) => Promise<void>) {
  const sent: unknown[][] = [];
  await loginAsDev(page);
  const drawn = await drawnData(page);
  const mapping: Record<string, Record<string, unknown>> = {
    StartEvent_1: { kind: "start_event", blueprint_path: "derived:start" },
  };
  STEPS.forEach((id, i) => {
    mapping[`Activity_${id}`] = { kind: "user_task", blueprint_path: `workflow.steps[${i}]`, performed_by: "" };
  });
  for (const id of drawn.objects) {
    mapping[id] = {
      kind: "data_object",
      blueprint_path: `artifacts.${artifactOf(id)}`,
      data_object: { id: artifactOf(id), label: "" },
    };
  }
  await page.route("**/api/sessions/ses_laskut/bpmn/mapping*", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ mapping, has_draft: true }) }),
  );
  await page.route("**/api/sessions/ses_laskut/blueprint/operations", (route) => {
    sent.push((route.request().postDataJSON() as { operations: unknown[] }).operations);
    return onOperation(route);
  });
  await openFlow(page);
  await unlockBpmnEditor(page);
  await expect(page.getByTestId("bpmn-panel")).toHaveAttribute("data-ops", "on", { timeout: 30_000 });
  await expect(page.locator('.bpmn-editable .djs-palette .entry[data-action="gaik-add-step"]')).toBeVisible();
  return { sent, drawn };
}

const refusedAs = (code: string, field?: string) => (route: Route) =>
  route.fulfill({
    status: 422,
    contentType: "application/json",
    body: JSON.stringify({ detail: { error: "invalid_operation", message: "no", field, code } }),
  });

const pad = (page: Page) => page.locator(".djs-context-pad .entry");
const shape = (page: Page, id: string) => page.locator(`.bpmn-editable .djs-element[data-element-id="${id}"]`);

/** Picks an element by its own hit area: a flow drawn across it can cover its middle. */
async function pick(page: Page, id: string) {
  await page.getByTestId("bpmn-zoom-controls").getByRole("button", { name: "Sovita näkymään" }).click();
  await shape(page, id).locator(".djs-hit").first().dispatchEvent("click");
  await expect(shape(page, id)).toHaveClass(/selected/);
}

test.describe("BPMN data objects", () => {
  test.use({ viewport: { width: 1600, height: 1100 } });
  test.beforeEach(async ({ request }) => {
    await resetMockSessions(request);
  });

  test("without wizard_api a data object has no tools and is not renamed in place", async ({ page }) => {
    test.setTimeout(90_000);
    const writes: string[] = [];
    page.on("request", (r) => {
      if (r.method() !== "GET" && /blueprint\/operations/.test(r.url())) writes.push(r.url());
    });
    await openFlow(page);
    await expect(page.getByTestId("bpmn-panel")).toHaveAttribute("data-ops", "off");
    const { objects, links } = await drawnData(page);
    expect(objects.length).toBeGreaterThan(0);
    await pick(page, objects[0]);
    await expect(pad(page)).toHaveCount(0);
    await shape(page, objects[0]).locator(".djs-hit").first().dispatchEvent("dblclick");
    await expect(page.locator(".djs-direct-editing-parent")).toBeHidden();
    // Nor an association.
    expect(links.length).toBeGreaterThan(0);
    await pick(page, links[0].id);
    await expect(pad(page)).toHaveCount(0);
    expect(writes).toEqual([]);
  });

  test("a data object's pad renames it in place: rename_data_object; a refusal names the field", async ({ page }) => {
    test.setTimeout(90_000);
    const { sent, drawn } = await openEditable(page, refusedAs("invalid", "label"));
    const object = drawn.objects[0];
    await pick(page, object);
    await expect(pad(page)).toHaveCount(2);
    const rename = page.locator('.djs-context-pad .entry[data-action="gaik-data-rename"]');
    await expect(rename).toHaveAttribute("title", "Nimeä dataobjekti uudelleen");
    await expect(page.locator('.djs-context-pad .entry[data-action="connect"]')).toHaveAttribute(
      "title",
      "Yhdistä vaiheeseen: vaihe käyttää dataobjektia",
    );
    // No Delete of the data object itself.
    await expect(page.locator('.djs-context-pad .entry[data-action="delete"]')).toHaveCount(0);
    await rename.click();
    const editor = page.locator(".djs-direct-editing-parent");
    await expect(editor).toBeVisible();
    await page.keyboard.press("ControlOrMeta+a");
    await page.keyboard.type("Laskun kentät");
    // Committed by picking something else.
    await page.getByTestId("bpmn-zoom-controls").getByRole("button", { name: "Sovita näkymään" }).click();
    await shape(page, "Activity_classify").locator(".djs-hit").first().dispatchEvent("click");
    await expect.poll(() => sent.length).toBe(1);
    expect(sent[0]).toEqual([{ op: "rename_data_object", artifact_id: artifactOf(object), label: "Laskun kentät" }]);
    await expect(page.getByTestId("bpmn-status")).toContainText("Muutosta ei tehty: tarkista dataobjektin nimi.");
  });

  test("a line from a data object to a step is link_data as an input; already linked says so", async ({ page }) => {
    test.setTimeout(90_000);
    const { sent, drawn } = await openEditable(page, refusedAs("already_linked", "artifact_id"));
    // A data object and a step that has no link to it yet.
    const object = drawn.links.find((l) => l.role === "input" && STEPS.includes(l.task.replace(/^Activity_/, "")))!.data;
    const step = STEPS.find((s) => !drawn.links.some((l) => l.data === object && l.task === `Activity_${s}`))!;
    await pick(page, object);
    await page.locator('.djs-context-pad .entry[data-action="connect"]').click();
    await shape(page, `Activity_${step}`).hover();
    await shape(page, `Activity_${step}`).click();
    await expect.poll(() => sent.length).toBe(1);
    expect(sent[0]).toEqual([{ op: "link_data", artifact_id: artifactOf(object), step_id: step, role: "input" }]);
    await expect(page.getByTestId("bpmn-status")).toContainText("vaihe on jo yhdistetty tähän dataobjektiin");
  });

  test("deleting a data association is unlink_data; the only producer of a data object says why", async ({
    page,
  }) => {
    test.setTimeout(90_000);
    const answers = [refusedAs("still_used", "artifact_id"), refusedAs("only_producer", "artifact_id")];
    const { sent, drawn } = await openEditable(page, (route) => answers[Math.min(sent.length - 1, 1)](route));
    const link = drawn.links.find((l) => l.role === "output" && STEPS.includes(l.task.replace(/^Activity_/, "")))!;
    await pick(page, link.id);
    await page.locator('.djs-context-pad .entry[data-action="delete"]').click();
    await expect.poll(() => sent.length).toBe(1);
    expect(sent[0]).toEqual([
      { op: "unlink_data", artifact_id: artifactOf(link.data), step_id: link.task.replace(/^Activity_/, ""), role: "output" },
    ]);
    await expect(page.getByTestId("bpmn-status")).toContainText("ainoa, joka tuottaa tämän dataobjektin");
    await expect(page.getByTestId("bpmn-status")).toContainText("Poista ensin se käyttö");
    // Used by no step, it still needs the step that makes it: the link stays.
    await expect(shape(page, link.id)).toBeVisible();
    await pick(page, link.id);
    await page.locator('.djs-context-pad .entry[data-action="delete"]').click();
    await expect.poll(() => sent.length).toBe(2);
    await expect(page.getByTestId("bpmn-status")).toContainText("joten yhteys pysyy");
  });
});
