import { test, expect, type Page, type Route } from "@playwright/test";
import { resetMockSessions } from "./helpers/mock";
import { loginAsDev, openAccountMenu } from "./helpers/auth";
import { openBpmnView, selectWorkspaceTab, setChatOpen, unlockBpmnEditor } from "./helpers/workspace";

/**
 * Business decisions on the BPMN canvas on the mock store. Without wizard_api
 * the canvas is read-only: no "Add decision after" on a step, no tools on a
 * gateway, no branch dialog. With the server's mapping stood in, a step's
 * "Add decision after" opens the branch dialog, which sends `add_decision`; a
 * business decision's gateway (mapped `decision_point`) gets Edit (the dialog
 * prefilled, `update_decision`) and Remove (`remove_decision`); a gateway the
 * generator draws by itself says why it has no tools. That a decision is kept
 * over a reload is in e2e/bpmn-decisions-stack.spec.ts.
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

type Mapping = Record<string, Record<string, unknown>>;

/** wizard_api's mapping and operations route, stood in; `gateway` is mapped as `kind`. */
async function openEditable(
  page: Page,
  gateway: (id: string) => Record<string, unknown>,
  onOperation: (route: Route) => Promise<void>,
) {
  const sent: unknown[][] = [];
  await loginAsDev(page);
  const gateways = await drawnGateways(page);
  expect(gateways.length).toBeGreaterThan(0);
  const mapping: Mapping = { StartEvent_1: { kind: "start_event", blueprint_path: "derived:start" } };
  STEPS.forEach((id, i) => {
    mapping[`Activity_${id}`] = { kind: "user_task", blueprint_path: `workflow.steps[${i}]`, performed_by: "" };
  });
  mapping[gateways[0]] = gateway(gateways[0]);
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
const refused = refusedAs("unknown_step", "target");

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

test.describe("BPMN decisions", () => {
  test.use({ viewport: { width: 1600, height: 1100 } });
  test.beforeEach(async ({ request }) => {
    await resetMockSessions(request);
  });

  test("without wizard_api no decision tools are offered: no Add decision, no gateway tools, no dialog", async ({
    page,
  }) => {
    test.setTimeout(90_000);
    const writes: string[] = [];
    page.on("request", (r) => {
      if (r.method() !== "GET" && /blueprint\/operations/.test(r.url())) writes.push(r.url());
    });
    await openFlow(page);
    await expect(page.getByTestId("bpmn-panel")).toHaveAttribute("data-ops", "off");
    await page.getByTestId("flow-step-list").locator("li").nth(1).getByRole("button").first().click();
    await expect(page.getByTestId("bpmn-step-panel")).toBeVisible();
    await expect(page.locator('.djs-context-pad .entry[data-action^="gaik-decision"]')).toHaveCount(0);
    await expect(page.locator('.djs-context-pad .entry[data-action="gaik-add-decision"]')).toHaveCount(0);
    await page.getByTestId("bpmn-properties").getByRole("button", { name: "Sulje" }).click();
    const [gateway] = await drawnGateways(page);
    await pickGateway(page, gateway);
    await expect(pad(page)).toHaveCount(0);
    await expect(page.getByTestId("bpmn-branch-dialog")).toHaveCount(0);
    expect(writes).toEqual([]);
  });

  test("a step's Add decision after opens the branch dialog, which sends add_decision; a refusal keeps it open and says why", async ({
    page,
  }) => {
    test.setTimeout(90_000);
    const { sent, gateway } = await openEditable(
      page,
      () => ({ kind: "approval_gateway", blueprint_path: "derived:approval_after:approve" }),
      refused,
    );

    // A gateway the generator draws by itself: no tools, and it says why.
    const derived = await pickGateway(page, gateway);
    await expect(derived).toHaveAttribute("data-gaik-derived", "true");
    await expect(pad(page)).toHaveCount(0);
    await expect(page.getByTestId("bpmn-derived-note")).toBeVisible();
    await page.getByTestId("bpmn-properties").getByRole("button", { name: "Sulje" }).click();

    await pickStep(page, 1);
    const add = page.locator('.djs-context-pad .entry[data-action="gaik-add-decision"]');
    await expect(add).toHaveAttribute("title", "Lisää päätös tämän jälkeen");
    await add.click();
    const dialog = page.getByTestId("bpmn-branch-dialog");
    await expect(dialog).toBeVisible();
    await expect(dialog.getByRole("heading")).toHaveText("Lisää päätös");
    const save = dialog.getByTestId("bpmn-branch-save");
    // Two branches to start with, none filled: nothing to save yet.
    await expect(dialog.getByTestId("bpmn-branch-condition")).toHaveCount(2);
    await expect(save).toBeDisabled();
    // The targets: every step and End (after the empty "pick one" entry of a new branch).
    const options = await dialog
      .getByTestId("bpmn-branch-target")
      .first()
      .locator("option")
      .evaluateAll((els) => els.map((el) => (el as HTMLOptionElement).value));
    expect(options).toEqual(["", ...STEPS, "end"]);

    await dialog.getByTestId("bpmn-branch-name").fill("Onko summa suuri?");
    await dialog.getByTestId("bpmn-branch-condition").nth(0).fill("Yli 10 000 €");
    await dialog.getByTestId("bpmn-branch-target").nth(0).selectOption("approve");
    await dialog.getByTestId("bpmn-branch-condition").nth(1).fill("Muuten");
    await dialog.getByTestId("bpmn-branch-target").nth(1).selectOption("approve");
    // All branches to one place decide nothing.
    await expect(save).toBeDisabled();
    await expect(dialog.getByTestId("bpmn-branch-same-target")).toBeVisible();
    await dialog.getByTestId("bpmn-branch-target").nth(1).selectOption("end");
    await expect(save).toBeEnabled();
    // Up to five branches; a third one added and removed again; never fewer than two.
    for (let i = 0; i < 3; i += 1) await dialog.getByTestId("bpmn-branch-add").click();
    await expect(dialog.getByTestId("bpmn-branch-condition")).toHaveCount(5);
    await expect(dialog.getByTestId("bpmn-branch-add")).toBeDisabled();
    for (let i = 0; i < 3; i += 1) await dialog.getByTestId("bpmn-branch-remove").last().click();
    await expect(dialog.getByTestId("bpmn-branch-condition")).toHaveCount(2);
    await expect(dialog.getByTestId("bpmn-branch-remove").first()).toBeDisabled();
    await expect(dialog.getByTestId("bpmn-branch-condition").first()).toHaveAttribute("maxlength", "200");

    await save.click();
    await expect.poll(() => sent.length).toBe(1);
    expect(sent[0]).toEqual([
      {
        op: "add_decision",
        after: "extract",
        name: "Onko summa suuri?",
        branches: [
          { condition: "Yli 10 000 €", target: "approve" },
          { condition: "Muuten", target: "end" },
        ],
      },
    ]);
    // Refused: the dialog stays with what was typed, and says why in the UI language.
    await expect(dialog.getByRole("alert")).toContainText("Muutosta ei tehty");
    await expect(dialog.getByTestId("bpmn-branch-name")).toHaveValue("Onko summa suuri?");
    await dialog.getByRole("button", { name: "Peruuta" }).click();
    await expect(dialog).toHaveCount(0);
    expect(sent).toHaveLength(1);
  });

  test("a business decision's gateway: Edit opens the dialog prefilled and sends update_decision; Remove sends remove_decision", async ({
    page,
  }) => {
    test.setTimeout(90_000);
    const decision = {
      id: "big",
      name: "Iso summa?",
      after: "extract",
      branches: [
        { condition: "Kyllä", target: "approve" },
        { condition: "Ei", target: "end" },
      ],
    };
    const { sent, gateway } = await openEditable(
      page,
      () => ({ kind: "decision_point", blueprint_path: "business_process.decision_points[0]", decision }),
      refusedAs("cycle"),
    );
    const shape = await pickGateway(page, gateway);
    await expect(shape).not.toHaveAttribute("data-gaik-derived", "true");
    const actions = await pad(page).evaluateAll((els) => els.map((el) => el.getAttribute("data-action")));
    expect(actions).toEqual(["gaik-decision-edit", "gaik-decision-remove"]);
    await expect(page.getByTestId("bpmn-derived-note")).toHaveCount(0);

    await page.locator('.djs-context-pad .entry[data-action="gaik-decision-edit"]').click();
    const dialog = page.getByTestId("bpmn-branch-dialog");
    await expect(dialog.getByRole("heading")).toHaveText("Muokkaa päätöstä");
    await expect(dialog.getByTestId("bpmn-branch-name")).toHaveValue("Iso summa?");
    await expect(dialog.getByTestId("bpmn-branch-condition").nth(1)).toHaveValue("Ei");
    await expect(dialog.getByTestId("bpmn-branch-target").nth(0)).toHaveValue("approve");
    // Saved unchanged: the dialog closes and nothing is sent.
    await dialog.getByTestId("bpmn-branch-save").click();
    await expect(dialog).toHaveCount(0);
    expect(sent).toHaveLength(0);
    await page.locator('.djs-context-pad .entry[data-action="gaik-decision-edit"]').click();
    await expect(dialog.getByTestId("bpmn-branch-name")).toHaveValue("Iso summa?");
    await dialog.getByTestId("bpmn-branch-add").click();
    await dialog.getByTestId("bpmn-branch-condition").nth(2).fill("Ehkä");
    await dialog.getByTestId("bpmn-branch-target").nth(2).selectOption("classify");
    await dialog.getByTestId("bpmn-branch-save").click();
    await expect.poll(() => sent.length).toBe(1);
    // Only what changed: the name stays out.
    expect(sent[0]).toEqual([
      {
        op: "update_decision",
        decision_id: "big",
        branches: [...decision.branches, { condition: "Ehkä", target: "classify" }],
      },
    ]);
    // A loop is said as one, not as a field to check.
    await expect(dialog.getByRole("alert")).toContainText("Haara ei voi johtaa taaksepäin");
    await dialog.getByRole("button", { name: "Peruuta" }).click();
    await expect(dialog).toHaveCount(0);

    // Another element first: the gateway is picked anew, and its pad opens again.
    await page.getByTestId("flow-step-list").locator("li").nth(0).getByRole("button").first().click();
    await pickGateway(page, gateway);
    await page.locator('.djs-context-pad .entry[data-action="gaik-decision-remove"]').click();
    await expect.poll(() => sent.length).toBe(2);
    expect(sent[1]).toEqual([{ op: "remove_decision", decision_id: "big" }]);
  });

  test("the dialog in English", async ({ page }) => {
    test.setTimeout(90_000);
    await openEditable(
      page,
      () => ({ kind: "approval_gateway", blueprint_path: "derived:approval_after:approve" }),
      refused,
    );
    // The language is chosen in the menu of the account row at the sidebar's foot.
    await (await openAccountMenu(page)).locator('button[name="locale"][value="en"]').click();
    await expect(page.locator(".bpmn-editable .djs-palette .entry").nth(0)).toHaveAttribute(
      "title",
      "Add a step at the end of the process",
    );
    await page.getByTestId("flow-step-list").locator("li").nth(1).getByRole("button").first().click();
    const add = page.locator('.djs-context-pad .entry[data-action="gaik-add-decision"]');
    await expect(add).toHaveAttribute("title", "Add a decision after this");
    await add.click();
    const dialog = page.getByTestId("bpmn-branch-dialog");
    await expect(dialog.getByRole("heading")).toHaveText("Add a decision");
    await expect(dialog.getByTestId("bpmn-branch-target").first().locator("option").last()).toHaveText("End");
    await expect(dialog.getByTestId("bpmn-branch-save")).toHaveText("Save the decision");
    await dialog.getByRole("button", { name: "Cancel" }).click();
    await expect(dialog).toHaveCount(0);
  });
});
