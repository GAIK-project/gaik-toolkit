import { test, expect, type Page } from "@playwright/test";
import { loginAsDev } from "./helpers/auth";
import { resetMockSessions } from "./helpers/mock";
import { openBlueprintEditor, selectWorkspaceTab, setChatOpen } from "./helpers/workspace";

/**
 * The Blueprint form: one page the tab scrolls, with the control that closes
 * it and the save status in the tab's first row. It saves by itself, says
 * where the draft stands, lists the process steps so they read as the
 * process, and a step opens in place with what can be done to it.
 */

const status = (page: Page) => page.getByTestId("blueprint-save-status");
const rows = (page: Page) => page.locator("ol > li[data-testid^='blueprint-step-']");
const blueprintPatch = (page: Page) =>
  page.waitForResponse((r) => /\/api\/sessions\/[^/]+\/blueprint$/.test(r.url()) && r.request().method() === "PATCH");

// Stops the page's timers (the wait that follows typing among them), so a
// test can tell what a timer did from what happened without one. Requests and
// rendering go on; `page.clock.runFor` lets the timers' time pass.
async function stopTimers(page: Page) {
  await page.clock.install();
  await page.clock.pauseAt(Date.now() + 1_000);
}

async function openForm(page: Page, sessionId: string) {
  await loginAsDev(page);
  await page.goto(`/sessions/${sessionId}`);
  // The tab opens in its read view; the form is behind "Muokkaa".
  await openBlueprintEditor(page);
  await expect(status(page)).toHaveAttribute("data-state", "saved");
}

// The form's save is held on its way to the server, and meanwhile the wizard
// writes a version of its own and its reply ends, so the page reads the
// session again and asks which version stays. `release` lets the held save
// through: it reaches the server after the wizard's version.
async function conflictDuringSave(page: Page) {
  await openForm(page, "ses_ui_basics");
  await setChatOpen(page, true);
  let release: () => void = () => {};
  const held = new Promise<void>((resolve) => (release = resolve));
  const patches: { goal?: string }[] = [];
  await page.route("**/api/sessions/*/blueprint", async (route) => {
    if (route.request().method() !== "PATCH") return route.continue();
    patches.push((route.request().postDataJSON() as { content: { goal?: string } }).content);
    if (patches.length === 1) await held;
    return route.continue();
  });
  await page.getByTestId("blueprint-field-goal").fill("Shorter handling time");
  await page.getByTestId("blueprint-field-name").focus();
  await expect.poll(() => patches.length).toBe(1);

  const theirs = await page.request.patch("/api/sessions/ses_ui_basics/blueprint", {
    data: { content: { ...patches[0], goal: "The wizard's goal" }, note: "agent" },
  });
  expect(theirs.ok()).toBe(true);
  await page.route("**/api/sessions/*/chat", (route) =>
    route.request().method() === "POST"
      ? route.fulfill({
          status: 200,
          contentType: "text/event-stream",
          body: `data: ${JSON.stringify({ delta: "Päivitin tavoitteen." })}

data: ${JSON.stringify({ done: true })}

`,
        })
      : route.continue(),
  );
  const field = page.locator('textarea[name="message"]');
  await field.fill("Päivitä tavoite");
  await field.press("Enter");
  const warning = page.getByTestId("blueprint-changed-elsewhere");
  await expect(warning).toBeVisible({ timeout: 15_000 });
  return { release, patches, warning };
}

