import { test, expect, type Page } from "@playwright/test";
import { loginAsDev } from "./helpers/auth";
import { setMockSessionStep } from "./helpers/dev-step";
import { resetMockSessions } from "./helpers/mock";
import { openBlueprintEditor, openBpmnView, selectWorkspaceTab, setChatOpen } from "./helpers/workspace";

/**
 * The Workflow tab's simple flow: one node a step, drawn from the blueprint.
 * It is what the tab opens on; the BPMN editor is behind "Avaa BPMN-kaaviona"
 * (e2e/bpmn-editing.spec.ts). Mock store: ses_chatbot is moved to step 8, where
 * the flow can be edited; ses_laskut stands at Gate 3 (step 11), after Gate 2,
 * where it opens read-only.
 */

const flow = (page: Page) => page.getByTestId("simple-flow");
const node = (page: Page, index: number) => page.getByTestId(`simple-flow-node-${index}`);
const nodes = (page: Page) => page.getByTestId(/^simple-flow-node-\d+$/);
const menu = (page: Page) => page.getByTestId("simple-flow-menu");
const listRows = (page: Page) => page.getByTestId("flow-step-list").locator("li");
const isPatch = (r: { url(): string; method(): string }) => r.url().endsWith("/blueprint") && r.method() === "PATCH";

type SavedStep = { id: string; name: string; type: string; component?: string };

/** The steps of every blueprint the page saves from now on. */
function recordSaves(page: Page): SavedStep[][] {
  const saves: SavedStep[][] = [];
  page.on("request", (r) => {
    if (isPatch(r)) saves.push((r.postDataJSON() as { content: { steps: SavedStep[] } }).content.steps);
  });
  return saves;
}

/** ses_chatbot at the diagram step, on the Workflow tab: before Gate 2, so the flow can be edited. */
async function openEditable(page: Page, request: Parameters<typeof setMockSessionStep>[0], baseURL: string | undefined) {
  await setMockSessionStep(request, baseURL as string, "ses_chatbot", 8);
  await loginAsDev(page);
  await page.goto("/sessions/ses_chatbot");
  await selectWorkspaceTab(page, "Työnkulku");
  await expect(node(page, 0)).toBeVisible({ timeout: 30_000 });
}

/** ses_laskut at Gate 3, on the Workflow tab: after Gate 2. */
async function openAfterGate2(page: Page) {
  await loginAsDev(page);
  await page.goto("/sessions/ses_laskut");
  await selectWorkspaceTab(page, "Työnkulku");
  await expect(node(page, 0)).toBeVisible({ timeout: 30_000 });
}

/** Every node of the flow lies inside the canvas, under the zoom controls. */
async function expectAllInView(page: Page) {
  const canvas = (await page.locator(".simple-flow").boundingBox())!;
  const controls = (await page.getByTestId("simple-flow-zoom-controls").boundingBox())!;
  const all = [...(await nodes(page).all()), ...(await page.getByTestId("simple-flow-outcomes").all())];
  expect(all.length).toBeGreaterThan(0);
  for (const el of all) {
    const box = (await el.boundingBox())!;
    expect(box.x).toBeGreaterThanOrEqual(canvas.x);
    expect(box.x + box.width).toBeLessThanOrEqual(canvas.x + canvas.width);
    expect(box.y).toBeGreaterThanOrEqual(controls.y + controls.height);
    expect(box.y + box.height).toBeLessThanOrEqual(canvas.y + canvas.height);
  }
}

const zoomLevel = async (page: Page) =>
  Number((await page.getByTestId("simple-flow-zoom-level").innerText()).replace(/[^\d]/g, ""));

/**
 * One chat turn in which the wizard writes a blueprint version: the mock
 * session is written while the reply is on its way, the way the wizard's own
 * tool writes a real one, and the page reads the session when the reply ends.
 */
