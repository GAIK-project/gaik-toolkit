import { test, expect, type Page, type Route } from "@playwright/test";
import { loginAsDev, openAccountMenu } from "./helpers/auth";
import { resetMockSessions } from "./helpers/mock";
import {
  openBlueprintEditor,
  openBpmnView,
  selectWorkspaceTab,
  setChatOpen,
  unlockBpmnEditor,
} from "./helpers/workspace";

/**
 * The Workflow tab's BPMN editor ("Avaa BPMN-kaaviona") on the mock store:
 * the process steps beside the diagram, the view controls, and what the
 * canvas does without wizard_api. Edits on the canvas are operations on the
 * agent's blueprint, which only wizard_api applies, so here the diagram is
 * read-only and says so (the mapping and operation routes answer 503
 * needs_wizard_api). The edits themselves, each kept over a reload, are in
 * e2e/bpmn-editing-stack.spec.ts. The tools the editor offers are checked
 * here with the server's mapping and answers stood in by the test. The tab
 * opens on the simple flow, which e2e/workflow-flow-view.spec.ts covers.
 */

const canvas = (page: Page) => page.locator(".bpmn-editable .djs-container");
const zoomLevel = async (page: Page) =>
  Number((await page.getByTestId("bpmn-zoom-level").innerText()).replace(/[^\d]/g, ""));

async function openFlow(page: Page, sessionId = "ses_laskut") {
  await loginAsDev(page);
  await page.goto(`/sessions/${sessionId}`);
  // The session waits on a gate, so the chat is open and the tab is narrow:
  // these tests are about the tab at its full width.
  await setChatOpen(page, false);
  await selectWorkspaceTab(page, "Työnkulku");
  await openBpmnView(page);
}

/**
 * The diagram is on the canvas. ses_laskut stands after Gate 2, where the
 * canvas opens locked each time the tab is opened: the lock is opened here
 * unless the test is about it (`edit: false`).
 */
async function waitForDiagram(page: Page, { edit = true }: { edit?: boolean } = {}) {
  if (edit) await unlockBpmnEditor(page);
  await expect(page.locator('.bpmn-editable [data-element-id="Activity_classify"]')).toBeVisible({
    timeout: 30_000,
  });
  await expect(page.locator(".bpmn-editable")).toHaveAttribute("aria-busy", "false");
}

/** The chat references the page asks for, read back with `window.__refs`. */
async function recordChatReferences(page: Page) {
  await page.evaluate(() => {
    const w = window as unknown as { __refs: unknown[] };
    w.__refs = [];
    window.addEventListener("gaik-wizard:chat-reference", (e) => w.__refs.push((e as CustomEvent).detail));
  });
}
const chatReferences = (page: Page) =>
  page.evaluate(() => (window as unknown as { __refs: unknown[] }).__refs);

/** A request that would change the blueprint or the layout from the canvas. */
const isCanvasWrite = (r: { url(): string; method(): string }) =>
  r.method() !== "GET" &&
  /\/api\/sessions\/[^/]+\/(bpmn\/sync|bpmn\/layout|blueprint\/operations|blueprint\/undo)/.test(r.url());

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
  await field.fill("Lisää vaihe");
  await field.press("Enter");
  await expect(page.locator('[data-testid="chat-message"][data-role="assistant"]').last()).toContainText("Selvä.");
  await setChatOpen(page, false);
}

/**
 * wizard_api's mapping for ses_laskut's diagram, stood in by the test: the
 * five tasks are `workflow.steps[0..4]`, the rest is drawn from elsewhere.
 * With it the editor opens with its tools; `operations` answers the edits.
 * `hasDraft: false` is a session whose agent has not written its draft yet;
 * `steps` the step ids the mapping is drawn for, read at each request.
 */
async function standInForWizardApi(
  page: Page,
  operations: (route: Route, body: { base_version: number; operations: unknown[] }) => Promise<void>,
  {
    hasDraft = true,
    steps = () => ["ingest", "extract", "classify", "approve", "export"],
  }: { hasDraft?: boolean; steps?: () => string[] } = {},
) {
  const mappingNow = () => {
    const mapping: Record<string, { kind: string; blueprint_path: string }> = {
      StartEvent_1: { kind: "start_event", blueprint_path: "derived:start" },
      Activity_submit_finance_system: { kind: "send_task", blueprint_path: "derived:submit:finance_system" },
    };
    steps().forEach((id, i) => {
      mapping[`Activity_${id}`] = { kind: "user_task", blueprint_path: `workflow.steps[${i}]` };
    });
    return mapping;
  };
  await page.route("**/api/sessions/ses_laskut/bpmn/mapping*", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ mapping: mappingNow(), has_draft: hasDraft }),
    }),
  );
  await page.route("**/api/sessions/ses_laskut/blueprint/operations", (route) =>
    operations(route, route.request().postDataJSON() as { base_version: number; operations: unknown[] }),
  );
}