test.describe("Blueprint form", () => {
  test.beforeEach(async ({ request }) => {
    await resetMockSessions(request);
  });

  test("saves by itself after an edit and has no save button", async ({ page }) => {
    await openForm(page, "ses_ui_basics");
    await expect(status(page)).toHaveText("Tallennettu");
    await expect(page.getByTestId("blueprint-save")).toHaveCount(0);

    await page.getByTestId("blueprint-step-0-toggle").click();
    const saved = blueprintPatch(page);
    await page.getByTestId("blueprint-step-0-name").fill("Intake of documents");
    const body = (await saved).request().postDataJSON() as { content: { steps: { name: string }[] } };
    expect(body.content.steps.map((s) => s.name)).toEqual(["Intake of documents", "Process"]);
    await expect(status(page)).toHaveText("Tallennettu");
    // What was typed stays in the field, and the card stays open.
    await expect(page.getByTestId("blueprint-step-0-name")).toHaveValue("Intake of documents");

    // The saved blueprint is what a reload shows.
    await page.reload();
    await openBlueprintEditor(page);
    await expect(rows(page).first()).toHaveAttribute("aria-label", "1. Intake of documents");
  });

  test("leaving a field saves at once", async ({ page }) => {
    await openForm(page, "ses_ui_basics");
    // No timer runs from here on: a save that is sent was not sent by the
    // wait that follows typing.
    await stopTimers(page);
    const goal = page.getByTestId("blueprint-field-goal");
    await goal.fill("Shorter handling time");
    const saved = blueprintPatch(page);
    await page.getByTestId("blueprint-field-name").focus();
    await saved;
    await expect(status(page)).toHaveText("Tallennettu");
  });

  test("holds the save while a step has no name, and says why", async ({ page }) => {
    await openForm(page, "ses_ui_basics");
    let patches = 0;
    page.on("request", (r) => {
      if (r.method() === "PATCH" && r.url().endsWith("/blueprint")) patches += 1;
    });

    await stopTimers(page);
    await page.getByTestId("blueprint-step-add").click();
    await expect(rows(page)).toHaveCount(3);
    await expect(page.getByTestId("blueprint-steps-heading")).toHaveText("Prosessin vaiheet (3)");
    // The new step's name field has the cursor.
    await expect(page.getByTestId("blueprint-step-2-name")).toBeFocused();
    await expect(status(page)).toHaveText("Ei tallennettu: anna vaiheelle nimi");
    // Long past the wait that follows typing, on the page's own clock.
    await page.clock.runFor(30_000);
    expect(patches).toBe(0);
    await page.clock.resume();

    const saved = blueprintPatch(page);
    await page.getByTestId("blueprint-step-2-name").fill("Review");
    await saved;
    await expect(status(page)).toHaveText("Tallennettu");
    expect(patches).toBe(1);
  });

  test("Valmis keeps the form open while its draft cannot be saved", async ({ page }) => {
    await openForm(page, "ses_ui_basics");
    await page.getByTestId("blueprint-step-add").click();
    await expect(status(page)).toHaveText("Ei tallennettu: anna vaiheelle nimi");

    // Behind the read view the draft was out of sight, and the read view showed the old steps.
    const note = page.getByTestId("blueprint-done-unsaved");
    await page.getByTestId("blueprint-done").click();
    await expect(note).toHaveText("Lomake pysyy auki, koska muutoksia ei ole voitu tallentaa.");
    await expect(status(page)).toBeVisible();
    await expect(page.getByTestId("solution-plan-view")).toHaveCount(0);

    const saved = blueprintPatch(page);
    await page.getByTestId("blueprint-step-2-name").fill("Review");
    await saved;
    await expect(status(page)).toHaveText("Tallennettu");
    await expect(note).toBeEmpty();
    await page.getByTestId("blueprint-done").click();
    await expect(page.getByTestId("solution-plan-view").getByTestId(/^plan-step-\d+$/)).toHaveCount(3);
  });

  test("a save that fails after Valmis brings the form back", async ({ page }) => {
    let fail = true;
    await page.route("**/api/sessions/ses_ui_basics/blueprint", (route) =>
      fail && route.request().method() === "PATCH" ? route.fulfill({ status: 500, body: "no" }) : route.continue(),
    );
    await openForm(page, "ses_ui_basics");
    await page.getByTestId("blueprint-field-goal").fill("Shorter handling time");
    // Leaving the field for the button sends the save; the form closes before the answer.
    await page.getByTestId("blueprint-done").click();

    await expect(status(page)).toContainText("Tallennus epäonnistui");
    await expect(status(page)).toBeVisible();
    await expect(page.getByTestId("blueprint-done-unsaved")).not.toBeEmpty();
    await expect(page.getByTestId("blueprint-field-goal")).toHaveValue("Shorter handling time");

    fail = false;
    const saved = blueprintPatch(page);
    await page.getByTestId("blueprint-save-retry").click();
    await saved;
    await expect(status(page)).toHaveText("Tallennettu");
    await page.getByTestId("blueprint-done").click();
    await expect(page.getByTestId("solution-plan-view")).toContainText("Shorter handling time");
  });

  test("a reload right after typing asks first, and the edit is sent as the page goes", async ({ page }) => {
    await openForm(page, "ses_ui_basics");
    const dialogs: string[] = [];
    page.on("dialog", (dialog) => {
      dialogs.push(dialog.type());
      void dialog.accept();
    });
    // Within the wait that follows typing, so nothing has been saved yet.
    await page.getByTestId("blueprint-field-goal").fill("Shorter handling time");
    await page.reload();
    expect(dialogs[0]).toBe("beforeunload");

    // The save and the reload cross on their way: the next load has it for certain.
    await expect(async () => {
      await page.reload();
      await expect(page.getByTestId("solution-plan-view")).toContainText("Shorter handling time", { timeout: 2_000 });
    }).toPass({ timeout: 20_000 });
  });

  test("a page that goes during a save sends the newer draft in place of the older one", async ({ page }) => {
    await openForm(page, "ses_ui_basics");
    // The first save is held on its way to the server.
    let release: () => void = () => {};
    const held = new Promise<void>((resolve) => (release = resolve));
    const patches: { goal?: string }[] = [];
    await page.route("**/api/sessions/*/blueprint", async (route) => {
      if (route.request().method() !== "PATCH") return route.continue();
      patches.push((route.request().postDataJSON() as { content: { goal?: string } }).content);
      if (patches.length === 1) await held;
      return route.continue().catch(() => {});
    });
    const failed: string[] = [];
    page.on("requestfailed", (r) => {
      if (r.method() === "PATCH") failed.push(r.url());
    });
    const goal = page.getByTestId("blueprint-field-goal");
    await goal.fill("Shorter handling time");
    await page.getByTestId("blueprint-field-name").focus();
    await expect.poll(() => patches.length).toBe(1);

    // Typed during that save, and the page goes before the form's own wait is over.
    await stopTimers(page);
    await goal.fill("Half the handling time");
    await page.evaluate(() => window.dispatchEvent(new Event("pagehide")));

    // The older save is cancelled, and one save with the newer draft follows it.
    await expect.poll(() => patches.length).toBe(2);
    expect(patches[1].goal).toBe("Half the handling time");
    await expect.poll(() => failed.length).toBe(1);
    release();

    await expect(async () => {
      await page.reload();
      await expect(page.getByTestId("solution-plan-view")).toContainText("Half the handling time", { timeout: 2_000 });
    }).toPass({ timeout: 20_000 });
    // The page stayed here (the event was only fired), so the reload may send
    // the draft once more: never the older one again.
    expect(patches.slice(1).map((p) => p.goal)).not.toContain("Shorter handling time");
  });

  test("a settings row shows its own setting after the one above is removed, and a key in use is not taken", async ({
    page,
  }) => {
    await openForm(page, "ses_ui_basics");
    await page.getByTestId("blueprint-step-0-toggle").click();
    await page.getByTestId("blueprint-step-0-tech").click();
    const key = (n: number) => page.getByTestId(`blueprint-step-0-setting-${n}-key`);
    const value = (n: number) => page.getByTestId(`blueprint-step-0-setting-${n}-value`);
    const add = page.getByTestId("blueprint-step-0-setting-add");

    await add.click();
    await add.click();
    await key(0).fill("model");
    // Tab goes on to the value: the rename does not rebuild the row under the cursor.
    await key(0).press("Tab");
    await expect(value(0)).toBeFocused();
    await value(0).fill("gpt-4o");
    await key(1).fill("language");
    await value(1).fill("fi");

    await page.getByTestId("blueprint-step-0-setting-0-remove").click();
    await expect(key(1)).toHaveCount(0);
    await expect(key(0)).toHaveValue("language");
    await expect(value(0)).toHaveValue("fi");

    // A key another setting has is refused: the field shows the setting's own key again.
    await add.click();
    await expect(key(1)).toHaveValue("setting_2");
    await key(1).fill("language");
    await value(1).fill("en");
    await expect(key(1)).toHaveValue("setting_2");
    await expect(key(0)).toHaveValue("language");

    await page.getByTestId("blueprint-field-name").focus();
    await expect(status(page)).toHaveText("Tallennettu");
    await page.getByTestId("blueprint-json-toggle").click();
    const saved = JSON.parse(await page.getByTestId("blueprint-json-editor").inputValue()) as {
      steps: { settings?: Record<string, string> }[];
    };
    expect(saved.steps[0].settings).toEqual({ language: "fi", setting_2: "en" });
  });

  test("a deleted step can be brought back while the note is shown", async ({ page }) => {
    await openForm(page, "ses_laskut");
    await expect(rows(page)).toHaveCount(5);

    // "Poista vaihe" is in the open step, with the step's other actions.
    await expect(page.getByTestId("blueprint-step-1-remove")).toBeHidden();
    await page.getByTestId("blueprint-step-1-toggle").click();
    await page.getByTestId("blueprint-step-1-remove").click();
    await expect(rows(page)).toHaveCount(4);
    const note = page.getByTestId("blueprint-step-removed");
    await expect(note).toContainText("Vaihe poistettu");
    await note.getByRole("button", { name: "Kumoa" }).click();
    await expect(rows(page)).toHaveCount(5);
    await expect(rows(page).nth(1)).toHaveAttribute("aria-label", "2. Data extraction");
    await expect(note).toHaveCount(0);
    // The step comes back open, as it was.
    await expect(page.getByTestId("blueprint-step-1-name")).toBeVisible();

    // Left alone, the note goes away after five seconds and the step stays deleted.
    await page.getByTestId("blueprint-step-1-remove").click();
    await expect(note).toBeVisible();
    await expect(note).toHaveCount(0, { timeout: 8_000 });
    await expect(rows(page)).toHaveCount(4);
    await expect(status(page)).toHaveText("Tallennettu", { timeout: 10_000 });
  });

  test("a step row reads as the process, and the technical details stay closed", async ({ page }) => {
    await openForm(page, "ses_laskut");
    await expect(page.getByTestId("blueprint-steps-heading")).toHaveText("Prosessin vaiheet (5)");

    // Number, name, type and description; no component code.
    const row = rows(page).nth(1);
    const toggle = page.getByTestId("blueprint-step-1-toggle");
    await expect(toggle).toContainText("2");
    await expect(toggle).toContainText("Data extraction");
    await expect(toggle).toContainText("Tekoäly");
    await expect(toggle).toContainText("Extract amounts, supplier, references");
    await expect(row).not.toContainText("docling");
    // The number sits on a full circle in the type's colour.
    const badge = toggle.locator("span[aria-hidden='true']").first();
    await expect(badge).toHaveCSS("border-left-width", "0px");
    await expect(badge).toHaveCSS("background-color", "rgb(138, 35, 135)");

    await toggle.click();
    await expect(page.getByTestId("blueprint-step-1-name")).toBeVisible();
    await expect(page.getByTestId("blueprint-step-1-description")).toBeVisible();
    await expect(page.getByTestId("blueprint-step-1-component")).toBeHidden();
    await expect(row).not.toContainText("SME");

    // Type is a choice of three, with the same words as the row.
    const saved = blueprintPatch(page);
    await page.getByTestId("blueprint-step-1-type").getByText("Ihmisen tarkistus").click();
    await saved;
    await expect(toggle).toContainText("Ihmisen tarkistus");
    await expect(badge).toHaveCSS("background-color", "rgb(180, 84, 26)");

    await page.getByTestId("blueprint-step-1-tech").click();
    await expect(page.getByTestId("blueprint-step-1-component")).toHaveValue("docling");
  });

  test("Muuta chatissa in an open step opens the chat with that step", async ({ page }) => {
    await openForm(page, "ses_laskut");
    await page.getByTestId("blueprint-step-3-toggle").click();
    await page.evaluate(() => {
      const w = window as unknown as { __refs: unknown[] };
      w.__refs = [];
      window.addEventListener("gaik-wizard:chat-reference", (e) => w.__refs.push((e as CustomEvent).detail));
    });

    await page.getByTestId("blueprint-step-3-ask").click();
    expect(await page.evaluate(() => (window as unknown as { __refs: unknown[] }).__refs)).toEqual([
      {
        key: "step:approve",
        label: "Vaihe 4 · Approval",
        prefix: 'Koskee prosessin vaihetta 4 (id approve), lainattuna: "Approval"',
      },
    ]);
    await expect(page.getByTestId("blueprint-step-3-ask")).toHaveText("Muuta chatissa");
    await expect(page.getByTestId("blueprint-step-3-ask")).toHaveAttribute(
      "title",
      "Pyydä wizardia muuttamaan vaihetta Approval",
    );

    // A step that is not saved yet has nothing to ask about.
    await page.getByTestId("blueprint-step-add").click();
    await expect(page.getByTestId("blueprint-step-5-ask")).toHaveCount(0);
  });

  test("a version that arrives while a save is on its way is still asked about, and Pidä omani keeps the draft", async ({
    page,
  }) => {
    const { release, patches, warning } = await conflictDuringSave(page);

    // The held save goes through: the question stays, and nothing more is saved by itself.
    release();
    await expect(status(page)).not.toHaveAttribute("data-state", "saving");
    await expect(warning).toBeVisible();
    await page.getByTestId("blueprint-field-description").fill("Still mine");
    await page.getByTestId("blueprint-field-name").focus();
    await expect(warning).toBeVisible();
    expect(patches.length).toBe(1);

    // "Pidä omani" saves the draft over the newer version, once.
    await warning.getByTestId("blueprint-keep-mine").click();
    await expect(warning).toHaveCount(0);
    await expect(status(page)).toHaveText("Tallennettu");
    expect(patches.length).toBe(2);
    expect(patches[1].goal).toBe("Shorter handling time");
    await page.reload();
    await expect(page.getByTestId("solution-plan-view")).toContainText("Shorter handling time");
  });

  test("saves again by itself after a refusal over a newer version with the same content", async ({ page }) => {
    // A version written since the form read the blueprint, with the same
    // content (a step forward writes one): the save made on the older version
    // is refused, the page reads the new one, and as nothing in the blueprint
    // changed there is nothing to choose between: the draft goes out again on
    // the version now shown, without a further edit.
    await openForm(page, "ses_ui_basics");
    await page.getByTestId("blueprint-json-toggle").click();
    const current = JSON.parse(await page.getByTestId("blueprint-json-editor").inputValue()) as unknown;
    await page.getByTestId("blueprint-json-toggle").click();
    const same = await page.request.patch("/api/sessions/ses_ui_basics/blueprint", {
      data: { content: current, note: "e2e: the same content, a new version" },
    });
    expect(same.status()).toBe(200);

    const statuses: number[] = [];
    page.on("response", (r) => {
      if (/\/api\/sessions\/[^/]+\/blueprint$/.test(r.url()) && r.request().method() === "PATCH") {
        statuses.push(r.status());
      }
    });
    await page.getByTestId("blueprint-field-goal").fill("Shorter handling time");
    await page.getByTestId("blueprint-field-name").focus();
    await expect.poll(() => statuses, { timeout: 15_000 }).toEqual([409, 200]);
    await expect(status(page)).toHaveText("Tallennettu");
    await expect(page.getByTestId("blueprint-changed-elsewhere")).toHaveCount(0);
    await page.reload();
    await expect(page.getByTestId("solution-plan-view")).toContainText("Shorter handling time");
  });

  test("a save made on an older version that reaches the server after a newer one is refused, and Ota uudempi keeps the newer one", async ({ page }) => {
    const { release, patches, warning } = await conflictDuringSave(page);
    // The held save started by itself on the version before the agent's: it
    // must not write over the version the agent saved meanwhile.
    const refused = page.waitForResponse(
      (r) => r.url().includes("/blueprint") && r.request().method() === "PATCH",
    );
    release();
    expect((await refused).status()).toBe(409);
    await expect(status(page)).not.toHaveAttribute("data-state", "saving");
    await expect(warning).toBeVisible();

    // The server still holds the agent's version, so taking it writes nothing.
    await warning.getByTestId("blueprint-take-newer").click();
    await expect(warning).toHaveCount(0);
    await expect(page.getByTestId("blueprint-field-goal")).toHaveValue("The wizard's goal");
    await expect(status(page)).toHaveText("Tallennettu");
    expect(patches.length).toBe(1);
    await page.reload();
    await expect(page.getByTestId("solution-plan-view")).toContainText("The wizard's goal");
  });

  test("asks which version stays when the blueprint changes under an unsaved draft", async ({ page }) => {
    test.setTimeout(150_000);
    await openForm(page, "ses_laskut");

    // An unsaved draft: a step without a name is not saved.
    await page.getByTestId("blueprint-step-0-toggle").click();
    await page.getByTestId("blueprint-step-0-name").fill("");
    await expect(status(page)).toHaveText("Ei tallennettu: anna vaiheelle nimi");

    // Meanwhile the simple flow beside it saves a rename of another step (the
    // BPMN canvas sends its edits to wizard_api, which the mock store has not).
    // The session waits on a gate, so the chat is open: collapsed, the tab has room.
    await setChatOpen(page, false);
    await selectWorkspaceTab(page, "Työnkulku");
    await expect(page.getByTestId("simple-flow")).toBeVisible({ timeout: 45_000 });
    const flowLocked = page.getByTestId("simple-flow-locked");
    if (await flowLocked.count()) await flowLocked.getByRole("button", { name: "Muokkaa kaaviota" }).click();
    await page.getByTestId("simple-flow-node-4").click();
    const flowName = page.getByTestId("simple-flow-name");
    await expect(flowName).toHaveValue("Export to finance system");
    const saved = page.waitForResponse((r) => /\/blueprint$/.test(r.url()) && r.request().method() === "PATCH");
    await flowName.fill("Send to finance");
    await flowName.press("Enter");
    expect((await saved).status()).toBe(200);
    await expect(page.getByTestId("simple-flow-status")).toHaveText("Tallennettu", { timeout: 15_000 });

    await page.getByRole("tab", { name: "Blueprint" }).click();
    const warning = page.getByTestId("blueprint-changed-elsewhere");
    await expect(warning).toContainText("Blueprint muuttui muualla");
    // The draft is still the user's.
    await expect(page.getByTestId("blueprint-step-0-name")).toHaveValue("");

    await warning.getByRole("button", { name: "Ota uudempi versio" }).click();
    await expect(warning).toHaveCount(0);
    await expect(rows(page).nth(0)).toHaveAttribute("aria-label", "1. Invoice intake");
    await expect(rows(page).nth(4)).toHaveAttribute("aria-label", "5. Send to finance");
    await expect(status(page)).toHaveText("Tallennettu");
  });

  test("the form is one page that the tab scrolls, with Valmis and the save status in view", async ({ page }) => {
    await page.setViewportSize({ width: 1100, height: 700 });
    await openForm(page, "ses_laskut");
    for (const n of [0, 1, 2]) await page.getByTestId(`blueprint-step-${n}-toggle`).click();

    // Nothing in the form scrolls by itself (a text area is a field, not a box of fields).
    const form = page.getByTestId("blueprint-form");
    const scrollers = await form.evaluate((root) =>
      [...root.querySelectorAll<HTMLElement>("*")]
        .filter((el) => el.tagName !== "TEXTAREA" && /auto|scroll/.test(getComputedStyle(el).overflowY))
        .map((el) => el.getAttribute("data-testid") ?? el.className),
    );
    expect(scrollers).toEqual([]);

    // The solution's fields and its steps are one page, longer than the tab: the tab scrolls it.
    const panel = page.getByRole("tabpanel", { name: "Blueprint" });
    const sizes = await panel.evaluate((el) => ({ page: el.scrollHeight, shown: el.clientHeight }));
    expect(sizes.page).toBeGreaterThan(sizes.shown);
    await panel.evaluate((el) => el.scrollTo(0, 0));
    await expect(page.getByTestId("blueprint-field-name")).toBeInViewport();
    await page.getByTestId("blueprint-json-toggle").scrollIntoViewIfNeeded();
    await expect(page.getByTestId("blueprint-field-name")).not.toBeInViewport();

    // The row with "Valmis" and the save status stays at the top of the tab.
    await expect(page.getByTestId("blueprint-done")).toBeInViewport({ ratio: 1 });
    await expect(status(page)).toBeInViewport({ ratio: 1 });
    const bar = await page.getByTestId("blueprint-mode-bar").filter({ visible: true }).boundingBox();
    const tab = await panel.boundingBox();
    expect(Math.abs(bar!.y - tab!.y)).toBeLessThan(1);
    // No sideways scroll either.
    expect(await panel.evaluate((el) => el.scrollWidth - el.clientWidth)).toBe(0);
  });

  test("Muokkaa heads the plan and Valmis the form, in the same place, with the save status beside it", async ({
    page,
  }) => {
    await loginAsDev(page);
    await page.goto("/sessions/ses_ui_basics");
    await selectWorkspaceTab(page, /Blueprint/);

    const edit = page.getByTestId("blueprint-edit");
    const done = page.getByTestId("blueprint-done");
    const bar = page.getByTestId("blueprint-mode-bar").filter({ visible: true });
    // Reading, the plan's first row ends in the control.
    await expect(bar).toHaveAttribute("data-mode", "read");
    await expect(bar.getByTestId("blueprint-edit")).toHaveCount(1);
    const reading = (await edit.boundingBox())!;

    await openBlueprintEditor(page);
    await expect(bar).toHaveAttribute("data-mode", "edit");
    await expect(bar).toHaveCount(1);
    // One control at a time: "Valmis" takes the place "Muokkaa" had.
    await expect(edit).toHaveCount(0);
    const editing = await done.boundingBox();
    expect(Math.abs(editing!.x + editing!.width - (reading.x + reading.width))).toBeLessThan(2);
    expect(Math.abs(editing!.y - reading.y)).toBeLessThan(2);
    // The status is in that row, next to the button.
    await expect(bar.getByTestId("blueprint-save-status")).toHaveText("Tallennettu");
    const saved = await status(page).boundingBox();
    expect(editing!.x - (saved!.x + saved!.width)).toBeLessThan(24);
    // The form has no heading of its own above the fields: the tab is the heading.
    await expect(page.getByTestId("blueprint-form").getByRole("heading")).toHaveText(["Prosessin vaiheet (2)"]);
  });

  test("an open step has its own actions: move it, add a step after it, remove it", async ({ page }) => {
    await openForm(page, "ses_laskut");
    const names = () => rows(page).evaluateAll((items) => items.map((li) => li.getAttribute("aria-label")));
    await page.getByTestId("blueprint-step-0-toggle").click();

    // The first step cannot go up; down moves it one place and the focus goes with it.
    await expect(page.getByTestId("blueprint-step-0-up")).toBeDisabled();
    const moved = blueprintPatch(page);
    await page.getByTestId("blueprint-step-0-down").click();
    expect((await names()).slice(0, 2)).toEqual(["1. Data extraction", "2. Invoice intake"]);
    await expect(page.getByTestId("blueprint-step-1-down")).toBeFocused();
    await expect(page.getByTestId("blueprint-step-1-name")).toHaveValue("Invoice intake");
    const order = (await moved).request().postDataJSON() as { content: { steps: { name: string }[] } };
    expect(order.content.steps.map((s) => s.name).slice(0, 2)).toEqual(["Data extraction", "Invoice intake"]);

    // Back up to the first place: "up" is then disabled, and the focus goes to its pair.
    await page.getByTestId("blueprint-step-1-up").click();
    await expect(page.getByTestId("blueprint-step-0-down")).toBeFocused();
    expect((await names())[0]).toBe("1. Invoice intake");

    // A step added from a step lands right after it, open, with the cursor in its name.
    await page.getByTestId("blueprint-step-0-add-after").click();
    await expect(rows(page)).toHaveCount(6);
    await expect(page.getByTestId("blueprint-step-1-name")).toBeFocused();
    const saved = blueprintPatch(page);
    await page.getByTestId("blueprint-step-1-name").fill("Duplicate check");
    const body = (await saved).request().postDataJSON() as { content: { steps: { name: string }[] } };
    expect(body.content.steps.map((s) => s.name).slice(0, 3)).toEqual([
      "Invoice intake",
      "Duplicate check",
      "Data extraction",
    ]);
    // "Lisää vaihe" under the list still adds the last step.
    await page.getByTestId("blueprint-step-add").click();
    await expect(page.getByTestId("blueprint-step-6-name")).toBeFocused();
  });

  test("a step dragged to the edge of the tab scrolls whatever scrolls the list, to a place off screen", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1100, height: 700 });
    await openForm(page, "ses_laskut");
    // Long enough that the last step is below the tab's bottom.
    for (const n of [1, 2, 3]) await page.getByTestId(`blueprint-step-${n}-toggle`).click();
    const panel = page.getByRole("tabpanel", { name: "Blueprint" });
    await panel.evaluate((el) => el.scrollTo(0, 0));
    // The first step in the middle of the tab, so the drag has a way to go to the edge.
    await page.getByTestId("blueprint-step-0-drag").evaluate((el) => el.scrollIntoView({ block: "center" }));
    await expect(rows(page).nth(4)).not.toBeInViewport();
    const before = await panel.evaluate((el) => el.scrollTop);

    // The scroller is not marked for the drag in any way: it is found by its computed overflow.
    await panel.evaluate((el) => el.classList.remove("overflow-y-auto"));
    await panel.evaluate((el) => (el.style.overflowY = "auto"));

    const handle = (await page.getByTestId("blueprint-step-0-drag").boundingBox())!;
    const tab = (await panel.boundingBox())!;
    const x = handle.x + handle.width / 2;
    await page.mouse.move(x, handle.y + handle.height / 2);
    await page.mouse.down();
    // Held just inside the tab's bottom edge: the list comes up under the pointer.
    await page.mouse.move(x, tab.y + tab.height - 12, { steps: 6 });
    await expect
      .poll(() => panel.evaluate((el) => Math.ceil(el.scrollTop + el.clientHeight) >= el.scrollHeight - 1), {
        timeout: 15_000,
      })
      .toBe(true);
    expect(await panel.evaluate((el) => el.scrollTop)).toBeGreaterThan(before);
    await page.mouse.up();

    // Dropped under the last step, which was off screen when the drag began.
    await expect(rows(page).nth(4)).toHaveAttribute("aria-label", "5. Invoice intake");
    await expect(rows(page).nth(0)).toHaveAttribute("aria-label", "1. Data extraction");
  });

  test("an empty blueprint shows one line and the way to add the first step", async ({ page }) => {
    await openForm(page, "ses_ui_basics");
    for (const n of [1, 0]) {
      await page.getByTestId(`blueprint-step-${n}-toggle`).click();
      await page.getByTestId(`blueprint-step-${n}-remove`).click();
    }
    await expect(rows(page)).toHaveCount(0);
    await expect(page.getByTestId("blueprint-steps-heading")).toHaveText("Prosessin vaiheet (0)");
    await expect(page.getByText("Ei vaiheita vielä. Lisää ensimmäinen vaihe.")).toBeVisible();
    await page.getByTestId("blueprint-step-add").click();
    await expect(page.getByTestId("blueprint-step-0-name")).toBeFocused();
  });

  test("technical settings keep the component and the key and value pairs, one under the other on a phone", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await openForm(page, "ses_laskut");
    await page.getByTestId("blueprint-step-1-toggle").click();
    const tech = page.getByTestId("blueprint-step-1-tech");
    await expect(tech).toHaveText("Tekniset asetukset");
    await tech.click();
    await expect(page.getByTestId("blueprint-step-1-component")).toHaveValue("docling");
    await page.getByTestId("blueprint-step-1-setting-add").click();

    const key = await page.getByTestId("blueprint-step-1-setting-0-key").boundingBox();
    const value = await page.getByTestId("blueprint-step-1-setting-0-value").boundingBox();
    expect(value!.y).toBeGreaterThan(key!.y + key!.height - 1);
    expect(value!.width).toBeGreaterThan(200);
    // The step's name and type stay readable on the row, and nothing is cut off sideways.
    await expect(page.getByTestId("blueprint-step-1-toggle")).toContainText("Data extraction");
    await expect(page.getByTestId("blueprint-step-1-toggle")).toContainText("Tekoäly");
    const panel = page.getByRole("tabpanel", { name: "Blueprint" });
    expect(await panel.evaluate((el) => el.scrollWidth - el.clientWidth)).toBe(0);
  });
});
