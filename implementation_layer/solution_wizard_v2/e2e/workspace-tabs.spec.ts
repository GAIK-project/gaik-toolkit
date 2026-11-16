import { test, expect, type Page } from "@playwright/test";
import { loginAsDev } from "./helpers/auth";
import { resetMockSessions } from "./helpers/mock";
import { setMockSessionStep } from "./helpers/dev-step";
import { readSessionAgain } from "./helpers/session";
import { selectWorkspaceTab, setChatOpen } from "./helpers/workspace";

/**
 * The workspace has three tabs in the wizard's order: Blueprint, Työnkulku and
 * PoC. Blueprint opens as a read view (the former Suunnitelma tab) with the
 * form behind "Muokkaa"; Työnkulku is there only once the diagram exists; the
 * PoC is locked until Gate 2 is approved; and a session opens on the tab of
 * its phase. Mock store: ses_ui_basics and ses_chatbot stand at step 6,
 * ses_gate2_pending at step 9 and ses_laskut at step 11; of these only
 * ses_chatbot and ses_laskut get a diagram (lib/bpmn-spike.ts).
 */

const selected = (page: Page) => page.getByRole("tab", { selected: true });

test.describe("Workspace tabs", () => {
  test.beforeEach(async ({ request }) => {
    await resetMockSessions(request);
  });

  test("before the diagram exists there are two tabs, and no hint line under them", async ({ page }) => {
    await loginAsDev(page);
    await page.goto("/sessions/ses_ui_basics");

    await expect(page.getByRole("tab")).toHaveText([/Blueprint/, /PoC/]);
    await expect(selected(page)).toHaveText(/Blueprint/);
    await expect(page.getByRole("tab", { name: "Suunnitelma" })).toHaveCount(0);
    await expect(page.getByText("Ratkaisun rakenne muokattavana lomakkeena")).toHaveCount(0);
  });

  test("a session opens on the tab of its phase, and the now mark shows only when another tab is open", async ({
    page,
    request,
    baseURL,
  }) => {
    await loginAsDev(page);

    // Step 6: the blueprint. The open tab is the phase's, so nothing marks it.
    await page.goto("/sessions/ses_ui_basics");
    await expect(selected(page)).toHaveText(/Blueprint/);
    await expect(page.getByTestId("tab-now")).toHaveCount(0);
    await expect(selected(page)).toHaveAccessibleName("Blueprint");

    // Step 8: the diagram exists, and it is what the phase is about.
    await setMockSessionStep(request, baseURL as string, "ses_chatbot", 8);
    await page.goto("/sessions/ses_chatbot");
    await expect(page.getByRole("tab")).toHaveText([/Blueprint/, /Työnkulku/, /PoC/]);
    await expect(selected(page)).toHaveText(/Työnkulku/);
    await expect(page.getByTestId("tab-now")).toHaveCount(0);
    // On another tab, the mark says where the phase is.
    await selectWorkspaceTab(page, "Blueprint");
    await expect(page.getByRole("tab", { name: "Työnkulku" }).getByTestId("tab-now")).toHaveCount(1);
    await expect(page.getByRole("tab", { name: "Työnkulku" })).toHaveAccessibleName(/Nyt/);
    await expect(page.getByTestId("tab-now")).toHaveCount(1);

    // Step 11 (Gate 3): the test run, not the diagram.
    await page.goto("/sessions/ses_laskut");
    await expect(selected(page)).toHaveText(/PoC/);
    await expect(page.getByTestId("tab-now")).toHaveCount(0);
  });

  test("the row of tabs has the tabs and the AI notice, and no line that repeats the open tab's name", async ({
    page,
  }) => {
    await loginAsDev(page);
    await page.goto("/sessions/ses_laskut");
    await expect(page.getByTestId("tab-hint")).toHaveCount(0);
    for (const hint of ["Testaa ratkaisu esimerkkiaineistolla", "Ratkaisun vaiheet ja niiden asetukset"]) {
      await expect(page.getByText(hint, { exact: true })).toHaveCount(0);
    }
    // What a tab shows is still its tooltip.
    await expect(page.getByRole("tab", { name: "Blueprint" })).toHaveAttribute(
      "title",
      "Ratkaisun vaiheet ja niiden asetukset",
    );
    await expect(page.getByTestId("workspace-ai-mark")).toBeVisible();
  });

  test("a ?tab= in the address wins over the phase", async ({ page }) => {
    await loginAsDev(page);
    await page.goto("/sessions/ses_laskut?tab=blueprint");

    await expect(selected(page)).toHaveText(/Blueprint/);
    // The phase's own tab still carries the mark, and it is another tab.
    await expect(page.getByTestId("tab-now")).toHaveCount(1);
    await expect(page.getByRole("tab", { name: "Blueprint" }).getByTestId("tab-now")).toHaveCount(0);
  });

  test("a ?tab=poc in the address of a session whose PoC is locked opens Blueprint", async ({ page }) => {
    await loginAsDev(page);
    await page.goto("/sessions/ses_gate2_pending?tab=poc");

    // This session has no diagram, so its tabs are Blueprint and the locked PoC.
    await expect(page.getByRole("tab")).toHaveText([/Blueprint/, /PoC/]);
    await expect(selected(page)).toHaveText(/Blueprint/);
    await expect(page.getByRole("tab", { name: "PoC" })).toHaveAttribute("aria-disabled", "true");
    await expect(page.getByTestId("solution-plan-view")).toBeVisible();
  });

  test("reaching the diagram step adds Työnkulku and moves to it", async ({ page, request, baseURL }) => {
    await loginAsDev(page);
    await page.goto("/sessions/ses_chatbot");
    // Before the diagram the only tab to be on is Blueprint: the PoC is locked.
    await expect(selected(page)).toHaveText(/Blueprint/);

    // The step moves while the page is open, as it does when the wizard
    // writes its files during a chat turn.
    await setMockSessionStep(request, baseURL as string, "ses_chatbot", 7);
    await readSessionAgain(page);
    await expect(page.getByRole("heading", { name: "Blueprint-kokoaminen" })).toBeVisible();
    await expect(selected(page)).toHaveText(/Blueprint/);

    await setMockSessionStep(request, baseURL as string, "ses_chatbot", 8);
    await readSessionAgain(page);
    await expect(page.getByRole("tab")).toHaveText([/Blueprint/, /Työnkulku/, /PoC/]);
    await expect(selected(page)).toHaveText(/Työnkulku/);
  });

  test("Blueprint opens as a read view: a card per step, details behind a disclosure", async ({ page }) => {
    await loginAsDev(page);
    await page.goto("/sessions/ses_chatbot");

    const plan = page.getByTestId("solution-plan-view");
    await expect(plan).toBeVisible();
    await expect(plan.getByTestId(/^plan-step-\d+$/)).toHaveCount(5);
    await expect(plan).not.toContainText("SME-5");
    await expect(plan).not.toContainText("Ei asetuksia");

    // A step with a component and settings keeps them folded away.
    const rag = page.getByTestId("plan-step-1");
    await expect(rag.getByRole("heading", { name: "Retrieval (RAG)" })).toBeVisible();
    await expect(rag).toContainText("Tekoäly");
    // The type reads as in the form and the Workflow list: the number on the type's colour.
    await expect(rag.locator("span[aria-hidden='true']").first()).toHaveCSS("background-color", "rgb(138, 35, 135)");
    await expect(rag).toContainText("Fetch relevant help articles");
    await expect(rag.getByText("pgvector")).toBeHidden();
    await rag.getByText("Komponentti ja asetukset").click();
    await expect(rag.getByText("pgvector")).toBeVisible();
    await expect(rag.getByText("top_k")).toBeVisible();

    // A step with neither has no disclosure at all.
    await expect(page.getByTestId("plan-step-0").locator("details")).toHaveCount(0);
  });

  test("Blueprint lists the output fields the wizard agreed behind Tulosskeema, read-only until Muokkaa kenttiä", async ({ page }) => {
    await loginAsDev(page);
    await page.goto("/sessions/ses_laskut?tab=json");

    const schema = page.getByTestId("plan-schema");
    const toggle = page.getByTestId("plan-schema-toggle");
    await expect(toggle).toHaveText("Tulosskeema6 kenttää");
    await expect(toggle).toHaveAttribute("aria-expanded", "false");
    const fields = page.getByTestId("plan-schema-fields").getByRole("listitem");
    await expect(fields.first()).toBeHidden();
    await toggle.click();

    // Name, type and the required mark; a description and the allowed values where there are any.
    await expect(fields).toHaveCount(6);
    await expect(fields.nth(0)).toHaveText("supplier_nameTekstiPakollinenThe supplier as written on the invoice.");
    await expect(fields.nth(2)).toHaveText("invoice_datePäivämääräPakollinen");
    await expect(fields.nth(4)).toHaveText("cost_centerValintaArvot: Sales, Production, Administration");
    await expect(schema.getByRole("textbox")).toHaveCount(0);

    // "Muokkaa kenttiä" turns the rows into a form: a name, a type and the
    // required mark for each field. Nothing is sent while nothing has changed,
    // and "Peruuta" brings the rows back as they were.
    const edit = schema.getByRole("button", { name: "Muokkaa kenttiä" });
    await edit.click();
    const form = page.getByTestId("plan-schema-form");
    await expect(form.getByRole("textbox", { name: "Nimi 1", exact: true })).toBeFocused();
    await expect(form.getByRole("textbox", { name: /^Nimi \d+$/ })).toHaveCount(6);
    await expect(form.getByRole("combobox")).toHaveCount(6);
    await expect(form.getByRole("checkbox")).toHaveCount(6);
    await expect(form.getByRole("button", { name: "Lähetä wizardille" })).toBeDisabled();
    await form.getByRole("textbox", { name: "Nimi 1", exact: true }).fill("supplier");
    await expect(form.getByRole("button", { name: "Lähetä wizardille" })).toBeEnabled();
    await form.getByRole("button", { name: "Peruuta" }).click();
    await expect(form).toHaveCount(0);
    await expect(edit).toBeFocused();
    await expect(fields.nth(0)).toContainText("supplier_name");

    // A session with no agreed fields has no entry.
    await page.goto("/sessions/ses_ui_basics");
    await expect(page.getByTestId("solution-plan-view")).toBeVisible();
    await expect(page.getByTestId("plan-schema")).toHaveCount(0);
  });

  test("Muokkaa opens the form and Valmis returns to the read view", async ({ page }) => {
    await loginAsDev(page);
    await page.goto("/sessions/ses_chatbot");

    const plan = page.getByTestId("solution-plan-view");
    const edit = page.getByTestId("blueprint-edit");
    const done = page.getByTestId("blueprint-done");
    await expect(plan).toBeVisible();
    await expect(page.getByTestId("blueprint-step-add")).toHaveCount(0);
    // Before Gate 2 an edit costs nothing yet, so the plan has no note above it.
    await expect(page.getByTestId("blueprint-edit-note")).toHaveCount(0);
    // The control heads the plan, at the end of its first row, next to what it
    // changes: not at the end of the tab row, which a wide window put far away.
    await expect(edit).toHaveText("Muokkaa blueprintia");
    const bar = plan.getByTestId("blueprint-mode-bar");
    await expect(bar).toHaveAttribute("data-mode", "read");
    await expect(bar.getByTestId("blueprint-edit")).toHaveCount(1);
    const planBox = (await plan.boundingBox())!;
    const editBox = (await edit.boundingBox())!;
    expect(Math.abs(editBox.x + editBox.width - (planBox.x + planBox.width))).toBeLessThan(12);
    expect(editBox.y).toBeLessThan((await page.getByTestId("plan-goal").boundingBox())!.y);
    await expect(page.getByRole("tablist").first().getByTestId("blueprint-edit")).toHaveCount(0);

    await expect(async () => {
      if (!(await done.isVisible())) await edit.click({ timeout: 1_000 });
      await expect(done).toBeVisible({ timeout: 1_000 });
    }).toPass({ timeout: 15_000 });
    await expect(page.getByTestId("blueprint-step-add")).toBeVisible();
    await expect(plan).toBeHidden();
    await expect(done).toBeFocused();

    await done.click();
    await expect(plan).toBeVisible();
    await expect(page.getByTestId("blueprint-step-add")).toBeHidden();
    await expect(edit).toBeFocused();
  });

  test("after Gate 2 Blueprint says what an edit costs beside its edit control, which stays an edit", async ({
    page,
  }) => {
    await loginAsDev(page);
    await page.goto("/sessions/ses_laskut");
    await selectWorkspaceTab(page, "Blueprint");

    // Not "read-only": the blueprint can still be edited here, and the row says what that means.
    const words = "Testattava paketti tehdään tästä blueprintista: muutos vaatii uuden paketin ja testiajon.";
    const note = page.getByTestId("blueprint-edit-note");
    await expect(note).toHaveText(words);
    await expect(page.getByTestId("blueprint-edit")).toHaveAccessibleDescription(words);
    await expect(page.getByTestId("blueprint-edit")).toHaveText("Muokkaa blueprintia");
    // The note and the control share the plan's first row.
    const bar = page.getByTestId("blueprint-mode-bar");
    await expect(bar.getByTestId("blueprint-edit-note")).toHaveCount(1);
    await expect(bar.getByTestId("blueprint-edit")).toHaveCount(1);

    // The Workflow tab's flow is read-only until "Muokkaa" there, and says so.
    await setChatOpen(page, false);
    await selectWorkspaceTab(page, "Työnkulku");
    const locked = page.getByTestId("simple-flow-locked");
    await expect(locked).toContainText(
      "Vain luku: muutos vaatii uuden paketin ja testiajon. Valitse vaihe ja pyydä muutosta wizardilta.",
    );
    await expect(locked.getByRole("button")).toHaveText("Muokkaa");
  });

  test("a step card's chat button opens the chat with a reference to that step", async ({ page }) => {
    await loginAsDev(page);
    await page.goto("/sessions/ses_chatbot");
    await expect(page.getByTestId("solution-plan-view")).toBeVisible();

    // The chat side is built on another branch: here only the event is checked.
    await page.evaluate(() => {
      const w = window as unknown as { __refs: unknown[] };
      w.__refs = [];
      window.addEventListener("gaik-wizard:chat-reference", (e) => w.__refs.push((e as CustomEvent).detail));
    });
    const ask = page.getByRole("button", { name: "Muuta chatissa: Vaihe 2 · Retrieval (RAG)" });
    await expect(async () => {
      await ask.click();
      expect(await page.evaluate(() => (window as unknown as { __refs: unknown[] }).__refs.length)).toBeGreaterThan(0);
    }).toPass({ timeout: 15_000 });

    const refs = await page.evaluate(() => (window as unknown as { __refs: unknown[] }).__refs);
    expect(refs[0]).toEqual({
      key: "step:retrieve",
      label: "Vaihe 2 · Retrieval (RAG)",
      prefix: 'Koskee prosessin vaihetta 2 (id retrieve), lainattuna: "Retrieval (RAG)"',
    });
  });

  test("the PoC is locked before Gate 2: a disabled tab that says why, no generate button, no package request", async ({
    page,
  }) => {
    const pocRequests: string[] = [];
    page.on("request", (r) => {
      if (r.url().includes("/poc/")) pocRequests.push(r.url());
    });
    await loginAsDev(page);
    await page.goto("/sessions/ses_ui_basics");
    await expect(page.getByTestId("solution-plan-view")).toBeVisible();

    const poc = page.getByRole("tab", { name: "PoC" });
    const reason = "Avautuu, kun Gate 2 on hyväksytty";
    await expect(poc).toHaveAttribute("aria-disabled", "true");
    await expect(poc).toHaveAttribute("title", reason);
    await expect(poc).toHaveAccessibleDescription(reason);
    // A press on it opens nothing: the tab that was open stays, and no locked page is drawn.
    await poc.click({ force: true });
    await expect(poc).toHaveAttribute("aria-selected", "false");
    await expect(selected(page)).toHaveText(/Blueprint/);
    await expect(page.getByRole("tabpanel", { name: "PoC" })).toHaveCount(0);
    await expect(page.getByText("Testaus avautuu")).toHaveCount(0);
    await expect(page.getByRole("button", { name: /Generoi/ })).toHaveCount(0);
    await expect(page.getByTestId("poc-run-sandbox")).toHaveCount(0);
    expect(pocRequests).toEqual([]);
  });

  test("a tab is selected from the keyboard, and only its panel is exposed", async ({ page }) => {
    await loginAsDev(page);
    await page.goto("/sessions/ses_laskut");
    const blueprint = page.getByRole("tab", { name: "Blueprint" });

    await expect(async () => {
      await blueprint.focus();
      await page.keyboard.press("Enter");
      await expect(blueprint).toHaveAttribute("aria-selected", "true", { timeout: 1_000 });
    }).toPass({ timeout: 15_000 });
    await expect(page.getByRole("tabpanel")).toHaveCount(1);
    await expect(page.getByRole("tabpanel")).toHaveAccessibleName(/Blueprint/);
  });
});

test.describe("Workspace tabs on a phone", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test.beforeEach(async ({ request }) => {
    await resetMockSessions(request);
  });

  test("the three tabs fit, and the selected one is on screen", async ({ page }) => {
    await loginAsDev(page);
    await page.goto("/sessions/ses_laskut");
    await expect(selected(page)).toHaveText(/PoC/);

    const box = (await selected(page).boundingBox())!;
    expect(box.x).toBeGreaterThanOrEqual(0);
    expect(box.x + box.width).toBeLessThanOrEqual(390);
    const list = await page.getByRole("tablist").evaluate((el) => ({ sw: el.scrollWidth, cw: el.clientWidth }));
    expect(list.sw).toBeLessThanOrEqual(list.cw);
    const doc = await page.evaluate(() => ({
      sw: document.documentElement.scrollWidth,
      cw: document.documentElement.clientWidth,
    }));
    expect(doc.sw).toBeLessThanOrEqual(doc.cw);
  });
});