async function chatTurnThatWrites(page: Page, sessionId: string, content: unknown) {
  await page.route("**/api/sessions/*/chat", async (route) => {
    if (route.request().method() !== "POST") return route.continue();
    const written = await page.request.patch(`/api/sessions/${sessionId}/blueprint`, {
      data: { content, note: "e2e: the wizard's version" },
    });
    expect(written.status()).toBe(200);
    return route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body: [{ delta: "Vaihdoin vaiheen nimen." }, { done: true }].map((f) => `data: ${JSON.stringify(f)}\n\n`).join(""),
    });
  });
  await setChatOpen(page, true);
  const field = page.locator('textarea[name="message"]');
  await field.fill("Vaihda toisen vaiheen nimi.");
  await field.press("Enter");
  await expect(page.locator('[data-testid="chat-message"][data-role="assistant"]').last()).toContainText(
    "Vaihdoin vaiheen nimen.",
  );
  await page.unroute("**/api/sessions/*/chat");
}

test.describe("Workflow tab: the simple flow", () => {
  test.beforeEach(async ({ request }) => {
    await resetMockSessions(request);
  });

  test.describe("at 1440 x 900", () => {
    test.use({ viewport: { width: 1440, height: 900 } });

    test("opens on the flow, whole and readable beside the open chat", async ({ page }) => {
      await openAfterGate2(page);
      // The session waits on a gate, so the chat is open beside the tab.
      await expect(page.getByTestId("chat-dock")).toHaveAttribute("data-chat-open", "true");

      await expect(page.getByTestId("flow-view-diagram")).toHaveAttribute("aria-pressed", "true");
      await expect(page.getByTestId("flow-view-bpmn")).toHaveAttribute("aria-pressed", "false");
      await expect(page.getByTestId("flow-view-bpmn")).toHaveText("Avaa BPMN-kaaviona");
      // The BPMN editor is not loaded until it is asked for.
      await expect(page.locator(".bpmn-editable")).toHaveCount(0);

      // One node a step, in the blueprint's order.
      await expect(nodes(page)).toHaveCount(5);
      await expect(nodes(page)).toContainText([
        "Invoice intake",
        "Data extraction",
        "Classification",
        "Approval",
        "Export to finance system",
      ]);
      await expectAllInView(page);
      expect(await zoomLevel(page)).toBeGreaterThanOrEqual(85);

      // Who does a step comes from the diagram's lanes, once the server has drawn it.
      // A screen reader hears the words on the node in their order, then the type the icon shows.
      await expect(node(page, 3)).toHaveAccessibleName(/^Vaihe 4: Approval Reviewer ?, Ihmisen tarkistus$/, {
        timeout: 30_000,
      });
      await expect(node(page, 3)).toContainText("Reviewer");
      await expect(node(page, 1)).toHaveAccessibleName(/^Vaihe 2: Data extraction GenAI ?, Tekoäly$/);

      // The review's two outcomes: the arrow on is the approval, the other ends the process.
      await expect(page.locator(".simple-flow").getByText("Hyväksyy", { exact: true })).toHaveCount(1);
      await expect(page.getByTestId("simple-flow-outcomes")).toContainText("Hylkää: käsittely päättyy");
      // A screen reader hears both with the review.
      await expect(node(page, 3)).toHaveAccessibleDescription(
        /Hyväksyy: jatkuu vaiheeseen 5.*Hylkää: käsittely päättyy/,
      );
    });

    test("fits again when the chat closes, and a view the user picked stays through a resize", async ({ page }) => {
      await openAfterGate2(page);
      const besideChat = (await page.locator(".simple-flow").boundingBox())!.width;
      await setChatOpen(page, false);
      await expect
        .poll(async () => (await page.locator(".simple-flow").boundingBox())!.width)
        .toBeGreaterThan(besideChat);
      await expectAllInView(page);

      await page.getByTestId("simple-flow-zoom-controls").getByRole("button", { name: "Lähennä" }).click();
      const picked = await zoomLevel(page);
      await setChatOpen(page, true);
      await expect.poll(async () => (await page.locator(".simple-flow").boundingBox())!.width).toBe(besideChat);
      expect(await zoomLevel(page)).toBe(picked);

      await page.getByTestId("simple-flow-zoom-controls").getByRole("button", { name: "Sovita näkymään" }).click();
      await expectAllInView(page);
    });

    test("the corner button lays the diagram over the whole window, fitted, and Esc puts the page back", async ({
      page,
    }) => {
      await openAfterGate2(page);
      const box = page.getByTestId("flow-diagram-box");
      const controls = page.getByTestId("simple-flow-zoom-controls");
      const beside = (await box.boundingBox())!;
      const besideZoom = await zoomLevel(page);

      await controls.getByRole("button", { name: "Suurenna kaavio" }).click();
      await expect(box).toHaveAttribute("data-full-view", "true");
      await expect.poll(async () => Math.round((await box.boundingBox())!.width)).toBe(1440);
      expect(Math.round((await box.boundingBox())!.height)).toBe(900);
      // The tab's AI notice is under the large view, so the view says it itself.
      await expect(page.getByTestId("flow-full-view-ai-mark")).toBeVisible();
      // The flow is fitted to the larger canvas: larger than beside the chat, all of it in view.
      await expect.poll(() => zoomLevel(page)).toBeGreaterThan(besideZoom);
      await expectAllInView(page);
      // Nothing of the page lies over it, and the focus stays inside it.
      const covered = await box.evaluate((el) => {
        let under = 0;
        for (let x = 8; x < innerWidth; x += 120) {
          for (let y = 8; y < innerHeight; y += 90) {
            if (!el.contains(document.elementFromPoint(x, y))) under += 1;
          }
        }
        return under;
      });
      expect(covered).toBe(0);
      const smaller = controls.getByRole("button", { name: "Pienennä kaavio" });
      await expect(smaller).toBeFocused();
      await expect(smaller).toHaveAttribute("aria-pressed", "true");
      // Tab goes round the diagram's own stops: past the last one it is on the first again,
      // every button is reached on the way, and the round ends where it began.
      const buttons = await box.evaluate(
        (el) => Array.from(el.querySelectorAll("button:not([disabled])")).filter((b) => b.getClientRects().length > 0).length,
      );
      let reached = 0;
      for (let i = 0; i < 40; i += 1) {
        await page.keyboard.press("Tab");
        expect(await box.evaluate((el) => el.contains(document.activeElement))).toBe(true);
        if (await page.evaluate(() => document.activeElement?.tagName === "BUTTON")) reached += 1;
        if (await smaller.evaluate((el) => el === document.activeElement)) break;
      }
      await expect(smaller).toBeFocused();
      expect(reached).toBe(buttons);
      await page.keyboard.press("Shift+Tab");
      await page.keyboard.press("Shift+Tab");
      await page.keyboard.press("Shift+Tab");
      await page.keyboard.press("Shift+Tab");
      expect(await box.evaluate((el) => el.contains(document.activeElement))).toBe(true);

      // A step still opens its menu there, and Esc closes the menu first, then the large view.
      await node(page, 1).click();
      await expect(menu(page)).toBeVisible();
      await page.keyboard.press("Escape");
      await expect(menu(page)).toHaveCount(0);
      await expect(box).toHaveAttribute("data-full-view", "true");
      await page.keyboard.press("Escape");
      await expect(box).toHaveAttribute("data-full-view", "false");
      await expect.poll(async () => (await box.boundingBox())!.width).toBe(beside.width);
      await expect.poll(() => zoomLevel(page)).toBe(besideZoom);
      await expect(controls.getByRole("button", { name: "Suurenna kaavio" })).toBeFocused();

      // A step handed to the chat from the large view: the view steps aside, and the chat has the cursor.
      await controls.getByRole("button", { name: "Suurenna kaavio" }).click();
      await expect(box).toHaveAttribute("data-full-view", "true");
      await node(page, 2).click();
      await page.getByTestId("simple-flow-ask").click();
      await expect(box).toHaveAttribute("data-full-view", "false");
      await expect(page.getByTestId("chat-reference")).toContainText("Vaihe 3 · Classification");
      await expect(page.locator('textarea[name="message"]')).toBeFocused();
    });

    test("fitting and enlarging are two buttons, and the large view does not come back by itself", async ({
      page,
    }) => {
      await openAfterGate2(page);
      const controls = page.getByTestId("simple-flow-zoom-controls");
      const box = page.getByTestId("flow-diagram-box");
      // Zoom out, zoom in, fit, enlarge; the level between them is a figure, not a control.
      await expect(controls.getByRole("button")).toHaveCount(4);
      const fitted = await zoomLevel(page);
      await controls.getByRole("button", { name: "Lähennä" }).click();
      await expect.poll(() => zoomLevel(page)).toBeGreaterThan(fitted);
      await controls.getByRole("button", { name: "Sovita näkymään" }).click();
      await expect.poll(() => zoomLevel(page)).toBe(fitted);
      await expect(box).toHaveAttribute("data-full-view", "false");

      // Where the list and the diagram take turns, the list takes the large diagram's place
      // (asked for from the page's own switch, which the large view covers): the diagram comes
      // back in its place in the tab, not over the window by itself.
      await page.setViewportSize({ width: 700, height: 900 });
      await controls.getByRole("button", { name: "Suurenna kaavio" }).click();
      await expect(box).toHaveAttribute("data-full-view", "true");
      await page.evaluate(() => document.querySelector<HTMLElement>('[data-testid="flow-view-list"]')?.click());
      await expect(box).toBeHidden();
      await page.getByTestId("flow-view-diagram").click();
      await expect(box).toBeVisible();
      await expect(box).toHaveAttribute("data-full-view", "false");
    });

    test("a rename saves to the blueprint, shows in the list, and changes nothing but the name", async ({
      page,
      request,
      baseURL,
    }) => {
      await openEditable(page, request, baseURL);
      const saves = recordSaves(page);
      const syncs: string[] = [];
      page.on("request", (r) => {
        if (r.url().includes("/bpmn/sync")) syncs.push(r.url());
      });

      // "Customer question" is a step without a component: an automatic "io" step.
      await node(page, 0).click();
      const name = page.getByTestId("simple-flow-name");
      await expect(name).toHaveValue("Customer question");
      const saved = page.waitForResponse((r) => isPatch(r.request()));
      await name.fill("Question from the web shop");
      await name.press("Enter");
      expect((await saved).status()).toBe(200);
      await expect(page.getByTestId("simple-flow-status")).toHaveText("Tallennettu");

      // The node and the list beside it carry the new name.
      await expect(node(page, 0)).toContainText("Question from the web shop");
      await expect(listRows(page).nth(0)).toContainText("Question from the web shop");
      // Only the name changed: the step is still "Syöte tai tulos", not an AI step.
      expect(saves).toHaveLength(1);
      expect(saves[0].map((s) => `${s.id}:${s.type}:${s.component ?? ""}`)).toEqual([
        "input:io:",
        "retrieve:ai:pgvector",
        "generate:ai:Azure OpenAI",
        "review:human_review:",
        "respond:io:",
      ]);
      await expect(listRows(page).nth(0)).toContainText("Syöte tai tulos");
      // The flow never writes BPMN: the save went to the blueprint alone.
      expect(syncs).toEqual([]);

      // The blueprint itself has it: the Blueprint tab reads the same version.
      await openBlueprintEditor(page);
      await page.getByTestId("blueprint-json-toggle").click();
      const blueprint = JSON.parse(await page.getByTestId("blueprint-json-editor").inputValue()) as {
        steps: SavedStep[];
      };
      expect(blueprint.steps[0]).toMatchObject({ id: "input", name: "Question from the web shop", type: "io" });
    });

    test("an empty name is not saved, and Escape gives up what was typed", async ({ page, request, baseURL }) => {
      await openEditable(page, request, baseURL);
      const saves = recordSaves(page);
      await node(page, 1).click();
      const name = page.getByTestId("simple-flow-name");

      await name.fill("   ");
      await name.press("Enter");
      await expect(name).toHaveValue("Retrieval (RAG)");

      await name.fill("Something else");
      await name.press("Escape");
      await expect(name).toHaveValue("Retrieval (RAG)");
      await expect(menu(page)).toBeVisible();
      await name.press("Escape");
      await expect(menu(page)).toHaveCount(0);
      expect(saves).toEqual([]);
    });

    test("a save made on a version the wizard has replaced is refused, and the flow shows the newer one", async ({
      page,
      request,
      baseURL,
    }) => {
      await openEditable(page, request, baseURL);
      const saves = recordSaves(page);

      // The blueprint as the page has it, and a version written since (the agent, from the chat).
      await openBlueprintEditor(page);
      await page.getByTestId("blueprint-json-toggle").click();
      const blueprint = JSON.parse(await page.getByTestId("blueprint-json-editor").inputValue()) as {
        steps: SavedStep[];
      };
      await page.getByTestId("blueprint-done").click();
      await selectWorkspaceTab(page, "Työnkulku");
      await expect(node(page, 0)).toBeVisible();
      const steps = blueprint.steps.map((s) => (s.id === "retrieve" ? { ...s, name: "Search the knowledge base" } : s));
      const written = await page.request.patch("/api/sessions/ses_chatbot/blueprint", {
        data: { content: { ...blueprint, steps }, note: "e2e: the agent's version" },
      });
      expect(written.status()).toBe(200);

      // A rename made on the older version is not written over the newer one.
      await node(page, 0).click();
      const refused = page.waitForResponse((r) => isPatch(r.request()));
      await page.getByTestId("simple-flow-name").fill("Question from the web shop");
      await page.getByTestId("simple-flow-name").press("Enter");
      expect((await refused).status()).toBe(409);
      await expect(page.getByTestId("simple-flow-status")).toContainText("Blueprint muuttui muualla");

      // The flow is drawn from the newer version, and the user's change is not in it.
      await expect(node(page, 1)).toContainText("Search the knowledge base");
      await expect(node(page, 0)).toContainText("Customer question");
      expect(saves).toHaveLength(1);

      // Made again on the version now shown, it saves.
      const saved = page.waitForResponse((r) => isPatch(r.request()));
      await page.getByTestId("simple-flow-name").fill("Question from the web shop");
      await page.getByTestId("simple-flow-name").press("Enter");
      expect((await saved).status()).toBe(200);
      await expect(node(page, 0)).toContainText("Question from the web shop");
      await expect(node(page, 1)).toContainText("Search the knowledge base");
    });

    test("a version the wizard writes in the chat is drawn, and both diagrams say so with the version", async ({
      page,
      request,
      baseURL,
    }) => {
      test.setTimeout(120_000);
      await openEditable(page, request, baseURL);
      // Nothing has changed yet, so the canvas has nothing to say.
      await expect(page.getByTestId("simple-flow-status")).toHaveCount(0);

      // The blueprint as the page has it; the seed session stands on version 3.
      await openBlueprintEditor(page);
      await page.getByTestId("blueprint-json-toggle").click();
      const blueprint = JSON.parse(await page.getByTestId("blueprint-json-editor").inputValue()) as {
        steps: SavedStep[];
      };
      await page.getByTestId("blueprint-done").click();
      await selectWorkspaceTab(page, "Työnkulku");
      await expect(node(page, 1)).toContainText("Retrieval (RAG)");

      const steps = blueprint.steps.map((s) => (s.id === "retrieve" ? { ...s, name: "Search the knowledge base" } : s));
      await chatTurnThatWrites(page, "ses_chatbot", { ...blueprint, steps });

      // The flow is drawn from the wizard's version, and says which one it shows and where it came from.
      await expect(node(page, 1)).toContainText("Search the knowledge base");
      const status = page.getByTestId("simple-flow-status");
      await expect(status).toHaveText("Päivitetty chatista · blueprintin versio 4");
      await expect(status).toHaveAttribute("role", "status");

      // A newer version with the same content (a step forward writes one) moves the number:
      // the line names the session's active version, not the one it first saw.
      await chatTurnThatWrites(page, "ses_chatbot", { ...blueprint, steps });
      await expect(status).toHaveText("Päivitetty chatista · blueprintin versio 5");

      // The BPMN view of the same blueprint says the same.
      await setChatOpen(page, false);
      await openBpmnView(page);
      await expect(page.locator('.bpmn-editable [data-element-id="Activity_retrieve"]')).toBeVisible({
        timeout: 45_000,
      });
      await expect(page.getByTestId("bpmn-updated")).toHaveText("Päivitetty chatista · blueprintin versio 5");

      // A save made here is the user's own version: the line gives way to "Tallennettu".
      await page.getByTestId("flow-view-diagram").click();
      await expect(page.getByTestId("simple-flow-updated")).toHaveText("Päivitetty chatista · blueprintin versio 5");
      await node(page, 0).click();
      const saved = page.waitForResponse((r) => isPatch(r.request()));
      await page.getByTestId("simple-flow-name").fill("Question from the web shop");
      await page.getByTestId("simple-flow-name").press("Enter");
      expect((await saved).status()).toBe(200);
      await expect(status).toHaveText("Tallennettu");
      await expect(page.getByTestId("simple-flow-updated")).toHaveCount(0);
    });

    test("adds a step and a human review after a step, and removes one with an undo", async ({
      page,
      request,
      baseURL,
    }) => {
      await openEditable(page, request, baseURL);
      const saves = recordSaves(page);

      // A step after the second one: it is picked, its name ready to be typed over.
      await node(page, 1).click();
      await page.getByTestId("simple-flow-add-step").click();
      await expect(nodes(page)).toHaveCount(6);
      await expect(node(page, 2)).toContainText("Uusi vaihe");
      await expect(node(page, 2)).toHaveAttribute("aria-pressed", "true");
      const name = page.getByTestId("simple-flow-name");
      await expect(name).toBeFocused();
      await expect(name).toHaveValue("Uusi vaihe");
      const renamed = page.waitForResponse((r) => isPatch(r.request()));
      await page.keyboard.type("Rank the articles");
      await page.keyboard.press("Enter");
      expect((await renamed).status()).toBe(200);
      await expect(node(page, 2)).toContainText("Rank the articles");
      await expect(listRows(page)).toHaveCount(6);
      await expect(listRows(page).nth(2)).toContainText("Rank the articles");
      expect(saves.at(-1)![2]).toMatchObject({ name: "Rank the articles", type: "io" });

      // A human review after it: a second review, with its own outcomes.
      await expect(page.getByTestId("simple-flow-outcomes")).toHaveCount(1);
      await page.getByTestId("simple-flow-add-review").click();
      await expect(nodes(page)).toHaveCount(7);
      await expect(node(page, 3)).toContainText("Ihmisen tarkistus");
      await expect(page.getByTestId("simple-flow-outcomes")).toHaveCount(2);
      expect(saves.at(-1)![3]).toMatchObject({ name: "Ihmisen tarkistus", type: "human_review" });
      await expect(listRows(page)).toHaveCount(7);

      // Remove it; "Kumoa" brings it back at its place.
      await page.getByTestId("simple-flow-remove").click();
      await expect(nodes(page)).toHaveCount(6);
      await expect(page.getByTestId("simple-flow-status")).toContainText("Vaihe poistettu");
      await expect(page.getByTestId("simple-flow-undo")).toBeFocused();
      await page.getByTestId("simple-flow-undo").click();
      await expect(nodes(page)).toHaveCount(7);
      await expect(node(page, 3)).toContainText("Ihmisen tarkistus");
      await expect(listRows(page)).toHaveCount(7);
      await expectAllInView(page);
    });

    test("after Gate 2 the canvas says why editing is off, and a step still leads to the wizard", async ({
      page,
    }) => {
      await openAfterGate2(page);
      const saves = recordSaves(page);

      const locked = page.getByTestId("simple-flow-locked");
      await expect(locked).toContainText(
        "Vain luku: muutos vaatii uuden paketin ja testiajon. Valitse vaihe ja pyydä muutosta wizardilta.",
      );

      // A click on a step shows what it is and one thing to do: ask the wizard.
      await node(page, 2).click();
      await expect(menu(page)).toBeVisible();
      await expect(page.getByTestId("simple-flow-name-text")).toHaveText("Classification");
      await expect(page.getByTestId("simple-flow-name")).toHaveCount(0);
      await expect(menu(page).getByRole("button")).toHaveText(["", "Pyydä wizardia muuttamaan tätä vaihetta"]);

      await page.getByTestId("simple-flow-ask").click();
      // The chat has the step as its reference chip; nothing is sent by itself.
      await expect(page.getByTestId("chat-reference")).toContainText("Vaihe 3 · Classification");
      await expect(page.getByTestId("chat-dock")).toHaveAttribute("data-chat-open", "true");
      await expect(page.locator('textarea[name="message"]')).toBeFocused();
      await expect(menu(page)).toHaveCount(0);
      expect(saves).toEqual([]);

      // "Muokkaa kaaviota" opens the edits here, as on the Blueprint tab.
      await locked.getByRole("button", { name: "Muokkaa kaaviota" }).click();
      await expect(locked).toHaveCount(0);
      await node(page, 2).click();
      await expect(page.getByTestId("simple-flow-name")).toHaveValue("Classification");
      await expect(page.getByTestId("simple-flow-remove")).toBeVisible();

      // One lock for the two diagrams: the BPMN editor is open too. Without
      // wizard_api (the mock store) it has no tools and says it is read-only.
      await openBpmnView(page, { edit: false });
      await expect(page.getByTestId("bpmn-panel")).toHaveAttribute("data-locked", "false", { timeout: 45_000 });
      await expect(page.getByTestId("bpmn-locked")).toHaveCount(0);
      await expect(page.getByTestId("bpmn-readonly-editing")).toBeVisible();
      await expect(page.locator(".bpmn-editable .djs-palette")).toHaveCount(0);
    });

    test("before Gate 2 nothing is locked, and a step's menu asks the wizard too", async ({
      page,
      request,
      baseURL,
    }) => {
      await openEditable(page, request, baseURL);
      await expect(page.getByTestId("simple-flow-locked")).toHaveCount(0);

      await node(page, 3).click();
      await page.getByTestId("simple-flow-ask").click();
      await expect(page.getByTestId("chat-reference")).toContainText("Vaihe 4 · Human review");
    });

    test("a step is opened and closed from the keyboard", async ({ page, request, baseURL }) => {
      await openEditable(page, request, baseURL);

      await node(page, 0).focus();
      await page.keyboard.press("Tab");
      await expect(node(page, 1)).toBeFocused();
      await page.keyboard.press("Enter");
      // The menu opens with the cursor in the step's name.
      await expect(menu(page)).toBeVisible();
      await expect(page.getByTestId("simple-flow-name")).toBeFocused();
      await page.keyboard.press("Tab");
      await page.keyboard.press("Tab");
      await expect(page.getByTestId("simple-flow-ask")).toBeFocused();

      await page.keyboard.press("Escape");
      await expect(menu(page)).toHaveCount(0);
      await expect(node(page, 1)).toBeFocused();
    });

    test("the BPMN editor is one click away, and the choice is kept over a visit to another tab", async ({
      page,
    }) => {
      test.setTimeout(90_000);
      await openAfterGate2(page);

      await page.getByTestId("flow-view-bpmn").click();
      await expect(page.locator('.bpmn-editable [data-element-id="Activity_classify"]')).toBeVisible({
        timeout: 45_000,
      });
      await expect(flow(page)).toHaveCount(0);
      await expect(page.getByTestId("flow-view-bpmn")).toHaveAttribute("aria-pressed", "true");

      await selectWorkspaceTab(page, "Blueprint");
      await selectWorkspaceTab(page, "Työnkulku");
      await expect(page.locator('.bpmn-editable [data-element-id="Activity_classify"]')).toBeVisible({
        timeout: 45_000,
      });

      await page.getByTestId("flow-view-diagram").click();
      await expect(nodes(page)).toHaveCount(5);
      await expect(page.locator(".bpmn-editable")).toHaveCount(0);
    });

    test("the flow is drawn when the BPMN diagram cannot be", async ({ page }) => {
      await page.route("**/api/sessions/ses_laskut/bpmn", (route) =>
        route.fulfill({ status: 500, body: "no diagram" }),
      );
      await openAfterGate2(page);

      await expect(nodes(page)).toHaveCount(5);
      await expect(page.getByTestId("flow-diagram-error")).toHaveCount(0);
      // Who does a step is then its type, and a review keeps its two outcomes.
      await expect(node(page, 3)).toHaveAccessibleName("Vaihe 4: Approval Ihmisen tarkistus");
      await expect(page.getByTestId("simple-flow-outcomes")).toContainText("Hylkää: käsittely päättyy");
    });

    test("a long workflow wraps into rows and still shows whole", async ({ page, request, baseURL }) => {
      await setMockSessionStep(request, baseURL as string, "ses_chatbot", 8);
      await loginAsDev(page);
      const steps = [
        { id: "upload", name: "Upload the delivery note", type: "io" },
        { id: "parse", name: "Read the document", type: "ai", component: "docling" },
        { id: "extract", name: "Extract the fields", type: "ai", component: "LLM" },
        { id: "match", name: "Match to the purchase order", type: "ai", component: "pgvector" },
        { id: "check", name: "Warehouse check", type: "human_review" },
        { id: "price", name: "Price the lines", type: "ai", component: "LLM" },
        { id: "approve", name: "Approval", type: "human_review" },
        { id: "export", name: "Export to the ERP", type: "io" },
        { id: "notify", name: "Notify the buyer", type: "io" },
      ];
      const res = await page.request.patch("/api/sessions/ses_chatbot/blueprint", {
        data: { content: { name: "Delivery notes", description: "", goal: "", steps }, note: "e2e: nine steps" },
      });
      expect(res.status()).toBe(200);
      await page.goto("/sessions/ses_chatbot");
      await selectWorkspaceTab(page, "Työnkulku");
      await setChatOpen(page, true);

      await expect(nodes(page)).toHaveCount(9);
      await expect(page.getByTestId("simple-flow-outcomes")).toHaveCount(2);
      await expect(flow(page)).toHaveAttribute("data-columns", "3");
      await expectAllInView(page);
      expect(await zoomLevel(page)).toBeGreaterThanOrEqual(75);
    });
  });

  test.describe("on a phone", () => {
    test.use({ viewport: { width: 390, height: 844 } });

    test("opens on the flow in one column at a readable size, with the list a tap away", async ({ page }) => {
      await openAfterGate2(page);

      await expect(page.getByTestId("flow-view-diagram")).toHaveAttribute("aria-pressed", "true");
      await expect(flow(page)).toHaveAttribute("data-columns", "1");
      expect(await zoomLevel(page)).toBeGreaterThanOrEqual(85);
      // The first steps are on screen, inside the canvas; the rest is a scroll down.
      const canvas = (await page.locator(".simple-flow").boundingBox())!;
      for (const index of [0, 1]) {
        const box = (await node(page, index).boundingBox())!;
        expect(box.x).toBeGreaterThanOrEqual(canvas.x);
        expect(box.x + box.width).toBeLessThanOrEqual(canvas.x + canvas.width);
        await expect(node(page, index)).toBeInViewport();
      }
      // Nothing makes the page scroll sideways.
      const doc = await page.evaluate(() => ({
        sw: document.documentElement.scrollWidth,
        cw: document.documentElement.clientWidth,
      }));
      expect(doc.sw).toBeLessThanOrEqual(doc.cw);

      // A step's menu fits the canvas.
      await node(page, 1).click();
      const box = (await menu(page).boundingBox())!;
      expect(box.x).toBeGreaterThanOrEqual(canvas.x);
      expect(box.x + box.width).toBeLessThanOrEqual(canvas.x + canvas.width);
      await expect(page.getByTestId("simple-flow-ask")).toBeInViewport();

      // The list is the same steps as text.
      await page.getByTestId("flow-view-list").click();
      await expect(listRows(page)).toHaveCount(5);
      await expect(flow(page)).toHaveCount(0);
    });
  });
});
