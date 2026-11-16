import { test, expect, type Page } from "@playwright/test";
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
 * The Workflow tab's BPMN editor ("Avaa BPMN-kaaviona"): the process steps
 * beside the diagram, the view controls, and what a canvas edit does (a rename
 * saves itself, a structural edit waits for "Tallenna muutokset", and nothing
 * reaches the other tabs unsaved). The tab opens on the simple flow, which
 * e2e/workflow-flow-view.spec.ts covers.
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
 * The diagram is on the canvas, open for edits. ses_laskut stands after Gate 2,
 * where the canvas opens read-only each time the tab is opened: the lock is
 * opened here unless the test is about it (`edit: false`).
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

const isSync = (r: { url(): string; method(): string }) => r.url().includes("/bpmn/sync") && r.method() === "POST";

/** The first save of the test waits at the server until `release()`; later ones go through. */
async function holdFirstSync(page: Page) {
  let release!: () => void;
  const held = new Promise<void>((resolve) => (release = resolve));
  let first = true;
  await page.route("**/api/sessions/ses_laskut/bpmn/sync", async (route) => {
    if (first) {
      first = false;
      await held;
    }
    await route.continue();
  });
  return release;
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
  await field.fill("Lisää vaihe");
  await field.press("Enter");
  await expect(page.locator('[data-testid="chat-message"][data-role="assistant"]').last()).toContainText("Selvä.");
  await setChatOpen(page, false);
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

    // One group: zoom out, the level (a figure), zoom in, fit, the large view. No mode pair, minimap, theme or save button.
    const controls = page.getByTestId("bpmn-zoom-controls");
    await expect(controls.getByRole("button")).toHaveCount(4);
    await expect(page.getByRole("button", { name: /Koko prosessi|Luettava/ })).toHaveCount(0);
    await expect(page.locator(".djs-minimap")).toHaveCount(0);
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

  test("a rename in the name field saves by itself and reaches the other tabs only once saved", async ({ page }) => {
    // A save lints, syncs and regenerates the diagram in child processes.
    test.setTimeout(120_000);
    await openFlow(page);
    await waitForDiagram(page);
    const rows = page.getByTestId("flow-step-list").locator("li");
    await rows.nth(2).getByRole("button").first().click();

    const name = page.getByTestId("bpmn-property-name");
    await expect(name).toHaveValue("Classification");
    const sync = page.waitForResponse((r) => r.url().includes("/bpmn/sync") && r.request().method() === "POST");
    await name.fill("Cost centre proposal");

    // While it is only typed, the list still has the saved name.
    await expect(rows.nth(2)).toContainText("Classification");
    expect((await sync).status()).toBe(200);

    await expect(page.getByTestId("bpmn-status")).toContainText("Tallennettu");
    await expect(rows.nth(2)).toContainText("Cost centre proposal");
    // The field keeps the cursor and the text through the save.
    await expect(name).toBeFocused();
    await expect(name).toHaveValue("Cost centre proposal");
    await expect(page.getByTestId("bpmn-save")).toHaveCount(0);

    // The Blueprint tab opens in its read view; the JSON is in the form.
    await expect(page.getByTestId("solution-plan-view").getByTestId("plan-step-2")).toContainText(
      "Cost centre proposal",
    );
    await openBlueprintEditor(page);
    await page.getByTestId("blueprint-json-toggle").click();
    const saved = JSON.parse(await page.getByTestId("blueprint-json-editor").inputValue()) as {
      steps: { id: string; name: string }[];
    };
    expect(saved.steps.map((s) => s.name)).toEqual([
      "Invoice intake",
      "Data extraction",
      "Cost centre proposal",
      "Approval",
      "Export to finance system",
    ]);
  });

  test("a structural edit waits for Tallenna muutokset and survives a visit to another tab", async ({ page }) => {
    test.setTimeout(120_000);
    await openFlow(page);
    await waitForDiagram(page);
    const rows = page.getByTestId("flow-step-list").locator("li");

    // Delete the Approval step from the context pad.
    await rows.nth(3).getByRole("button").first().click();
    await page.locator('.djs-context-pad .entry[data-action="delete"]').click();
    const status = page.getByTestId("bpmn-status");
    await expect(status).toContainText("Muutoksia ei ole tallennettu");
    const save = page.getByTestId("bpmn-save");
    await expect(save).toHaveText("Tallenna muutokset");

    // Nothing is saved or shown elsewhere yet.
    await expect(rows).toHaveCount(5);
    await selectWorkspaceTab(page, "Blueprint");
    await expect(page.getByTestId("solution-plan-view").getByTestId(/^plan-step-\d+$/)).toHaveCount(5);

    // Back on the tab the unsaved edit is still on the canvas.
    await page.getByRole("tab", { name: "Työnkulku" }).click();
    await expect(page.getByTestId("bpmn-save")).toBeVisible({ timeout: 30_000 });
    await expect(page.locator('.bpmn-editable [data-element-id="Activity_approve"]')).toHaveCount(0);

    const sync = page.waitForResponse((r) => r.url().includes("/bpmn/sync") && r.request().method() === "POST");
    await page.getByTestId("bpmn-save").click();
    expect((await sync).status()).toBe(200);
    await expect(page.getByTestId("bpmn-status")).toContainText("Tallennettu", { timeout: 15_000 });
    await expect(page.getByTestId("bpmn-save")).toHaveCount(0);
    await expect(page.getByTestId("flow-step-list").locator("li")).toHaveCount(4);
    await expect(page.getByRole("heading", { name: "Prosessin vaiheet (4)" })).toBeVisible();
  });

  test("a label being typed on the canvas is kept when an earlier rename finishes saving", async ({ page }) => {
    test.setTimeout(120_000);
    const release = await holdFirstSync(page);
    await openFlow(page);
    await waitForDiagram(page);
    const rows = page.getByTestId("flow-step-list").locator("li");

    await rows.nth(0).getByRole("button").first().click();
    const sent = page.waitForRequest(isSync);
    await page.getByTestId("bpmn-property-name").fill("Receive the invoice");
    await sent;

    // While that save is on its way, the next label is typed in place: no command yet.
    await rows.nth(2).getByRole("button").first().click();
    await page.locator('.djs-context-pad .entry[data-action="rename"]').click();
    const box = page.locator(".bpmn-editable .djs-direct-editing-content");
    await box.fill("Cost centre proposal");

    const saved = page.waitForResponse((r) => isSync(r.request()));
    release();
    expect((await saved).status()).toBe(200);
    await expect(rows.nth(0)).toContainText("Receive the invoice");
    // The saved diagram was not imported over the open label.
    await expect(box).toBeVisible();
    await expect(box).toHaveText("Cost centre proposal");

    // Finishing the label saves it as the next rename.
    const second = page.waitForResponse((r) => isSync(r.request()));
    await page.keyboard.press("Enter");
    expect((await second).status()).toBe(200);
    await expect(rows.nth(2)).toContainText("Cost centre proposal");
    await expect(rows.nth(0)).toContainText("Receive the invoice");
  });

  test("an edit made while a rename was being saved survives a visit to another tab", async ({ page }) => {
    test.setTimeout(120_000);
    const release = await holdFirstSync(page);
    await openFlow(page);
    await waitForDiagram(page);
    const rows = page.getByTestId("flow-step-list").locator("li");

    await rows.nth(0).getByRole("button").first().click();
    const sent = page.waitForRequest(isSync);
    await page.getByTestId("bpmn-property-name").fill("Receive the invoice");
    await sent;

    // During the save the Approval step is deleted: the canvas is kept as it is when the save ends.
    await rows.nth(3).getByRole("button").first().click();
    await page.locator('.djs-context-pad .entry[data-action="delete"]').click();
    const saved = page.waitForResponse((r) => isSync(r.request()));
    release();
    expect((await saved).status()).toBe(200);
    await expect(rows.nth(0)).toContainText("Receive the invoice");
    await expect(page.getByTestId("bpmn-save")).toBeVisible();

    await selectWorkspaceTab(page, "Blueprint");
    await selectWorkspaceTab(page, "Työnkulku");
    // The unsaved delete is still there, on the diagram the rename saved: nothing to choose between.
    await expect(page.getByTestId("bpmn-save")).toBeVisible({ timeout: 30_000 });
    await expect(page.locator('.bpmn-editable [data-element-id="Activity_approve"]')).toHaveCount(0);
    await expect(page.getByTestId("bpmn-changed-elsewhere")).toHaveCount(0);
  });

  test("a blueprint changed in the chat reloads the diagram, and unsaved canvas edits wait for a choice", async ({
    page,
  }) => {
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
    let syncs = 0;
    page.on("request", (r) => {
      if (isSync(r)) syncs += 1;
    });

    // No edits on the canvas: the agent's new step is drawn.
    const archive = { id: "archive", name: "Archiving", type: "io" };
    await writeVersion([...blueprint.steps, archive]);
    await chatTurn(page);
    await expect(canvasTask("Activity_archive")).toBeVisible({ timeout: 30_000 });
    await expect(page.getByTestId("flow-step-list").locator("li")).toHaveCount(6);
    await expect(page.getByTestId("bpmn-changed-elsewhere")).toHaveCount(0);
    // The canvas says what it was drawn from: the seed session stood on version 7.
    const updated = page.getByTestId("bpmn-updated");
    await expect(updated).toHaveText("Päivitetty chatista · blueprintin versio 8");

    // An unsaved edit on the canvas, and the agent writes another version.
    await page.getByTestId("flow-step-list").locator("li").nth(3).getByRole("button").first().click();
    await page.locator('.djs-context-pad .entry[data-action="delete"]').click();
    await expect(page.getByTestId("bpmn-save")).toBeVisible();
    await writeVersion([...blueprint.steps, archive, { id: "report", name: "Monthly report", type: "ai" }]);
    await chatTurn(page);

    // The canvas keeps the edit, nothing is saved over the newer version, and the user chooses.
    const choice = page.getByTestId("bpmn-changed-elsewhere");
    await expect(choice).toContainText("Blueprint muuttui muualla", { timeout: 30_000 });
    await expect(canvasTask("Activity_approve")).toHaveCount(0);
    await expect(canvasTask("Activity_report")).toHaveCount(0);
    await expect(page.getByTestId("bpmn-save")).toHaveCount(0);
    await expect(choice.getByRole("button", { name: "Tallenna omat muutokseni" })).toBeEnabled();
    // The canvas still holds the user's edit on the older version: it does not claim the newer one.
    await expect(updated).toHaveCount(0);

    await choice.getByRole("button", { name: "Ota uudempi versio" }).click();
    await expect(canvasTask("Activity_report")).toBeVisible({ timeout: 30_000 });
    await expect(canvasTask("Activity_approve")).toBeVisible();
    await expect(choice).toHaveCount(0);
    await expect(page.getByTestId("bpmn-save")).toHaveCount(0);
    await expect(updated).toHaveText("Päivitetty chatista · blueprintin versio 9");
    expect(syncs).toBe(0);
  });

  test("after a save of its own the canvas still says when the chat wrote a newer version, redrawn or not", async ({
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
    await selectWorkspaceTab(page, "Työnkulku");
    await waitForDiagram(page);
    const updated = page.getByTestId("bpmn-updated");
    const write = async (content: unknown) => {
      const res = await page.request.patch("/api/sessions/ses_laskut/blueprint", {
        data: { content, note: "e2e: the agent's version" },
      });
      expect(res.status()).toBe(200);
    };

    // The user's own rename: version 8, and the canvas says "Tallennettu".
    await page.getByTestId("flow-step-list").locator("li").nth(2).getByRole("button").first().click();
    const sync = page.waitForResponse((r) => isSync(r.request()));
    await page.getByTestId("bpmn-property-name").fill("Cost centre classification");
    expect((await sync).status()).toBe(200);
    await expect(page.getByTestId("bpmn-status")).toContainText("Tallennettu", { timeout: 20_000 });
    await expect(updated).toHaveCount(0);
    const steps = blueprint.steps.map((s) => (s.id === "classify" ? { ...s, name: "Cost centre classification" } : s));

    // The wizard changes something the diagram does not draw: the line still comes, in place of "Tallennettu".
    await write({ ...blueprint, steps, goal: `${blueprint.goal} Reviewed weekly.` });
    await chatTurn(page);
    await expect(updated).toHaveText("Päivitetty chatista · blueprintin versio 9", { timeout: 30_000 });
    await expect(page.getByTestId("bpmn-status")).not.toContainText("Tallennettu");

    // And a step: the diagram is drawn again with a step still picked, and the line names the new version.
    await write({ ...blueprint, steps: [...steps, { id: "archive", name: "Archiving", type: "io" }] });
    await chatTurn(page);
    await expect(page.locator('.bpmn-editable [data-element-id="Activity_archive"]')).toBeVisible({ timeout: 30_000 });
    await expect(updated).toHaveText("Päivitetty chatista · blueprintin versio 10");
  });

  test("after Gate 2 the canvas opens read-only, as the simple flow does, and one Muokkaa opens both", async ({
    page,
  }) => {
    test.setTimeout(90_000);
    await loginAsDev(page);
    await page.goto("/sessions/ses_laskut");
    await setChatOpen(page, false);
    await selectWorkspaceTab(page, "Työnkulku");
    await openBpmnView(page, { edit: false });
    await waitForDiagram(page, { edit: false });
    let syncs = 0;
    page.on("request", (r) => {
      if (isSync(r)) syncs += 1;
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

    // A step can be picked: its name is text, not a field, and nothing offers a rename or a delete.
    const task = page.locator('.bpmn-editable [data-element-id="Activity_classify"]');
    const neighbour = page.locator('.bpmn-editable [data-element-id="Activity_extract"]');
    // Picked from the list, which brings it to the middle of the view.
    await page.getByTestId("flow-step-list").locator("li").nth(2).getByRole("button").first().click();
    await expect(task).toHaveClass(/selected/);
    await expect(page.getByTestId("bpmn-property-name-text")).toHaveText("Classification");
    await expect(page.getByTestId("bpmn-property-name")).toHaveCount(0);
    await expect(page.locator(".bpmn-editable .djs-context-pad .entry")).toHaveCount(0);

    // What edits an open canvas does nothing here: typing in place, Delete, dragging a step.
    await task.dblclick();
    await expect(page.locator(".djs-direct-editing-parent")).toHaveCount(0);
    await page.keyboard.press("Delete");
    await expect(task).toBeVisible();
    const gap = async () => (await task.boundingBox())!.x - (await neighbour.boundingBox())!.x;
    const before = await gap();
    const box = (await task.boundingBox())!;
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    await page.mouse.down();
    await page.mouse.move(box.x + box.width / 2 + 60, box.y + box.height / 2 + 40, { steps: 6 });
    await page.mouse.up();
    // The view may have moved with the drag; the step has not moved in the process.
    expect(Math.abs((await gap()) - before)).toBeLessThan(1);
    await expect(page.getByTestId("bpmn-save")).toHaveCount(0);

    // The step still leads to the wizard.
    await page.getByTestId("bpmn-ask-step").click();
    await expect(page.getByTestId("chat-reference")).toContainText("Vaihe 3 · Classification");
    await setChatOpen(page, false);

    // "Muokkaa" opens the canvas where it stands: the tools appear and the picked step stays picked.
    await locked.getByRole("button", { name: "Muokkaa" }).click();
    await expect(panel).toHaveAttribute("data-locked", "false");
    await expect(locked).toHaveCount(0);
    await waitForDiagram(page, { edit: false });
    await expect(page.locator(".bpmn-editable .djs-palette")).toBeVisible();
    await expect(page.getByTestId("bpmn-property-name")).toHaveValue("Classification");

    // One lock for the two diagrams: the simple flow is open for edits too.
    await page.getByTestId("flow-view-diagram").click();
    await expect(page.getByTestId("simple-flow")).toBeVisible();
    await expect(page.getByTestId("simple-flow-locked")).toHaveCount(0);
    expect(syncs).toBe(0);
  });

  test("a version that arrives while a diagram save is on its way is still asked about, and Ota uudempi versio writes it back", async ({
    page,
  }) => {
    test.setTimeout(150_000);
    await openFlow(page);
    await waitForDiagram(page);
    await openBlueprintEditor(page);
    await page.getByTestId("blueprint-json-toggle").click();
    const blueprint = JSON.parse(await page.getByTestId("blueprint-json-editor").inputValue()) as {
      steps: { id: string; name: string; type: string }[];
    };
    await page.getByTestId("blueprint-done").click();
    await selectWorkspaceTab(page, "Työnkulku");
    await waitForDiagram(page);
    const canvasTask = (id: string) => page.locator(`.bpmn-editable [data-element-id="${id}"]`);
    const choice = page.getByTestId("bpmn-changed-elsewhere");

    // A deleted step is on its way to the server, held there.
    const release = await holdFirstSync(page);
    let syncs = 0;
    page.on("request", (r) => {
      if (isSync(r)) syncs += 1;
    });
    await page.getByTestId("flow-step-list").locator("li").nth(3).getByRole("button").first().click();
    await page.locator('.djs-context-pad .entry[data-action="delete"]').click();
    await page.getByTestId("bpmn-save").click();
    await expect.poll(() => syncs).toBe(1);

    // Meanwhile the agent writes a version with a new step, and the page
    // draws its diagram: the canvas keeps its own while the save is going.
    const res = await page.request.patch("/api/sessions/ses_laskut/blueprint", {
      data: {
        content: { ...blueprint, steps: [...blueprint.steps, { id: "report", name: "Monthly report", type: "ai" }] },
        note: "e2e: the agent's version",
      },
    });
    expect(res.status()).toBe(200);
    const redrawn = page.waitForResponse((r) => /\/bpmn$/.test(r.url()) && r.request().method() === "GET");
    await chatTurn(page);
    await redrawn;

    // The save was made on the version before the agent's, so the server
    // refuses it (409 changed_elsewhere) rather than write over the agent's
    // version. The canvas keeps the user's edit, and the choice is theirs.
    release();
    await expect(choice).toBeVisible({ timeout: 30_000 });
    await expect(page.locator(".bpmn-editable")).toHaveAttribute("aria-busy", "false");
    await expect(canvasTask("Activity_approve")).toHaveCount(0);
    await expect(canvasTask("Activity_report")).toHaveCount(0);

    // The newer version is written back, so a reload shows it too.
    await choice.getByRole("button", { name: "Ota uudempi versio" }).click();
    await expect(canvasTask("Activity_report")).toBeVisible({ timeout: 30_000 });
    await expect(canvasTask("Activity_approve")).toBeVisible();
    await expect(choice).toHaveCount(0);
    expect(syncs).toBe(1);
    await page.reload();
    await selectWorkspaceTab(page, "Työnkulku");
    await openBpmnView(page);
    await waitForDiagram(page);
    await expect(canvasTask("Activity_report")).toBeVisible();
    await expect(canvasTask("Activity_approve")).toBeVisible();
  });

  test("a save the validation refuses shows its errors and leaves the name field usable", async ({ page }) => {
    await page.route("**/api/sessions/ses_laskut/bpmn/sync", (route) =>
      route.fulfill({
        status: 422,
        contentType: "application/json",
        body: JSON.stringify({
          error: "bpmn_lint_failed",
          lint: {
            ok: false,
            errors: [{ rule: "no-disconnected", id: "Activity_classify", message: "Element is not connected" }],
            warnings: [],
          },
        }),
      }),
    );
    await openFlow(page);
    await waitForDiagram(page);
    const rows = page.getByTestId("flow-step-list").locator("li");
    await rows.nth(2).getByRole("button").first().click();
    const name = page.getByTestId("bpmn-property-name");
    await name.fill("Cost centre proposal");

    const status = page.getByTestId("bpmn-status");
    await expect(status).toContainText("Ei tallennettu: kaaviossa on virheitä");
    await expect(status).toContainText("no-disconnected (Activity_classify): Element is not connected");
    // Typing goes on, and the other tabs still have the saved name.
    await name.pressSequentially(" v2");
    await expect(name).toHaveValue("Cost centre proposal v2");
    await expect(rows.nth(2)).toContainText("Classification");
  });

  test("a failed save says so and saves on Yritä uudelleen", async ({ page }) => {
    test.setTimeout(120_000);
    let fail = true;
    await page.route("**/api/sessions/ses_laskut/bpmn/sync", (route) =>
      fail ? route.fulfill({ status: 500, body: "BPMN sync failed" }) : route.continue(),
    );
    await openFlow(page);
    await waitForDiagram(page);
    const rows = page.getByTestId("flow-step-list").locator("li");
    await rows.nth(0).getByRole("button").first().click();
    await page.getByTestId("bpmn-property-name").fill("Receive the invoice");

    const status = page.getByTestId("bpmn-status");
    await expect(status).toContainText("Tallennus epäonnistui");
    await expect(rows.nth(0)).toContainText("Invoice intake");

    fail = false;
    const sync = page.waitForResponse((r) => r.url().includes("/bpmn/sync") && r.status() === 200);
    await status.getByRole("button", { name: "Yritä uudelleen" }).click();
    await sync;
    await expect(status).toContainText("Tallennettu", { timeout: 15_000 });
    await expect(rows.nth(0)).toContainText("Receive the invoice");
  });

  test("the palette offers only what a save keeps", async ({ page }) => {
    await openFlow(page);
    await waitForDiagram(page);
    const entries = page.locator(".bpmn-editable .djs-palette .entry");
    await expect(entries).toHaveCount(2);
    await expect(entries.nth(0)).toHaveAttribute("title", /^Lisää tehtävä/);
    await expect(entries.nth(1)).toHaveAttribute("title", /^Yhdistä/);

    // The context pad of a task: rename and delete, nothing else.
    await page.getByTestId("flow-step-list").locator("li").nth(1).getByRole("button").first().click();
    const pad = page.locator(".djs-context-pad .entry");
    await expect(pad).toHaveCount(2);
    await expect(pad.nth(0)).toHaveAttribute("title", "Nimeä uudelleen");
    await expect(pad.nth(1)).toHaveAttribute("title", "Poista");

    // A task the generator draws by itself is not a step: a save would undo a
    // rename or a delete, so it has neither, by the pad, the name field or the keys.
    await page.getByTestId("bpmn-zoom-controls").getByRole("button", { name: "Sovita näkymään" }).click();
    const generated = page.locator('.bpmn-editable [data-element-id="Activity_submit_finance_system"]');
    await generated.click();
    await expect(generated).toHaveClass(/selected/);
    await expect(pad).toHaveCount(0);
    await expect(page.getByTestId("bpmn-properties")).toHaveCount(0);
    await page.keyboard.press("Delete");
    await generated.dblclick();
    await expect(page.locator(".bpmn-editable .djs-direct-editing-parent")).toHaveCount(0);
    await expect(generated).toBeVisible();
    await expect(page.getByTestId("bpmn-status")).toHaveCount(0);
  });

  test("Yhdistä draws the order of the steps, and no line to or from a data object", async ({ page }) => {
    await openFlow(page);
    await waitForDiagram(page);
    await page.getByTestId("bpmn-zoom-controls").getByRole("button", { name: "Sovita näkymään" }).click();
    const connections = page.locator(".bpmn-editable .djs-connection");
    const before = await connections.count();
    const task = (id: string) => page.locator(`.bpmn-editable .djs-shape[data-element-id="${id}"]`);
    const data = page.locator('.bpmn-editable .djs-shape[data-element-id^="Data"]').first();
    await expect(data).toBeVisible();
    const connect = async (from: ReturnType<typeof task>, to: ReturnType<typeof task>) => {
      await page.locator('.bpmn-editable .djs-palette .entry[data-action="global-connect-tool"]').click();
      await from.click();
      await to.hover();
      await to.click();
      await page.keyboard.press("Escape");
    };

    // From a data object, and to one: nothing is drawn, so nothing is unsaved.
    await connect(data, task("Activity_approve"));
    await connect(task("Activity_ingest"), data);
    await expect(connections).toHaveCount(before);
    await expect(page.getByTestId("bpmn-status")).toHaveCount(0);

    // The same gesture between two steps draws a flow.
    await connect(task("Activity_ingest"), task("Activity_approve"));
    await expect(connections).toHaveCount(before + 1);
    await expect(page.getByTestId("bpmn-status")).toContainText("Muutoksia ei ole tallennettu");
  });

  test("the end of a line dragged onto a data object leaves the line as it was", async ({ page }) => {
    await openFlow(page);
    await waitForDiagram(page);
    await page.getByTestId("bpmn-zoom-controls").getByRole("button", { name: "Sovita näkymään" }).click();
    const flow = page.locator('.bpmn-editable .djs-connection[data-element-id="Flow_1"]');
    const connections = page.locator(".bpmn-editable .djs-connection");
    const before = await connections.count();
    const line = (await flow.locator(".djs-hit").first().boundingBox())!;
    const data = (await page.locator('.bpmn-editable .djs-shape[data-element-id^="Data"]').first().boundingBox())!;
    const dragEndTo = async (x: number, y: number) => {
      // The handles of a line show while the pointer is on it; the last one is its end.
      await page.mouse.move(line.x + line.width / 2, line.y + line.height / 2);
      await page.mouse.move(line.x + line.width - 1, line.y + line.height / 2, { steps: 4 });
      await page.mouse.down();
      await page.mouse.move(x, y, { steps: 12 });
      await page.mouse.up();
    };

    // bpmn-js would make the flow a data association, which a save does not read.
    await dragEndTo(data.x + data.width / 2, data.y + data.height / 2);
    await expect(flow).toHaveCount(1);
    await expect(connections).toHaveCount(before);
    await expect(page.getByTestId("bpmn-status")).toHaveCount(0);
  });

  test("a language switch keeps an unsaved canvas edit and names the tools in the new language", async ({ page }) => {
    await openFlow(page);
    await waitForDiagram(page);

    // An unsaved structural edit: the Approval step is deleted.
    await page.getByTestId("flow-step-list").locator("li").nth(3).getByRole("button").first().click();
    await page.locator('.djs-context-pad .entry[data-action="delete"]').click();
    await expect(page.getByTestId("bpmn-save")).toBeVisible();

    // The language is chosen in the menu of the account row at the sidebar's foot.
    await (await openAccountMenu(page)).locator('button[name="locale"][value="en"]').click();
    const entries = page.locator(".bpmn-editable .djs-palette .entry");
    await expect(entries.nth(0)).toHaveAttribute("title", /^Add a task/);
    await expect(entries.nth(1)).toHaveAttribute("title", /^Connect steps/);

    // The diagram was not loaded again over the edit.
    await expect(page.getByTestId("bpmn-status")).toContainText("Unsaved changes");
    await expect(page.locator('.bpmn-editable [data-element-id="Activity_approve"]')).toHaveCount(0);
    await expect(page.locator('.bpmn-editable [data-element-id="Activity_classify"]')).toBeVisible();
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
