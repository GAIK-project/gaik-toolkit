import { test, expect, type Page, type Route } from "@playwright/test";
import { loginAsDev } from "./helpers/auth";
import { resetMockSessions } from "./helpers/mock";
import { openBlueprintEditor, openBpmnView, selectWorkspaceTab, setChatOpen } from "./helpers/workspace";

/**
 * The BPMN editor's step panel and its step type menu on the mock store. With
 * no wizard_api the canvas is read-only, and so is the panel: its fields are
 * shown and cannot be changed. What the panel and the menu send is checked
 * with the server's mapping and answers stood in by the test; that the edits
 * are kept over a reload is in e2e/bpmn-step-panel-stack.spec.ts.
 */

type Body = { base_version: number; operations: { op: string; [key: string]: unknown }[] };
type MockBlueprint = { goal: string; steps: { id: string; name: string; type: string; component?: string }[] };

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

/** The session's blueprint, read from the form's JSON. */
async function readBlueprint(page: Page): Promise<MockBlueprint> {
  await openBlueprintEditor(page);
  await page.getByTestId("blueprint-json-toggle").click();
  const blueprint = JSON.parse(await page.getByTestId("blueprint-json-editor").inputValue()) as MockBlueprint;
  await page.getByTestId("blueprint-done").click();
  return blueprint;
}

/** wizard_api's mapping (the five tasks are `workflow.steps[0..4]`) and its operations, stood in. */
async function standInForWizardApi(page: Page, operations: (route: Route, body: Body) => Promise<void>) {
  const mapping: Record<string, { kind: string; blueprint_path: string }> = {
    StartEvent_1: { kind: "start_event", blueprint_path: "derived:start" },
    Activity_submit_finance_system: { kind: "send_task", blueprint_path: "derived:submit:finance_system" },
  };
  STEPS.forEach((id, i) => {
    mapping[`Activity_${id}`] = { kind: "user_task", blueprint_path: `workflow.steps[${i}]` };
  });
  await page.route("**/api/sessions/ses_laskut/bpmn/mapping*", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ mapping, has_draft: true }) }),
  );
  await page.route("**/api/sessions/ses_laskut/blueprint/operations", (route) =>
    operations(route, route.request().postDataJSON() as Body),
  );
}

/** A made edit's answer: the session on the version sent, and what the edit left for the wizard. */
function made(blueprint: MockBlueprint, body: Body, needsAttention: string[] = []) {
  return {
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({
      session: { id: "ses_laskut", active_version: body.base_version, blueprint },
      warnings: [],
      needs_attention: needsAttention,
      bpmn_changed: true,
    }),
  };
}

/** One chat turn with a canned answer: the page takes the session's current blueprint after it. */
async function chatTurn(page: Page) {
  await page.route("**/api/sessions/*/chat", (route) =>
    route.request().method() === "POST"
      ? route.fulfill({
          status: 200,
          contentType: "text/event-stream",
          body: `data: ${JSON.stringify({ delta: "Selvä." })}\n\ndata: ${JSON.stringify({ done: true })}\n\n`,
        })
      : route.continue(),
  );
  await setChatOpen(page, true);
  const field = page.locator('textarea[name="message"]');
  await field.fill("Poista hyväksyntä");
  await field.press("Enter");
  await expect(page.locator('[data-testid="chat-message"][data-role="assistant"]').last()).toContainText("Selvä.");
  await setChatOpen(page, false);
}

const rows = (page: Page) => page.getByTestId("flow-step-list").locator("li");
const isWrite = (r: { url(): string; method(): string }) =>
  r.method() !== "GET" && /\/api\/sessions\/[^/]+\/(bpmn\/sync|bpmn\/layout|blueprint\/operations|blueprint\/undo)/.test(r.url());

