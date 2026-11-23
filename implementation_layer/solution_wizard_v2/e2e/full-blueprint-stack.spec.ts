import { readFile } from "node:fs/promises";
import { test, expect, type APIRequestContext, type Page } from "@playwright/test";
import { getWizardApiUrl, waitForApiHealthy } from "./helpers/api";
import { draft, sessionAtBpmn } from "./helpers/bpmn-stack";
import { selectWorkspaceTab, setChatOpen } from "./helpers/workspace";

const STACK_E2E = process.env.PLAYWRIGHT_STACK_E2E === "true";

/**
 * The Blueprint tab's full blueprint against the real stack (UI + wizard_api
 * + Postgres): the draft is downloaded as JSON, a model's name is changed in
 * the advanced editor and saved, and after a reload the change is kept while
 * the BPMN diagram is the same. A save over a draft changed meanwhile is
 * refused with the user's text kept, and "Keep editing" saves it on the newer
 * draft. e2e/full-blueprint.spec.ts covers the views on the mock store.
 */

const MODEL = "gpt-4.1-mini";

/** `draft()` with a model for the extraction step, and a change log: a section only the wizard writes. */
function draftWithModel() {
  return {
    ...draft(),
    models: { extract: { provider: "azure", model: MODEL } },
    change_log: [{ version: "1", date: "2026-01-01", change: "e2e: the agent's draft", changed_by: "wizard" }],
  };
}

async function writeDraft(request: APIRequestContext, id: string, content: unknown) {
  const res = await request.post(`${getWizardApiUrl()}/test/sessions/${id}/draft`, { data: content });
  expect(res.status(), `write draft: ${await res.text()}`).toBe(204);
}

async function readDraft(request: APIRequestContext, id: string) {
  const res = await request.get(`${getWizardApiUrl()}/test/sessions/${id}/draft`);
  expect(res.ok()).toBe(true);
  return (await res.json()) as { models?: { extract?: { model?: string } }; use_case: { description: string } };
}

async function openFullBlueprint(page: Page) {
  await setChatOpen(page, false);
  await selectWorkspaceTab(page, /Blueprint/);
  await page.getByTestId("blueprint-view-full").click();
  await expect(page.getByTestId("full-blueprint-advanced")).toBeVisible({ timeout: 30_000 });
}

/**
 * The editor's line holding `text`, clicked when `click`: the tab is scrolled
 * (down, then from the top again) until CodeMirror draws it. A line drawn a
 * moment ago can be gone after the next scroll, so finding and clicking are
 * retried together.
 */
async function editorLine(page: Page, text: string, { click = false }: { click?: boolean } = {}) {
  const line = page.locator('[data-testid="full-blueprint-editor"] .cm-line', { hasText: text });
  const panel = page.getByRole("tabpanel", { name: "Blueprint" });
  await expect(async () => {
    if ((await line.count()) === 0) {
      await panel.evaluate((el) => {
        const atEnd = el.scrollTop + el.clientHeight >= el.scrollHeight - 1;
        if (atEnd) el.scrollTo(0, 0);
        else el.scrollBy(0, 300);
      });
    }
    expect(await line.count()).toBe(1);
    if (click) await line.click({ timeout: 2_000 });
  }).toPass({ timeout: 30_000 });
  return line;
}

/** Replaces the editor's line holding `from` (after its indentation) with `to`. */
async function replaceLine(page: Page, from: string, to: string) {
  await editorLine(page, from, { click: true });
  await page.keyboard.press("End");
  await page.keyboard.press("Shift+Home");
  await page.keyboard.type(to);
  await editorLine(page, to);
}

const fullSave = (page: Page) =>
  page.waitForResponse((r) => r.url().endsWith("/blueprint/full") && r.request().method() === "PUT");

