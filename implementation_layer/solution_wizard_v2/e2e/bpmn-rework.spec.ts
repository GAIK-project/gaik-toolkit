import { test, expect, type Page, type Route } from "@playwright/test";
import { resetMockSessions } from "./helpers/mock";
import { loginAsDev, openAccountMenu } from "./helpers/auth";
import { openBpmnView, selectWorkspaceTab, setChatOpen, unlockBpmnEditor } from "./helpers/workspace";

/**
 * Rework and rejection paths on the BPMN canvas on the mock store. Without
 * wizard_api the canvas is read-only: no "Add rework path" on a step, no
 * tools on a path's element, no path dialog. With the server's mapping stood
 * in, a step's "Add rework path" opens the path dialog (a name, a condition,
 * and back to this step or an earlier one, or the end), which sends
 * `add_rework_path`; an element the mapping names as a path (`exception`)
 * gets Edit (prefilled, `update_rework_path` with what changed) and Remove
 * (`remove_rework_path`). That a path is kept over a reload is in
 * e2e/bpmn-rework-stack.spec.ts.
 */

const STEPS = ["ingest", "extract", "classify", "approve", "export"];

async function openFlow(page: Page) {
  await loginAsDev(page);
  await page.goto("/sessions/ses_laskut");
  await setChatOpen(page, false);
  await selectWorkspaceTab(page, "Työnkulku");
  await openBpmnView(page);
  await expect(page.locator('.bpmn-editable [data-element-id="Activity_classify"]')).toBeVisible({ timeout: 30_000 });
  await expect(page.locator(".bpmn-editable")).toHaveAttribute("aria-busy", "false");
}

/** The exclusive gateways the mock store draws. */
async function drawnGateways(page: Page): Promise<string[]> {
  const xml = await (await page.request.get("/api/sessions/ses_laskut/bpmn?data_objects=1")).text();
  return [...xml.matchAll(/<bpmn:exclusiveGateway id="([^"]+)"/g)].map((m) => m[1]);
}

/** wizard_api's mapping and operations route, stood in; the first gateway is mapped as `gateway`. */
async function openEditable(page: Page, gateway: Record<string, unknown>, onOperation: (route: Route) => Promise<void>) {
  const sent: unknown[][] = [];
  await loginAsDev(page);
  const gateways = await drawnGateways(page);
  expect(gateways.length).toBeGreaterThan(0);
  const mapping: Record<string, Record<string, unknown>> = {
    StartEvent_1: { kind: "start_event", blueprint_path: "derived:start" },
  };
  STEPS.forEach((id, i) => {
    mapping[`Activity_${id}`] = { kind: "user_task", blueprint_path: `workflow.steps[${i}]`, performed_by: "" };
  });
  mapping[gateways[0]] = gateway;
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
  return { sent, gateway: gateways[0] };
}

const refusedAs = (code: string, field?: string) => (route: Route) =>
  route.fulfill({
    status: 422,
    contentType: "application/json",
    body: JSON.stringify({ detail: { error: "invalid_operation", message: "no", field, code } }),
  });

const pad = (page: Page) => page.locator(".djs-context-pad .entry");

async function pickStep(page: Page, index: number) {
  await page.getByTestId("flow-step-list").locator("li").nth(index).getByRole("button").first().click();
  await page.getByTestId("bpmn-properties").getByRole("button", { name: "Sulje" }).click();
  await page.getByTestId("flow-step-list").locator("li").nth(index).getByRole("button").first().click();
}

async function pickGateway(page: Page, id: string) {
  await page.getByTestId("bpmn-zoom-controls").getByRole("button", { name: "Sovita näkymään" }).click();
  const gateway = page.locator(`.bpmn-editable .djs-shape[data-element-id="${id}"]`);
  // A flow drawn across the gateway can cover its middle: the click goes to the gateway itself.
  await gateway.locator(".djs-hit").first().dispatchEvent("click");
  await expect(gateway).toHaveClass(/selected/);
  return gateway;
}

const PATH = {
  id: "wrong_class",
  name: "Väärä luokka",
  attached_to: "approve",
  condition: "Luokka väärin",
  outcome: "loop_to:classify",
};