test.describe("BPMN step panel", () => {
  test.beforeEach(async ({ request }) => {
    await resetMockSessions(request);
  });

  test("without wizard_api the step panel opens read-only and saves nothing; it closes when its step goes", async ({
    page,
  }) => {
    test.setTimeout(150_000);
    const writes: string[] = [];
    page.on("request", (r) => {
      if (isWrite(r)) writes.push(`${r.method()} ${r.url()}`);
    });
    await openFlow(page);
    const blueprint = await readBlueprint(page);
    await selectWorkspaceTab(page, "Työnkulku");
    await expect(page.getByTestId("bpmn-panel")).toHaveAttribute("data-ops", "off");

    await rows(page).nth(3).getByRole("button").first().click();
    const panel = page.getByTestId("bpmn-step-panel");
    await expect(panel).toBeVisible();
    const name = page.getByTestId("bpmn-property-name");
    const description = page.getByTestId("bpmn-step-description");
    const type = page.getByTestId("bpmn-step-type");
    await expect(name).toHaveValue("Approval");
    await expect(description).toHaveValue("Accountant confirms the classification");
    await expect(type).toHaveValue("human_review");
    for (const field of [name, description, type]) await expect(field).toBeDisabled();
    await expect(description).toHaveAttribute("maxlength", "2000");
    await expect(page.getByTestId("bpmn-step-description-count")).toHaveText("38 / 2000 merkkiä");
    // No type menu on a read-only canvas.
    await expect(page.locator(".bpmn-editable .djs-context-pad .entry")).toHaveCount(0);

    // The step is removed in a version the chat brings: its panel closes with it.
    const res = await page.request.patch("/api/sessions/ses_laskut/blueprint", {
      data: { content: { ...blueprint, steps: blueprint.steps.filter((s) => s.id !== "approve") }, note: "e2e" },
    });
    expect(res.status()).toBe(200);
    await chatTurn(page);
    await expect(page.locator('.bpmn-editable [data-element-id="Activity_approve"]')).toHaveCount(0, {
      timeout: 30_000,
    });
    await expect(panel).toHaveCount(0);
    await expect(page.getByTestId("bpmn-properties")).toHaveCount(0);
    expect(writes).toEqual([]);
  });

  test("the type menu is on steps only, marks the step's type and sends set_step_type; bpmn-js's replace menu stays off", async ({
    page,
  }) => {
    test.setTimeout(150_000);
    await openFlow(page);
    const blueprint = await readBlueprint(page);
    const sent: Body[] = [];
    await standInForWizardApi(page, async (route, body) => {
      sent.push(body);
      // The step is an automated task now, and has no component: the wizard is to add one.
      await route.fulfill(made(blueprint, body, ["approve: needs a component"]));
    });
    await page.reload();
    await setChatOpen(page, false);
    await selectWorkspaceTab(page, "Työnkulku");
    await openBpmnView(page);
    await expect(page.getByTestId("bpmn-panel")).toHaveAttribute("data-ops", "on", { timeout: 30_000 });

    await rows(page).nth(3).getByRole("button").first().click();
    const pad = page.locator(".djs-context-pad .entry");
    await expect(pad).toHaveCount(9);
    const change = page.locator('.djs-context-pad .entry[data-action="gaik-step-type"]');
    await expect(change).toHaveAttribute("title", "Vaihda vaiheen tyyppi");
    await change.click();
    const menu = page.locator('.djs-popup-parent[data-popup="gaik-step-type"]');
    await expect(menu.locator(".djs-popup")).toBeVisible();
    await expect(menu.locator(".entry")).toHaveText(["Syöte tai tulos", "Tekoäly", "Ihmisen tarkistus"]);
    // The step's own type is shown and is no edit.
    await expect(menu.locator('.entry[data-id="gaik-step-type-human_review"]')).toHaveAttribute("aria-disabled", "true");
    await menu.locator('.entry[data-id="gaik-step-type-automated_task"]').click();
    await expect.poll(() => sent.length).toBe(1);
    expect(sent[0]).toEqual({
      base_version: 7,
      operations: [{ op: "set_step_type", step_id: "approve", type: "automated_task" }],
    });
    await expect(menu).toHaveCount(0);
    // The panel says what the edit left: an AI step that needs a component.
    await expect(page.getByTestId("bpmn-step-type")).toHaveValue("automated_task");
    await expect(page.getByTestId("bpmn-step-needs-component")).toHaveText(
      "Tekoälyvaihe tarvitsee komponentin: pyydä wizardia valitsemaan se.",
    );

    // The R key (bpmn-js's "replace element") opens no menu.
    await rows(page).nth(2).getByRole("button").first().click();
    await page.locator('.bpmn-editable svg[tabindex="0"]').focus();
    await page.keyboard.press("r");
    await expect(page.locator(".djs-popup-parent")).toHaveCount(0);

    // What the blueprint draws from elsewhere has no type menu.
    await page.getByTestId("bpmn-properties").getByRole("button", { name: "Sulje" }).click();
    await page.getByTestId("bpmn-zoom-controls").getByRole("button", { name: "Sovita näkymään" }).click();
    await page.locator('.bpmn-editable [data-element-id="Activity_submit_finance_system"]').click();
    await expect(page.locator('.djs-context-pad .entry[data-action="gaik-step-type"]')).toHaveCount(0);
    expect(sent).toHaveLength(1);
  });

  test("the panel saves a step's name, description and type on Enter or leaving a field, each save one edit; Escape takes a change back", async ({
    page,
  }) => {
    test.setTimeout(150_000);
    await openFlow(page);
    const blueprint = await readBlueprint(page);
    const sent: Body[] = [];
    let release: (() => void) | null = null;
    await standInForWizardApi(page, async (route, body) => {
      sent.push(body);
      if (sent.length === 2) await new Promise<void>((resolve) => (release = resolve));
      await route.fulfill(made(blueprint, body));
    });
    await page.reload();
    await setChatOpen(page, false);
    await selectWorkspaceTab(page, "Työnkulku");
    await openBpmnView(page);
    await expect(page.getByTestId("bpmn-panel")).toHaveAttribute("data-ops", "on", { timeout: 30_000 });

    await rows(page).nth(2).getByRole("button").first().click();
    const name = page.getByTestId("bpmn-property-name");
    const description = page.getByTestId("bpmn-step-description");
    const type = page.getByTestId("bpmn-step-type");
    await expect(name).toBeEnabled();
    await expect(name).toHaveValue("Classification");
    await expect(description).toHaveValue("Suggest cost center and account");
    await expect(type).toHaveValue("automated_task");

    // Escape takes the typed change back; nothing is sent.
    await description.fill("Something else");
    await description.press("Escape");
    await expect(description).toHaveValue("Suggest cost center and account");
    await description.blur();

    // Enter saves the name.
    await name.fill("Cost centre proposal");
    await name.press("Enter");
    await expect.poll(() => sent.length).toBe(1);
    expect(sent[0].operations).toEqual([{ op: "rename_step", step_id: "classify", name: "Cost centre proposal" }]);
    await expect(page.getByTestId("bpmn-status")).toContainText("Tallennettu");
    await expect(name).toBeEnabled();

    // Leaving the description saves it; while the edit is on its way the fields wait.
    await description.fill("Proposes the cost centre and the account.");
    await expect(page.getByTestId("bpmn-step-description-count")).toHaveText("41 / 2000 merkkiä");
    await description.blur();
    await expect.poll(() => sent.length).toBe(2);
    expect(sent[1].operations).toEqual([
      { op: "set_step_description", step_id: "classify", description: "Proposes the cost centre and the account." },
    ]);
    for (const field of [name, description, type]) await expect(field).toBeDisabled();
    release!();
    await expect(name).toBeEnabled();

    // The type saves when it is picked.
    await type.selectOption("human_review");
    await expect.poll(() => sent.length).toBe(3);
    expect(sent[2].operations).toEqual([{ op: "set_step_type", step_id: "classify", type: "human_review" }]);
    await expect(type).toBeEnabled();

    // A description longer than 2000 characters is cut at the field.
    await description.fill("x".repeat(2100));
    await expect(description).toHaveValue("x".repeat(2000));
    await name.click();
    await expect.poll(() => sent.length).toBe(4);
    expect(sent[3].operations).toEqual([
      { op: "set_step_description", step_id: "classify", description: "x".repeat(2000) },
    ]);
  });
  test("a type picked while the edit is refused as changed elsewhere is made again on the newer version", async ({
    page,
  }) => {
    test.setTimeout(150_000);
    await openFlow(page);
    const blueprint = await readBlueprint(page);
    const sent: Body[] = [];
    let release!: () => void;
    const held = new Promise<void>((resolve) => (release = resolve));
    await standInForWizardApi(page, async (route, body) => {
      sent.push(body);
      if (sent.length === 1) {
        // Held while a version is written elsewhere, then refused as changed elsewhere.
        await held;
        const refused = { detail: { error: "changed_elsewhere", message: "reload" } };
        await route.fulfill({ status: 409, contentType: "application/json", body: JSON.stringify(refused) });
        return;
      }
      await route.fulfill(made(blueprint, body));
    });
    await page.reload();
    await setChatOpen(page, false);
    await selectWorkspaceTab(page, "Työnkulku");
    await openBpmnView(page);
    await expect(page.getByTestId("bpmn-panel")).toHaveAttribute("data-ops", "on", { timeout: 30_000 });

    await rows(page).nth(0).getByRole("button").first().click();
    const type = page.getByTestId("bpmn-step-type");
    await expect(type).toHaveValue("user_task");
    await type.selectOption("human_review");
    await expect.poll(() => sent.length).toBe(1);
    expect(sent[0]).toEqual({
      base_version: 7,
      operations: [{ op: "set_step_type", step_id: "ingest", type: "human_review" }],
    });
    // Meanwhile version 8 is written elsewhere; the type change is refused.
    const res = await page.request.patch("/api/sessions/ses_laskut/blueprint", {
      data: { content: { ...blueprint, goal: `${blueprint.goal} Reviewed weekly.` }, note: "e2e: written elsewhere" },
    });
    expect(res.status()).toBe(200);
    release();
    await expect(page.getByTestId("bpmn-changed-elsewhere")).toBeVisible();
    // Once the page has version 8, the type change is made again on it.
    await expect.poll(() => sent.length, { timeout: 20_000 }).toBe(2);
    expect(sent[1]).toEqual({
      base_version: 8,
      operations: [{ op: "set_step_type", step_id: "ingest", type: "human_review" }],
    });
    await expect(page.getByTestId("bpmn-status")).toContainText("Tallennettu");
  });

  test("edits of two steps kept over a refusal are both made once the page has the newer version", async ({ page }) => {
    test.setTimeout(150_000);
    await openFlow(page);
    const blueprint = await readBlueprint(page);
    const sent: Body[] = [];
    let release!: () => void;
    const held = new Promise<void>((resolve) => (release = resolve));
    await standInForWizardApi(page, async (route, body) => {
      sent.push(body);
      if (sent.length === 1) {
        await held;
        const refused = { detail: { error: "changed_elsewhere", message: "reload" } };
        await route.fulfill({ status: 409, contentType: "application/json", body: JSON.stringify(refused) });
        return;
      }
      await route.fulfill(made(blueprint, body));
    });
    await page.reload();
    await setChatOpen(page, false);
    await selectWorkspaceTab(page, "Työnkulku");
    await openBpmnView(page);
    await expect(page.getByTestId("bpmn-panel")).toHaveAttribute("data-ops", "on", { timeout: 30_000 });

    // Step A is renamed; the edit is held while version 8 is written elsewhere.
    await rows(page).nth(0).getByRole("button").first().click();
    const name = page.getByTestId("bpmn-property-name");
    await expect(name).toBeEnabled();
    await name.fill("Ingest renamed");
    await name.press("Enter");
    await expect.poll(() => sent.length).toBe(1);
    const res = await page.request.patch("/api/sessions/ses_laskut/blueprint", {
      data: { content: { ...blueprint, goal: `${blueprint.goal} Reviewed weekly.` }, note: "e2e: written elsewhere" },
    });
    expect(res.status()).toBe(200);
    // The page's read of version 8 is held too, so step B is edited before the page has it.
    let releaseRefresh!: () => void;
    const refreshHeld = new Promise<void>((resolve) => (releaseRefresh = resolve));
    await page.route(
      (url) => url.pathname === "/sessions/ses_laskut",
      async (route) => {
        if (route.request().headers()["rsc"] === "1") await refreshHeld;
        await route.fallback();
      },
    );
    release();
    await expect(page.getByTestId("bpmn-changed-elsewhere")).toBeVisible();

    // Step B's description is given while the canvas waits for version 8.
    await rows(page).nth(1).getByRole("button").first().click();
    const description = page.getByTestId("bpmn-step-description");
    await expect(description).toBeEnabled();
    await description.fill("Reads the invoice fields.");
    await description.blur();
    await page.waitForTimeout(500);
    expect(sent.length).toBe(1);

    releaseRefresh();
    // Both kept edits go out on version 8: B's did not replace A's.
    await expect.poll(() => sent.length, { timeout: 20_000 }).toBeGreaterThanOrEqual(2);
    const resent = sent.slice(1).flatMap((body) => {
      expect(body.base_version).toBe(8);
      return body.operations;
    });
    expect(resent).toEqual(
      expect.arrayContaining([
        { op: "rename_step", step_id: "ingest", name: "Ingest renamed" },
        { op: "set_step_description", step_id: "extract", description: "Reads the invoice fields." },
      ]),
    );
    await expect(page.getByTestId("bpmn-status")).toContainText("Tallennettu");
  });

  test("a refusal that comes after the page already read the newer version does not hold later saves back", async ({
    page,
  }) => {
    test.setTimeout(150_000);
    await openFlow(page);
    const blueprint = await readBlueprint(page);
    const sent: Body[] = [];
    let release!: () => void;
    const held = new Promise<void>((resolve) => (release = resolve));
    await standInForWizardApi(page, async (route, body) => {
      sent.push(body);
      if (sent.length === 1) {
        await held;
        const refused = { detail: { error: "changed_elsewhere", message: "reload" } };
        await route.fulfill({ status: 409, contentType: "application/json", body: JSON.stringify(refused) });
        return;
      }
      await route.fulfill(made(blueprint, body));
    });
    await page.reload();
    await setChatOpen(page, false);
    await selectWorkspaceTab(page, "Työnkulku");
    await openBpmnView(page);
    await expect(page.getByTestId("bpmn-panel")).toHaveAttribute("data-ops", "on", { timeout: 30_000 });

    await rows(page).nth(0).getByRole("button").first().click();
    const type = page.getByTestId("bpmn-step-type");
    await expect(type).toHaveValue("user_task");
    await type.selectOption("human_review");
    await expect.poll(() => sent.length).toBe(1);
    expect(sent[0].base_version).toBe(7);
    // Version 8 is written elsewhere, and the page reads it (a chat turn) while the edit is on its way.
    const res = await page.request.patch("/api/sessions/ses_laskut/blueprint", {
      data: { content: { ...blueprint, goal: `${blueprint.goal} Reviewed weekly.` }, note: "e2e: written elsewhere" },
    });
    expect(res.status()).toBe(200);
    const pageRead = page.waitForResponse(
      (r) => new URL(r.url()).pathname === "/sessions/ses_laskut" && r.request().headers()["rsc"] === "1",
    );
    await chatTurn(page);
    await pageRead;
    // The page has version 8 before the refusal of the edit made on 7 comes.
    await page.waitForTimeout(1_000);
    release();
    // No newer version comes after the refusal: the kept type goes out on version 8 at once.
    await expect.poll(() => sent.length, { timeout: 20_000 }).toBe(2);
    expect(sent[1]).toEqual({
      base_version: 8,
      operations: [{ op: "set_step_type", step_id: "ingest", type: "human_review" }],
    });
    await expect(page.getByTestId("bpmn-status")).toContainText("Tallennettu");
  });
});