test.describe("Full blueprint (stack)", () => {
  test.skip(!STACK_E2E, "set PLAYWRIGHT_STACK_E2E=true (docker-test.sh --step stack-e2e)");
  test.use({ viewport: { width: 1600, height: 1100 } });

  test.beforeAll(async ({ request }) => {
    await waitForApiHealthy(request);
  });

  test("download, change a model's name in the advanced editor, save: kept over a reload, the diagram the same", async ({
    page,
    request,
  }) => {
    test.setTimeout(180_000);
    const id = await sessionAtBpmn(page, request);
    await writeDraft(request, id, draftWithModel());
    await page.reload();
    await openFullBlueprint(page);

    // The sections, folded, in plain words.
    const models = page.getByTestId("full-blueprint-section-models");
    await expect(models.locator("summary")).toContainText("Mallit");
    await models.locator("summary").click();
    await expect(models.locator("pre")).toContainText(MODEL);

    // The download is the draft, named after the use case.
    const downloading = page.waitForEvent("download");
    await page.getByTestId("full-blueprint-download").click();
    const file = await downloading;
    expect(file.suggestedFilename()).toBe("invoices.blueprint.json");
    const downloaded = JSON.parse(await readFile((await file.path())!, "utf-8")) as ReturnType<typeof draftWithModel>;
    expect(downloaded.models.extract.model).toBe(MODEL);
    expect(downloaded.use_case.id).toBe("invoices");
    // Marked as AI output, as the case exports are (lib/ai-marking).
    expect(downloaded).toMatchObject({ ai_generated: true, ai_generator: "GAIK Solution Wizard" });

    const bpmnBefore = await (await page.request.get(`/api/sessions/${id}/bpmn`)).text();
    expect(bpmnBefore).toContain("Activity_extract");

    await page.getByTestId("full-blueprint-advanced").click();
    await expect(page.getByTestId("code-editor")).toBeVisible();

    // A read-only section is shaded and cannot be typed into.
    const changeLog = await editorLine(page, '"change_log": [', { click: true });
    await expect(changeLog.locator('[data-locked="true"]').first()).toBeVisible();
    await page.keyboard.type("ZZQ");
    await expect(page.locator('[data-testid="full-blueprint-editor"] .cm-line', { hasText: "ZZQ" })).toHaveCount(0);

    await replaceLine(page, `"model": "${MODEL}"`, '"model": "gpt-5-mini"');
    const saved = fullSave(page);
    await page.getByTestId("full-blueprint-save").click();
    const answer = await saved;
    expect(answer.status()).toBe(200);
    expect(((await answer.json()) as { bpmn_changed: boolean }).bpmn_changed).toBe(false);
    await expect(page.getByTestId("full-blueprint-status")).toHaveAttribute("data-state", "saved");
    await expect(page.getByTestId("full-blueprint-view")).toHaveAttribute("data-mode", "read");

    // A second save without a reload is made on the version the first wrote.
    await page.getByTestId("full-blueprint-advanced").click();
    await replaceLine(page, '"model": "gpt-5-mini"', '"model": "gpt-5"');
    const again = fullSave(page);
    await page.getByTestId("full-blueprint-save").click();
    expect((await again).status()).toBe(200);
    await expect(page.getByTestId("full-blueprint-status")).toHaveAttribute("data-state", "saved");

    await page.reload();
    await openFullBlueprint(page);
    await page.getByTestId("full-blueprint-section-models").locator("summary").click();
    await expect(page.getByTestId("full-blueprint-section-models").locator("pre")).toContainText('"gpt-5"');
    expect((await readDraft(request, id)).models?.extract?.model).toBe("gpt-5");
    // The change log is the server's own: the saves left the seeded entry in it.
    expect(JSON.stringify((await readDraft(request, id)) as unknown)).toContain("e2e: the agent's draft");
    expect(await (await page.request.get(`/api/sessions/${id}/bpmn`)).text()).toBe(bpmnBefore);
  });

  test("a save over a draft changed meanwhile is refused and keeps the text; Keep editing merges it into the newer draft", async ({
    page,
    request,
  }) => {
    test.setTimeout(180_000);
    const id = await sessionAtBpmn(page, request);
    await writeDraft(request, id, draftWithModel());
    await page.reload();
    await openFullBlueprint(page);
    await page.getByTestId("full-blueprint-advanced").click();
    await replaceLine(page, `"model": "${MODEL}"`, '"model": "gpt-5-mini"');

    // The agent writes its draft again meanwhile.
    const newer = draftWithModel();
    newer.use_case.description = "Invoice handling, written by the agent";
    await writeDraft(request, id, newer);

    const refused = fullSave(page);
    await page.getByTestId("full-blueprint-save").click();
    expect((await refused).status()).toBe(409);
    const status = page.getByTestId("full-blueprint-status");
    await expect(status).toHaveAttribute("data-state", "changed");
    await expect(status).toContainText("muuttui muualla");
    await expect(page.getByTestId("full-blueprint-reload")).toBeVisible();
    await editorLine(page, '"model": "gpt-5-mini"');
    expect((await readDraft(request, id)).models?.extract?.model).toBe(MODEL);

    await page.getByTestId("full-blueprint-keep-editing").click();
    await expect(status).toHaveAttribute("data-state", "kept");
    const saved = fullSave(page);
    await page.getByTestId("full-blueprint-save").click();
    expect((await saved).status()).toBe(200);
    await expect(status).toHaveAttribute("data-state", "saved");
    const merged = await readDraft(request, id);
    expect(merged.models?.extract?.model).toBe("gpt-5-mini");
    // What the agent changed meanwhile, in a section the text did not change, is kept.
    expect(merged.use_case.description).toBe("Invoice handling, written by the agent");
  });

  test("a section both the text and a newer draft changed is refused by name; only the newer version is offered", async ({
    page,
    request,
  }) => {
    test.setTimeout(180_000);
    const id = await sessionAtBpmn(page, request);
    await writeDraft(request, id, draftWithModel());
    await page.reload();
    await openFullBlueprint(page);
    await page.getByTestId("full-blueprint-advanced").click();
    await replaceLine(page, `"model": "${MODEL}"`, '"model": "gpt-5-mini"');

    // Leaving the view with the text not saved asks first; going back keeps the text.
    await page.getByTestId("blueprint-view-steps").click();
    await expect(page.getByTestId("blueprint-view-leave")).toContainText("tallentamattomia muutoksia");
    await page.getByTestId("blueprint-view-leave-stay").click();
    await expect(page.getByTestId("blueprint-view-leave")).toHaveCount(0);
    await editorLine(page, '"model": "gpt-5-mini"');

    // The agent changes the same model meanwhile.
    const newer = draftWithModel();
    newer.models.extract.model = "gpt-4.1";
    await writeDraft(request, id, newer);

    const refused = fullSave(page);
    await page.getByTestId("full-blueprint-save").click();
    expect((await refused).status()).toBe(409);
    await page.getByTestId("full-blueprint-keep-editing").click();
    const status = page.getByTestId("full-blueprint-status");
    await expect(status).toHaveAttribute("data-state", "kept");

    // Nothing is sent: the conflict is found before.
    let puts = 0;
    page.on("request", (r) => {
      if (r.url().endsWith("/blueprint/full") && r.method() === "PUT") puts += 1;
    });
    await page.getByTestId("full-blueprint-save").click();
    await expect(status).toHaveAttribute("data-state", "conflict");
    await expect(status).toContainText("Mallit");
    await expect(page.getByTestId("full-blueprint-save")).toBeDisabled();
    await expect(page.getByTestId("full-blueprint-keep-editing")).toHaveCount(0);
    expect(puts).toBe(0);
    expect((await readDraft(request, id)).models?.extract?.model).toBe("gpt-4.1");

    // Loading the newer version shows the agent's model; the text is gone, so leaving asks nothing.
    await page.getByTestId("full-blueprint-reload").click();
    await expect(page.getByTestId("full-blueprint-view")).toHaveAttribute("data-mode", "read");
    const models = page.getByTestId("full-blueprint-section-models");
    await models.locator("summary").click();
    await expect(models.locator("pre")).toContainText('"gpt-4.1"');
    await page.getByTestId("blueprint-view-steps").click();
    await expect(page.getByTestId("blueprint-view-leave")).toHaveCount(0);
    await expect(page.getByTestId("blueprint-view-steps")).toHaveAttribute("aria-pressed", "true");
  });

  test("leaving the full blueprint with text not saved, and discarding it, drops the text", async ({ page, request }) => {
    test.setTimeout(180_000);
    const id = await sessionAtBpmn(page, request);
    await writeDraft(request, id, draftWithModel());
    await page.reload();
    await openFullBlueprint(page);
    await page.getByTestId("full-blueprint-advanced").click();
    await replaceLine(page, `"model": "${MODEL}"`, '"model": "gpt-5-mini"');
    await page.getByTestId("blueprint-view-steps").click();
    await page.getByTestId("blueprint-view-leave-discard").click();
    await expect(page.getByTestId("blueprint-view-steps")).toHaveAttribute("aria-pressed", "true");
    await expect(page.getByTestId("full-blueprint-view")).toHaveCount(0);
    await page.getByTestId("blueprint-view-full").click();
    await expect(page.getByTestId("full-blueprint-view")).toHaveAttribute("data-mode", "read");
    expect((await readDraft(request, id)).models?.extract?.model).toBe(MODEL);
  });
});