test.describe("BPMN rework paths", () => {
  test.use({ viewport: { width: 1600, height: 1100 } });
  test.beforeEach(async ({ request }) => {
    await resetMockSessions(request);
  });

  test("without wizard_api no path tools are offered: no Add rework path, no path tools, no dialog", async ({ page }) => {
    test.setTimeout(90_000);
    const writes: string[] = [];
    page.on("request", (r) => {
      if (r.method() !== "GET" && /blueprint\/operations/.test(r.url())) writes.push(r.url());
    });
    await openFlow(page);
    await expect(page.getByTestId("bpmn-panel")).toHaveAttribute("data-ops", "off");
    await page.getByTestId("flow-step-list").locator("li").nth(3).getByRole("button").first().click();
    await expect(page.getByTestId("bpmn-step-panel")).toBeVisible();
    await expect(page.locator('.djs-context-pad .entry[data-action="gaik-add-rework"]')).toHaveCount(0);
    await expect(page.locator('.djs-context-pad .entry[data-action^="gaik-rework"]')).toHaveCount(0);
    await page.getByTestId("bpmn-properties").getByRole("button", { name: "Sulje" }).click();
    const [gateway] = await drawnGateways(page);
    await pickGateway(page, gateway);
    await expect(pad(page)).toHaveCount(0);
    await expect(page.getByTestId("bpmn-rework-dialog")).toHaveCount(0);
    expect(writes).toEqual([]);
  });

  test("a step's Add rework path opens the path dialog, which sends add_rework_path; a refusal keeps it open and says why", async ({
    page,
  }) => {
    test.setTimeout(90_000);
    const { sent } = await openEditable(
      page,
      { kind: "approval_gateway", blueprint_path: "derived:approval_after:approve" },
      refusedAs("unknown_step", "outcome"),
    );
    await pickStep(page, 3);
    const add = page.locator('.djs-context-pad .entry[data-action="gaik-add-rework"]');
    await expect(add).toHaveAttribute("title", "Lisää korjauspolku");
    await add.click();
    const dialog = page.getByTestId("bpmn-rework-dialog");
    await expect(dialog).toBeVisible();
    await expect(dialog.getByRole("heading")).toHaveText("Lisää korjauspolku");
    const save = dialog.getByTestId("bpmn-rework-save");
    await expect(save).toBeDisabled();
    // Back to this step or an earlier one, or the end; nothing picked yet.
    const outcome = dialog.getByTestId("bpmn-rework-outcome");
    const options = await outcome
      .locator("option")
      .evaluateAll((els) => els.map((el) => (el as HTMLOptionElement).value));
    expect(options).toEqual(["", "loop_to:ingest", "loop_to:extract", "loop_to:classify", "loop_to:approve", "end"]);
    await expect(outcome.locator('option[value="loop_to:classify"]')).toHaveText("Takaisin vaiheeseen: Classification");
    await expect(dialog.getByTestId("bpmn-rework-condition")).toHaveAttribute("maxlength", "200");

    await dialog.getByTestId("bpmn-rework-name").fill("Väärä luokka");
    await expect(save).toBeDisabled();
    await outcome.selectOption("loop_to:classify");
    await expect(save).toBeEnabled();
    await dialog.getByTestId("bpmn-rework-condition").fill(" Luokka väärin ");
    await save.click();
    await expect.poll(() => sent.length).toBe(1);
    expect(sent[0]).toEqual([
      {
        op: "add_rework_path",
        attached_to: "approve",
        name: "Väärä luokka",
        condition: "Luokka väärin",
        outcome: "loop_to:classify",
      },
    ]);
    // Refused: the dialog stays with what was typed, and says why in the UI language.
    await expect(dialog.getByRole("alert")).toContainText("Muutosta ei tehty: tarkista polun jatko");
    await expect(dialog.getByTestId("bpmn-rework-name")).toHaveValue("Väärä luokka");
    await dialog.getByRole("button", { name: "Peruuta" }).click();
    await expect(dialog).toHaveCount(0);
    expect(sent).toHaveLength(1);
  });

  test("a path's element: Edit opens the dialog prefilled and sends what changed; Remove sends remove_rework_path", async ({
    page,
  }) => {
    test.setTimeout(90_000);
    const { sent, gateway } = await openEditable(
      page,
      { kind: "approval_gateway", blueprint_path: "derived:approval_after:approve", exception: PATH },
      refusedAs("invalid", "outcome"),
    );
    const shape = await pickGateway(page, gateway);
    await expect(shape).not.toHaveAttribute("data-gaik-derived", "true");
    const actions = await pad(page).evaluateAll((els) => els.map((el) => el.getAttribute("data-action")));
    expect(actions).toEqual(["gaik-rework-edit", "gaik-rework-remove"]);
    await expect(page.getByTestId("bpmn-derived-note")).toHaveCount(0);

    await page.locator('.djs-context-pad .entry[data-action="gaik-rework-edit"]').click();
    const dialog = page.getByTestId("bpmn-rework-dialog");
    await expect(dialog.getByRole("heading")).toHaveText("Muokkaa polkua");
    await expect(dialog.getByTestId("bpmn-rework-name")).toHaveValue("Väärä luokka");
    await expect(dialog.getByTestId("bpmn-rework-condition")).toHaveValue("Luokka väärin");
    await expect(dialog.getByTestId("bpmn-rework-outcome")).toHaveValue("loop_to:classify");
    // Saved unchanged: the dialog closes and nothing is sent.
    await dialog.getByTestId("bpmn-rework-save").click();
    await expect(dialog).toHaveCount(0);
    expect(sent).toHaveLength(0);
    await page.locator('.djs-context-pad .entry[data-action="gaik-rework-edit"]').click();
    await dialog.getByTestId("bpmn-rework-outcome").selectOption("end");
    await dialog.getByTestId("bpmn-rework-save").click();
    await expect.poll(() => sent.length).toBe(1);
    // Only what changed: the name and the condition stay out.
    expect(sent[0]).toEqual([{ op: "update_rework_path", exception_id: "wrong_class", outcome: "end" }]);
    await expect(dialog.getByRole("alert")).toContainText("Muutosta ei tehty");
    await dialog.getByRole("button", { name: "Peruuta" }).click();
    await expect(dialog).toHaveCount(0);

    // Another element first: the gateway is picked anew, and its pad opens again.
    await page.getByTestId("flow-step-list").locator("li").nth(0).getByRole("button").first().click();
    const picked = await pickGateway(page, gateway);
    // The Delete key does nothing on the approval gateway: its path goes with Remove only.
    // The keys go to the canvas once it has the focus.
    await page.locator('.bpmn-editable svg[tabindex="0"]').focus();
    await expect(picked).toHaveClass(/selected/);
    await page.keyboard.press("Delete");
    await page.waitForTimeout(500);
    expect(sent).toHaveLength(1);
    await expect(picked).toBeVisible();
    await page.locator('.djs-context-pad .entry[data-action="gaik-rework-remove"]').click();
    await expect.poll(() => sent.length).toBe(2);
    expect(sent[1]).toEqual([{ op: "remove_rework_path", exception_id: "wrong_class" }]);
  });

  test("the dialog in English", async ({ page }) => {
    test.setTimeout(90_000);
    await openEditable(
      page,
      { kind: "approval_gateway", blueprint_path: "derived:approval_after:approve" },
      refusedAs("invalid"),
    );
    await (await openAccountMenu(page)).locator('button[name="locale"][value="en"]').click();
    await expect(page.locator(".bpmn-editable .djs-palette .entry").nth(0)).toHaveAttribute(
      "title",
      "Add a step at the end of the process",
    );
    await page.getByTestId("flow-step-list").locator("li").nth(1).getByRole("button").first().click();
    const add = page.locator('.djs-context-pad .entry[data-action="gaik-add-rework"]');
    await expect(add).toHaveAttribute("title", "Add a rework path");
    await add.click();
    const dialog = page.getByTestId("bpmn-rework-dialog");
    await expect(dialog.getByRole("heading")).toHaveText("Add a rework path");
    await expect(dialog.getByTestId("bpmn-rework-outcome").locator("option").last()).toHaveText("The process ends");
    await expect(dialog.getByTestId("bpmn-rework-save")).toHaveText("Save the path");
    await dialog.getByRole("button", { name: "Cancel" }).click();
    await expect(dialog).toHaveCount(0);
  });
});