test.describe("Workflow tab", () => {
  test.beforeEach(async ({ request }) => {
    await resetMockSessions(request);
  });


  test("opens readable with one group of view controls, and a resize keeps the view the user chose", async ({
    page,
  }) => {
    await openFlow(page);
    await waitForDiagram(page);

    // One group: zoom out, the level (a figure), zoom in, fit, the large view. No mode pair, theme or save button;
    // the minimap is part of the canvas, always open, not a control in the group.
    const controls = page.getByTestId("bpmn-zoom-controls");
    await expect(controls.getByRole("button")).toHaveCount(4);
    await expect(page.getByRole("button", { name: /Koko prosessi|Luettava/ })).toHaveCount(0);
    await expect(page.locator(".djs-minimap")).toHaveCount(1);
    await expect(page.getByTestId("bpmn-save")).toHaveCount(0);

    // The invoice process does not fit readably: it opens at the readable zoom, start event in view.
    await expect.poll(() => zoomLevel(page)).toBe(72);
    await expect(page.locator('.bpmn-editable [data-element-id^="StartEvent"]').first()).toBeInViewport();

    // "Sovita näkymään" shows all of it, inside the canvas.
    await controls.getByRole("button", { name: "Sovita näkymään" }).click();
    const fitted = await zoomLevel(page);
    expect(fitted).toBeLessThan(72);
    const box = (await canvas(page).boundingBox())!;
    for (const id of ["Activity_ingest", "Activity_export"]) {
      const shape = (await page.locator(`.bpmn-editable [data-element-id="${id}"]`).boundingBox())!;
      expect(shape.x).toBeGreaterThanOrEqual(box.x);
      expect(shape.x + shape.width).toBeLessThanOrEqual(box.x + box.width);
      expect(shape.y + shape.height).toBeLessThanOrEqual(box.y + box.height);
    }

    // A larger window fits again (beside the phase rail the fit is limited by the
    // canvas's width); a zoom the user picked stays through the next resize.
    await page.setViewportSize({ width: 1600, height: 1000 });
    await expect.poll(() => zoomLevel(page)).toBeGreaterThan(fitted);
    await controls.getByRole("button", { name: "Lähennä" }).click();
    const picked = await zoomLevel(page);
    await page.setViewportSize({ width: 1280, height: 720 });
    // Once the canvas has its new size and the page has drawn it twice (a
    // re-fit would have run by then), the zoom is still the one picked.
    await expect
      .poll(() => page.locator(".bpmn-editable").evaluate((el) => el.getBoundingClientRect().right))
      .toBeLessThanOrEqual(1280);
    await page.evaluate(() => new Promise((done) => requestAnimationFrame(() => requestAnimationFrame(done))));
    expect(await zoomLevel(page)).toBe(picked);
  });

  test("lists the process steps beside the diagram; a row and its task select each other", async ({ page }) => {
    await openFlow(page);
    await waitForDiagram(page);

    await expect(page.getByRole("heading", { name: "Prosessin vaiheet (5)" })).toBeVisible();
    const rows = page.getByTestId("flow-step-list").locator("li");
    await expect(rows).toHaveCount(5);
    // Names as the blueprint has them: the generator's "[LLM] " codes are not shown.
    await expect(rows.nth(2)).toContainText("Classification");
    await expect(canvas(page)).not.toContainText("[LLM]");
    await expect(canvas(page)).not.toContainText("[D]");

    // A row selects its task and brings it into view, beside its properties.
    await rows.nth(4).getByRole("button").first().click();
    const task = page.locator('.bpmn-editable [data-element-id="Activity_export"]');
    await expect(task).toHaveClass(/selected/);
    await expect(rows.nth(4)).toHaveAttribute("data-selected", "true");
    const props = page.getByTestId("bpmn-properties");
    await expect(props).toBeVisible();
    const box = (await canvas(page).boundingBox())!;
    const shape = (await task.boundingBox())!;
    const panel = (await props.boundingBox())!;
    expect(shape.x).toBeGreaterThan(box.x);
    expect(shape.y).toBeGreaterThan(box.y);
    expect(shape.y + shape.height).toBeLessThan(box.y + box.height);
    expect(shape.x + shape.width).toBeLessThan(panel.x);

    // The step's properties name its type in the Blueprint form's words.
    await expect(props).toContainText("Vaihe 5");
    await expect(props).toContainText("Syöte tai tulos");

    // Selecting a task on the canvas marks its row.
    await rows.nth(2).getByRole("button").first().click();
    await expect(rows.nth(2)).toHaveAttribute("data-selected", "true");
    await expect(rows.nth(4)).not.toHaveAttribute("data-selected", "true");
  });


  test("without wizard_api the canvas is read-only and says so, and nothing on it changes the blueprint", async ({
    page,
  }) => {
    test.setTimeout(90_000);
    const writes: string[] = [];
    page.on("request", (r) => {
      if (isCanvasWrite(r)) writes.push(`${r.method()} ${r.url()}`);
    });
    await openFlow(page);
    await waitForDiagram(page);
    const panel = page.getByTestId("bpmn-panel");
    const rows = page.getByTestId("flow-step-list").locator("li");

    // Open after Gate 2 ("Muokkaa kaaviota" pressed), but with no wizard_api to send edits to.
    await expect(panel).toHaveAttribute("data-locked", "false");
    await expect(panel).toHaveAttribute("data-ops", "off");
    await expect(page.locator(".bpmn-editable")).toHaveAttribute("data-read-only", "true");
    const note = page.getByTestId("bpmn-readonly-editing");
    await expect(note).toContainText(
      "Vain luku: kaavion muokkaus tarvitsee wizardin palvelun, joka ei ole nyt käytössä.",
    );
    await expect(page.getByTestId("bpmn-editing")).toHaveCount(0);

    // No tools, no Save and no Undo.
    await expect(page.locator(".bpmn-editable .djs-palette")).toHaveCount(0);
    await expect(page.getByTestId("bpmn-save")).toHaveCount(0);
    await expect(page.getByTestId("bpmn-undo")).toHaveCount(0);

    // A step's fields are shown but cannot be changed, and its context pad is empty.
    await rows.nth(2).getByRole("button").first().click();
    const task = page.locator('.bpmn-editable [data-element-id="Activity_classify"]');
    await expect(task).toHaveClass(/selected/);
    await expect(page.getByTestId("bpmn-property-name")).toHaveValue("Classification");
    await expect(page.getByTestId("bpmn-property-name")).toBeDisabled();
    await expect(page.locator(".bpmn-editable .djs-context-pad .entry")).toHaveCount(0);

    // Typing in place, Delete and dragging a step do nothing.
    await page.getByTestId("bpmn-properties").getByRole("button", { name: "Sulje" }).click();
    await task.dblclick();
    await expect(page.locator(".djs-direct-editing-parent")).toHaveCount(0);
    await page.keyboard.press("Delete");
    await expect(task).toBeVisible();
    const neighbour = page.locator('.bpmn-editable [data-element-id="Activity_extract"]');
    const gap = async () => (await task.boundingBox())!.x - (await neighbour.boundingBox())!.x;
    const before = await gap();
    const box = (await task.boundingBox())!;
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    await page.mouse.down();
    await page.mouse.move(box.x + box.width / 2 + 60, box.y + box.height / 2 + 40, { steps: 6 });
    await page.mouse.up();
    // The view may have moved with the drag; the step has not moved in the process.
    expect(Math.abs((await gap()) - before)).toBeLessThan(1);

    // Nothing was sent, and the other tabs have the steps as they were.
    await expect(rows).toHaveCount(5);
    await expect(rows.nth(2)).toContainText("Classification");
    await selectWorkspaceTab(page, "Blueprint");
    await expect(page.getByTestId("solution-plan-view").getByTestId(/^plan-step-\d+$/)).toHaveCount(5);
    expect(writes).toEqual([]);
  });

  test("with the server's mapping the editor offers the step tools, and none on what the blueprint draws elsewhere", async ({
    page,
  }) => {
    await standInForWizardApi(page, (route) => route.fulfill({ status: 500, body: "not in this test" }));
    await openFlow(page);
    await waitForDiagram(page);
    const panel = page.getByTestId("bpmn-panel");
    await expect(panel).toHaveAttribute("data-ops", "on");
    await expect(page.getByTestId("bpmn-editing")).toContainText("Jokainen muutos tallentuu heti");
    await expect(page.getByTestId("bpmn-undo")).toHaveText("Kumoa");

    // The palette: Add step, Add lane and the connect tool.
    const entries = page.locator(".bpmn-editable .djs-palette .entry");
    await expect(entries).toHaveCount(3);
    await expect(entries.nth(0)).toHaveAttribute("title", "Lisää vaihe prosessin loppuun");
    await expect(entries.nth(0)).toHaveAttribute("data-action", "gaik-add-step");
    await expect(entries.nth(1)).toHaveAttribute("title", "Lisää kaista");
    await expect(entries.nth(2)).toHaveAttribute("title", /^Yhdistä/);

    // The first step: rename, change type, append, a decision after it, a rework path, move (not earlier), connect, delete.
    const rows = page.getByTestId("flow-step-list").locator("li");
    await rows.nth(0).getByRole("button").first().click();
    const pad = page.locator(".djs-context-pad .entry");
    await expect(pad).toHaveCount(9);
    const titles = await pad.evaluateAll((els) => els.map((el) => el.getAttribute("title")));
    expect(titles).toEqual([
      "Nimeä uudelleen",
      "Vaihda vaiheen tyyppi",
      "Lisää vaihe tämän jälkeen",
      "Lisää päätös tämän jälkeen",
      "Lisää korjauspolku",
      "Siirrä aiemmaksi",
      "Siirrä myöhemmäksi",
      "Poista",
      "Yhdistä toiseen vaiheeseen",
    ]);
    await expect(page.locator('.djs-context-pad .entry[data-action="move-earlier"]')).toHaveAttribute(
      "aria-disabled",
      "true",
    );
    await expect(page.getByTestId("bpmn-property-name")).toHaveValue("Invoice intake");

    // The last step cannot move later.
    await rows.nth(4).getByRole("button").first().click();
    await expect(page.locator('.djs-context-pad .entry[data-action="move-later"]')).toHaveAttribute(
      "aria-disabled",
      "true",
    );
    await expect(page.locator('.djs-context-pad .entry[data-action="move-earlier"]')).not.toHaveAttribute(
      "aria-disabled",
      "true",
    );

    // A task the generator draws by itself is no step: no tools, no name field, and it says why.
    await page.getByTestId("bpmn-properties").getByRole("button", { name: "Sulje" }).click();
    await page.getByTestId("bpmn-zoom-controls").getByRole("button", { name: "Sovita näkymään" }).click();
    const generated = page.locator('.bpmn-editable [data-element-id="Activity_submit_finance_system"]');
    await expect(generated).toHaveAttribute("data-gaik-derived", "true");
    await expect(generated.locator("title")).toHaveText(/piirretään blueprintin muista tiedoista/);
    await generated.click();
    await expect(generated).toHaveClass(/selected/);
    await expect(pad).toHaveCount(0);
    await page.keyboard.press("Delete");
    await generated.dblclick();
    await expect(page.locator(".bpmn-editable .djs-direct-editing-parent")).toHaveCount(0);
    await expect(generated).toBeVisible();
  });

  test("move later, rename in place, delete and the Delete key send their operations on the version shown; each refusal is said in the UI language and the diagram is put back", async ({
    page,
  }) => {
    test.setTimeout(90_000);
    const sent: { base_version: number; operations: unknown[] }[] = [];
    const answers = [
      { status: 422, body: { detail: { error: "invalid_operation", message: "x", field: "operations[0].after" } } },
      { status: 409, body: { detail: { error: "agent_busy", message: "busy" } } },
      { status: 409, body: { detail: { error: "changed_elsewhere", message: "reload" } } },
      { status: 422, body: { detail: { error: "unsupported_edit", message: "Ask the wizard to change x." } } },
    ];
    await standInForWizardApi(page, async (route, body) => {
      sent.push(body);
      const answer = answers.shift() ?? { status: 500, body: {} };
      await route.fulfill({ status: answer.status, contentType: "application/json", body: JSON.stringify(answer.body) });
    });
    await openFlow(page);
    await waitForDiagram(page);
    const rows = page.getByTestId("flow-step-list").locator("li");
    const status = page.getByTestId("bpmn-status");
    const tasks = page.locator('.bpmn-editable .djs-shape[data-element-id^="Activity_"]');
    const count = await tasks.count();

    // Move later on the second step: after the third. Refused for a field, in plain words.
    await rows.nth(1).getByRole("button").first().click();
    await page.locator('.djs-context-pad .entry[data-action="move-later"]').click();
    await expect(status).toContainText("Muutosta ei tehty: tarkista edeltävä vaihe.");
    expect(sent[0]).toEqual({
      base_version: 7,
      operations: [{ op: "move_step", step_id: "extract", after: "classify" }],
    });

    // Rename in place: the wizard is replying, so it is not made and the name is back.
    await rows.nth(2).getByRole("button").first().click();
    await page.locator('.djs-context-pad .entry[data-action="rename"]').click();
    const box = page.locator(".bpmn-editable .djs-direct-editing-content");
    await box.fill("Cost centre proposal");
    await page.keyboard.press("Enter");
    await expect(status).toContainText("Wizard vastaa juuri.");
    expect(sent[1].operations).toEqual([{ op: "rename_step", step_id: "classify", name: "Cost centre proposal" }]);
    await expect(page.locator('.bpmn-editable [data-element-id="Activity_classify"]')).toContainText("Classification");

    // Delete: changed elsewhere, so the newer version is read and the user is told.
    await rows.nth(3).getByRole("button").first().click();
    await page.locator('.djs-context-pad .entry[data-action="delete"]').click();
    await expect(page.getByTestId("bpmn-changed-elsewhere")).toContainText("Blueprint muuttui muualla");
    expect(sent[2].operations).toEqual([{ op: "remove_step", step_id: "approve" }]);
    await expect(tasks).toHaveCount(count);
    await expect(rows).toHaveCount(5);

    // The Delete key on a picked step: remove_step. The server's English words are not shown.
    await rows.nth(0).getByRole("button").first().click();
    await expect(page.locator('.bpmn-editable [data-element-id="Activity_ingest"]')).toHaveClass(/selected/);
    // The keys go to the canvas once it has the focus.
    await page.locator('.bpmn-editable svg[tabindex="0"]').focus();
    await page.keyboard.press("Delete");
    await expect(status).toContainText("Muutosta ei voitu tehdä.");
    await expect(status).not.toContainText("Ask the wizard");
    expect(sent[3].operations).toEqual([{ op: "remove_step", step_id: "ingest" }]);
    await expect(tasks).toHaveCount(count);

    // Ctrl+Z on the canvas undoes nothing locally: the blueprint's Kumoa is the way back.
    await page.locator('.bpmn-editable svg[tabindex="0"]').focus();
    await page.keyboard.press("Control+z");
    await expect(tasks).toHaveCount(count);
    expect(sent).toHaveLength(4);
  });

  test("no edit starts while a name is typed in place: the palette does nothing and the step's tools go", async ({
    page,
  }) => {
    test.setTimeout(90_000);
    const sent: unknown[][] = [];
    await standInForWizardApi(page, async (route, body) => {
      sent.push(body.operations);
      const refused = { detail: { error: "agent_busy", message: "busy" } };
      await route.fulfill({ status: 409, contentType: "application/json", body: JSON.stringify(refused) });
    });
    await openFlow(page);
    await waitForDiagram(page);
    const rows = page.getByTestId("flow-step-list").locator("li");

    await rows.nth(2).getByRole("button").first().click();
    const pad = page.locator(".djs-context-pad .entry");
    await expect(page.locator('.djs-context-pad .entry[data-action="move-later"]')).toBeVisible();
    await page.locator('.djs-context-pad .entry[data-action="rename"]').click();
    const typed = page.locator(".bpmn-editable .djs-direct-editing-content");
    await typed.fill("Cost centre proposal");
    // The step's own tools (append, move, delete) are gone while its name is typed.
    await expect(pad).toHaveCount(0);
    await expect(page.getByTestId("bpmn-show-data")).toBeDisabled();
    await expect(page.getByTestId("bpmn-undo")).toBeDisabled();
    // Add step in the palette does nothing meanwhile, and the name stays open for typing.
    await page.locator('.bpmn-editable .djs-palette .entry[data-action="gaik-add-step"]').click();
    await expect(typed).toBeVisible();
    await expect(typed).toHaveText("Cost centre proposal");
    expect(sent).toEqual([]);
    // Finished, the name goes out, and only it.
    await typed.press("Enter");
    await expect.poll(() => sent.length).toBe(1);
    expect(sent[0]).toEqual([{ op: "rename_step", step_id: "classify", name: "Cost centre proposal" }]);
  });

  test("a rename refused as changed elsewhere is made again on the newer version, or said lost when its step is gone", async ({
    page,
  }) => {
    test.setTimeout(150_000);
    await openFlow(page);
    await waitForDiagram(page);
    await openBlueprintEditor(page);
    await page.getByTestId("blueprint-json-toggle").click();
    const blueprint = JSON.parse(await page.getByTestId("blueprint-json-editor").inputValue()) as {
      goal: string;
      steps: { id: string; name: string; type: string }[];
    };
    await page.getByTestId("blueprint-done").click();

    let steps = blueprint.steps.map((s) => s.id);
    const sent: { base_version: number; operations: unknown[] }[] = [];
    let release!: () => void;
    let held = new Promise<void>((resolve) => (release = resolve));
    await standInForWizardApi(
      page,
      async (route, body) => {
        sent.push(body);
        if (sent.length === 1 || sent.length === 3) {
          // Held while a version is written elsewhere, then refused as changed elsewhere.
          await held;
          const refused = { detail: { error: "changed_elsewhere", message: "reload" } };
          await route.fulfill({ status: 409, contentType: "application/json", body: JSON.stringify(refused) });
          return;
        }
        // The stand-in writes no version to the mock store, so the session stays on the one sent.
        const session = { id: "ses_laskut", active_version: body.base_version, blueprint };
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ session, warnings: [], needs_attention: [], bpmn_changed: true }),
        });
      },
      { steps: () => steps },
    );
    // The stand-in comes before the canvas reads its mapping again.
    await page.reload();
    await setChatOpen(page, false);
    await selectWorkspaceTab(page, "Työnkulku");
    await openBpmnView(page);
    await waitForDiagram(page);
    await expect(page.getByTestId("bpmn-panel")).toHaveAttribute("data-ops", "on");
    const rows = page.getByTestId("flow-step-list").locator("li");
    const write = async (content: unknown) => {
      const res = await page.request.patch("/api/sessions/ses_laskut/blueprint", {
        data: { content, note: "e2e: written elsewhere" },
      });
      expect(res.status()).toBe(200);
    };

    // A rename in the name field, on version 7, held at the server.
    await rows.nth(0).getByRole("button").first().click();
    const name = page.getByTestId("bpmn-property-name");
    await expect(name).toHaveValue("Invoice intake");
    await name.fill("Receive the invoice");
    await name.press("Enter");
    await expect.poll(() => sent.length).toBe(1);
    expect(sent[0].base_version).toBe(7);
    // Meanwhile version 8 is written elsewhere; the rename is refused.
    await write({ ...blueprint, goal: `${blueprint.goal} Reviewed weekly.` });
    release();
    await expect(page.getByTestId("bpmn-changed-elsewhere")).toBeVisible();
    // Once the page has version 8 the rename is made again, on it.
    await expect.poll(() => sent.length, { timeout: 20_000 }).toBe(2);
    expect(sent[1]).toEqual({
      base_version: 8,
      operations: [{ op: "rename_step", step_id: "ingest", name: "Receive the invoice" }],
    });
    await expect(page.getByTestId("bpmn-status")).toContainText("Tallennettu");

    // Again, but this time the step is removed elsewhere meanwhile: the user is told.
    held = new Promise<void>((resolve) => (release = resolve));
    await rows.nth(1).getByRole("button").first().click();
    await expect(name).toHaveValue("Data extraction");
    await name.fill("Read the amounts");
    await name.press("Enter");
    await expect.poll(() => sent.length).toBe(3);
    const without = blueprint.steps.filter((s) => s.id !== "extract");
    steps = without.map((s) => s.id);
    await write({ ...blueprint, steps: without });
    release();
    await expect(page.getByTestId("bpmn-status")).toContainText(
      "Nimeä ”Read the amounts” ei tallennettu: vaihe poistettiin muualla.",
      { timeout: 20_000 },
    );
    expect(sent).toHaveLength(3);
  });

  test("before the agent has written its blueprint the canvas is read-only and says why", async ({ page }) => {
    const sent: unknown[] = [];
    await standInForWizardApi(page, async (route, body) => {
      sent.push(body);
      await route.fulfill({ status: 500, body: "not in this test" });
    }, { hasDraft: false });
    await openFlow(page);
    await waitForDiagram(page);

    const panel = page.getByTestId("bpmn-panel");
    await expect(panel).toHaveAttribute("data-ops", "no_draft");
    await expect(page.getByTestId("bpmn-readonly-editing")).toContainText(
      "Vain luku: kaaviota voi muokata, kun wizard on kirjoittanut ensimmäisen blueprintin.",
    );
    await expect(page.locator(".bpmn-editable .djs-palette")).toHaveCount(0);
    await page.getByTestId("flow-step-list").locator("li").nth(2).getByRole("button").first().click();
    await expect(page.getByTestId("bpmn-property-name")).toHaveValue("Classification");
    await expect(page.getByTestId("bpmn-property-name")).toBeDisabled();
    expect(sent).toEqual([]);
  });

  test("an edit refused because there is no draft yet makes the canvas read-only with the same note", async ({
    page,
  }) => {
    await standInForWizardApi(page, async (route) => {
      const refused = { detail: { error: "no_draft", message: "The wizard has not written the blueprint yet" } };
      await route.fulfill({ status: 409, contentType: "application/json", body: JSON.stringify(refused) });
    });
    await openFlow(page);
    await waitForDiagram(page);
    await page.locator('.bpmn-editable .djs-palette .entry[data-action="gaik-add-step"]').click();
    await expect(page.getByTestId("bpmn-panel")).toHaveAttribute("data-ops", "no_draft");
    await expect(page.getByTestId("bpmn-readonly-editing")).toContainText("kun wizard on kirjoittanut");
    await expect(page.getByTestId("bpmn-status")).toHaveCount(0);
  });

  test("a blueprint changed in the chat reloads the read-only diagram", async ({ page }) => {
    test.setTimeout(150_000);
    await openFlow(page);
    await waitForDiagram(page);

    // The blueprint as the session has it, read from the form's JSON.
    await openBlueprintEditor(page);
    await page.getByTestId("blueprint-json-toggle").click();
    const blueprint = JSON.parse(await page.getByTestId("blueprint-json-editor").inputValue()) as {
      steps: { id: string; name: string; type: string }[];
    };
    await page.getByTestId("blueprint-done").click();
    await selectWorkspaceTab(page, "Työnkulku");
    await waitForDiagram(page);
    const writeVersion = async (steps: { id: string; name: string; type: string }[]) => {
      const res = await page.request.patch("/api/sessions/ses_laskut/blueprint", {
        data: { content: { ...blueprint, steps }, note: "e2e: the agent's version" },
      });
      expect(res.status()).toBe(200);
    };
    const canvasTask = (id: string) => page.locator(`.bpmn-editable [data-element-id="${id}"]`);
    let writes = 0;
    page.on("request", (r) => {
      if (isCanvasWrite(r)) writes += 1;
    });

    // The agent's new step is drawn.
    const archive = { id: "archive", name: "Archiving", type: "io" };
    await writeVersion([...blueprint.steps, archive]);
    await chatTurn(page);
    await expect(canvasTask("Activity_archive")).toBeVisible({ timeout: 30_000 });
    await expect(page.getByTestId("flow-step-list").locator("li")).toHaveCount(6);
    await expect(page.getByTestId("bpmn-changed-elsewhere")).toHaveCount(0);
    // The canvas says what it was drawn from: the seed session stood on version 7.
    const updated = page.getByTestId("bpmn-updated");
    await expect(updated).toHaveText("Päivitetty chatista · blueprintin versio 8");

    // And the next one: with nothing of the user's on the canvas there is nothing to choose.
    await writeVersion([...blueprint.steps, archive, { id: "report", name: "Monthly report", type: "ai" }]);
    await chatTurn(page);
    await expect(canvasTask("Activity_report")).toBeVisible({ timeout: 30_000 });
    await expect(canvasTask("Activity_approve")).toBeVisible();
    await expect(page.getByTestId("bpmn-changed-elsewhere")).toHaveCount(0);
    await expect(updated).toHaveText("Päivitetty chatista · blueprintin versio 9");
    expect(writes).toBe(0);
  });

  test("the canvas says when the chat wrote a newer version, redrawn or not", async ({ page }) => {
    test.setTimeout(150_000);
    await openFlow(page);
    await waitForDiagram(page);
    await openBlueprintEditor(page);
    await page.getByTestId("blueprint-json-toggle").click();
    const blueprint = JSON.parse(await page.getByTestId("blueprint-json-editor").inputValue()) as {
      goal: string;
      steps: { id: string; name: string; type: string }[];
    };
    await page.getByTestId("blueprint-done").click();
    await selectWorkspaceTab(page, "Työnkulku");
    await waitForDiagram(page);
    const updated = page.getByTestId("bpmn-updated");
    const write = async (content: unknown) => {
      const res = await page.request.patch("/api/sessions/ses_laskut/blueprint", {
        data: { content, note: "e2e: the agent's version" },
      });
      expect(res.status()).toBe(200);
    };

    // The wizard changes something the diagram does not draw: the line still comes.
    await page.getByTestId("flow-step-list").locator("li").nth(2).getByRole("button").first().click();
    await write({ ...blueprint, goal: `${blueprint.goal} Reviewed weekly.` });
    await chatTurn(page);
    await expect(updated).toHaveText("Päivitetty chatista · blueprintin versio 8", { timeout: 30_000 });

    // And a step: the diagram is drawn again with a step still picked, and the line names the new version.
    await write({ ...blueprint, steps: [...blueprint.steps, { id: "archive", name: "Archiving", type: "io" }] });
    await chatTurn(page);
    await expect(page.locator('.bpmn-editable [data-element-id="Activity_archive"]')).toBeVisible({ timeout: 30_000 });
    await expect(page.locator('.bpmn-editable [data-element-id="Activity_classify"]')).toHaveClass(/selected/);
    await expect(updated).toHaveText("Päivitetty chatista · blueprintin versio 9");
  });

  test("after Gate 2 the canvas opens locked, as the simple flow does, and one Muokkaa opens both", async ({
    page,
  }) => {
    test.setTimeout(90_000);
    await loginAsDev(page);
    await page.goto("/sessions/ses_laskut");
    await setChatOpen(page, false);
    await selectWorkspaceTab(page, "Työnkulku");
    await openBpmnView(page, { edit: false });
    await waitForDiagram(page, { edit: false });
    let writes = 0;
    page.on("request", (r) => {
      if (isCanvasWrite(r)) writes += 1;
    });

    // The same words and the same button as under the simple flow.
    const panel = page.getByTestId("bpmn-panel");
    const locked = page.getByTestId("bpmn-locked");
    await expect(panel).toHaveAttribute("data-locked", "true");
    await expect(locked).toContainText(
      "Vain luku: muutos vaatii uuden paketin ja testiajon. Valitse vaihe ja pyydä muutosta wizardilta.",
    );
    // No tools to edit with.
    await expect(page.locator(".bpmn-editable .djs-palette")).toHaveCount(0);

    // A step can be picked: its fields cannot be changed, and nothing offers a rename or a delete.
    const task = page.locator('.bpmn-editable [data-element-id="Activity_classify"]');
    await page.getByTestId("flow-step-list").locator("li").nth(2).getByRole("button").first().click();
    await expect(task).toHaveClass(/selected/);
    await expect(page.getByTestId("bpmn-property-name")).toHaveValue("Classification");
    await expect(page.getByTestId("bpmn-property-name")).toBeDisabled();
    await expect(page.locator(".bpmn-editable .djs-context-pad .entry")).toHaveCount(0);

    // The step still leads to the wizard.
    await page.getByTestId("bpmn-ask-step").click();
    await expect(page.getByTestId("chat-reference")).toContainText("Vaihe 3 · Classification");
    await setChatOpen(page, false);

    // "Muokkaa kaaviota" opens the lock where the canvas stands; without wizard_api it stays
    // read-only and says why, and the picked step stays picked.
    await locked.getByRole("button", { name: "Muokkaa kaaviota" }).click();
    await expect(panel).toHaveAttribute("data-locked", "false");
    await expect(locked).toHaveCount(0);
    await waitForDiagram(page, { edit: false });
    await expect(page.getByTestId("bpmn-readonly-editing")).toContainText("Vain luku: kaavion muokkaus tarvitsee");
    await expect(page.locator(".bpmn-editable .djs-palette")).toHaveCount(0);
    await expect(page.getByTestId("bpmn-property-name")).toHaveValue("Classification");
    await expect(page.getByTestId("bpmn-property-name")).toBeDisabled();

    // One lock for the two diagrams: the simple flow is open for edits.
    await page.getByTestId("flow-view-diagram").click();
    await expect(page.getByTestId("simple-flow")).toBeVisible();
    await expect(page.getByTestId("simple-flow-locked")).toHaveCount(0);
    expect(writes).toBe(0);
  });

  test("after Gate 2 Lopeta muokkaus closes the diagrams again", async ({ page }) => {
    await loginAsDev(page);
    await page.goto("/sessions/ses_laskut");
    await setChatOpen(page, false);
    await selectWorkspaceTab(page, "Työnkulku");
    await openBpmnView(page, { edit: false });
    await waitForDiagram(page, { edit: false });

    await page.getByTestId("bpmn-locked").getByRole("button", { name: "Muokkaa kaaviota" }).click();
    const done = page.getByTestId("bpmn-readonly-editing").getByRole("button", { name: "Lopeta muokkaus" });
    await expect(done).toBeEnabled();
    await expect(page.getByTestId("bpmn-locked")).toHaveCount(0);

    await done.click();
    await expect(page.getByTestId("bpmn-panel")).toHaveAttribute("data-locked", "true");
    await expect(page.getByTestId("bpmn-locked")).toBeVisible();
    await expect(page.getByTestId("bpmn-readonly-editing")).toHaveCount(0);
    await expect(page.locator(".bpmn-editable .djs-palette")).toHaveCount(0);

    // One lock for both: the simple flow is read-only again too, and opens and closes the same way.
    await page.getByTestId("flow-view-diagram").click();
    await expect(page.getByTestId("simple-flow-locked")).toBeVisible();
    await page.getByTestId("simple-flow-locked").getByRole("button", { name: "Muokkaa kaaviota" }).click();
    await expect(page.getByTestId("simple-flow-editing")).toContainText("Jokainen muutos tallentuu heti");
    // A removal leaves "Kumoa"; closing the flow takes it away, so nothing saves into a locked flow.
    await page.getByTestId("simple-flow-node-3").click();
    await page.getByTestId("simple-flow-remove").click();
    await expect(page.getByTestId("simple-flow-undo")).toBeVisible();
    await page.getByTestId("simple-flow-editing").getByRole("button", { name: "Lopeta muokkaus" }).click();
    await expect(page.getByTestId("simple-flow-locked")).toBeVisible();
    await expect(page.getByTestId("simple-flow-undo")).toHaveCount(0);
  });

  test("a language switch says the read-only note and names the tools in the new language", async ({ page }) => {
    await standInForWizardApi(page, (route) => route.fulfill({ status: 500, body: "not in this test" }));
    await openFlow(page);
    await waitForDiagram(page);
    await expect(page.locator(".bpmn-editable .djs-palette .entry").nth(0)).toHaveAttribute(
      "title",
      "Lisää vaihe prosessin loppuun",
    );

    // The language is chosen in the menu of the account row at the sidebar's foot.
    await (await openAccountMenu(page)).locator('button[name="locale"][value="en"]').click();
    const entries = page.locator(".bpmn-editable .djs-palette .entry");
    await expect(entries.nth(0)).toHaveAttribute("title", "Add a step at the end of the process");
    await expect(entries.nth(1)).toHaveAttribute("title", "Add a lane");
    await expect(entries.nth(2)).toHaveAttribute("title", /^Connect steps/);
    await expect(page.getByTestId("bpmn-editing")).toContainText("Each change saves at once.");
    await expect(page.locator('.bpmn-editable [data-element-id="Activity_classify"]')).toBeVisible();

    // Without the stand-in the canvas is read-only, in English too.
    await page.unrouteAll({ behavior: "ignoreErrors" });
    await page.reload();
    await selectWorkspaceTab(page, "Workflow");
    await openBpmnView(page);
    await waitForDiagram(page);
    await expect(page.getByTestId("bpmn-readonly-editing")).toContainText(
      "Read only: editing the diagram needs the wizard service",
    );
  });

  test("Muuta chatissa on a step row and in the properties opens the chat with that step", async ({ page }) => {
    await openFlow(page);
    await waitForDiagram(page);
    await recordChatReferences(page);

    await page.getByRole("button", { name: "Pyydä wizardia muuttamaan vaihetta Classification" }).click();
    const reference = {
      key: "step:classify",
      label: "Vaihe 3 · Classification",
      prefix: 'Koskee prosessin vaihetta 3 (id classify), lainattuna: "Classification"',
    };
    expect(await chatReferences(page)).toEqual([reference]);
    // The chat opened for the question, and the tab is narrow again: collapsed, the list is back.
    await expect(page.getByTestId("chat-dock")).toHaveAttribute("data-chat-open", "true");
    await setChatOpen(page, false);

    await page.getByTestId("flow-step-list").locator("li").nth(2).getByRole("button").first().click();
    await page.getByTestId("bpmn-ask-step").click();
    expect(await chatReferences(page)).toEqual([reference, reference]);
  });

  test("shows the steps with a retry when the diagram cannot be loaded", async ({ page }) => {
    let fail = true;
    await page.route("**/api/sessions/ses_laskut/bpmn", (route) =>
      fail ? route.fulfill({ status: 500, body: "no diagram" }) : route.continue(),
    );
    await openFlow(page);

    const error = page.getByTestId("flow-diagram-error");
    await expect(error).toContainText("Kaaviota ei saatu ladattua.");
    await expect(page.getByTestId("flow-step-list").locator("li")).toHaveCount(5);

    fail = false;
    await error.getByRole("button", { name: "Yritä uudelleen" }).click();
    await waitForDiagram(page);
    await expect(error).toHaveCount(0);
  });

  test("on a phone the BPMN editor has no palette, and a list row leads back to it", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await openFlow(page);

    await waitForDiagram(page);
    await expect(page.getByTestId("flow-step-list")).toBeHidden();
    await expect(page.locator(".bpmn-editable .djs-palette")).toBeHidden();
    await expect(page.getByTestId("bpmn-zoom-controls")).toBeInViewport();

    // The list takes the diagram's place, and a row takes the user to its task
    // on the diagram that was open.
    await page.getByTestId("flow-view-list").click();
    await expect(page.getByTestId("flow-view-list")).toHaveAttribute("aria-pressed", "true");
    await expect(page.getByTestId("flow-step-list")).toBeVisible();
    await page.getByTestId("flow-step-list").locator("li").nth(0).getByRole("button").first().click();
    await expect(page.getByTestId("flow-view-bpmn")).toHaveAttribute("aria-pressed", "true");
    const task = page.locator('.bpmn-editable [data-element-id="Activity_ingest"]');
    await expect(task).toHaveClass(/selected/);
    // The task is on screen below its properties, which span the narrow canvas.
    const props = (await page.getByTestId("bpmn-properties").boundingBox())!;
    const shape = (await task.boundingBox())!;
    expect(shape.y).toBeGreaterThanOrEqual(props.y + props.height);
    await expect(task).toBeInViewport();
  });
});
