import { test, expect, type APIRequestContext, type Page } from "@playwright/test";
import { getWizardApiUrl, waitForApiHealthy } from "./helpers/api";
import { openEditor, sessionAtBpmn, writeDraft } from "./helpers/bpmn-stack";

const STACK_E2E = process.env.PLAYWRIGHT_STACK_E2E === "true";

/**
 * Rework and rejection paths on the BPMN canvas against the real stack (UI +
 * wizard_api + Postgres): a rework path added on the review step is drawn as
 * the approval's "No" looping back, and kept over a reload, in the canvas and
 * in the agent's draft; Edit turns it into a rejection (the process ends), and
 * Remove takes it away. e2e/bpmn-rework.spec.ts covers the dialog and what is
 * sent on the mock store.
 */

type Path = { id: string; name: string; attached_to: string; condition: string; outcome: string };

async function paths(request: APIRequestContext, id: string): Promise<Path[]> {
  const res = await request.get(`${getWizardApiUrl()}/test/sessions/${id}/draft`);
  expect(res.ok()).toBe(true);
  const draft = (await res.json()) as { business_process?: { exceptions?: Path[] } };
  return draft.business_process?.exceptions ?? [];
}

async function flows(page: Page, id: string): Promise<string[]> {
  const xml = await (await page.request.get(`/api/sessions/${id}/bpmn?data_objects=1`)).text();
  return [...xml.matchAll(/<bpmn:sequenceFlow [^>]*>/g)].map((m) => {
    const attr = (name: string) => new RegExp(`${name}="([^"]*)"`).exec(m[0])?.[1] ?? "";
    return [attr("sourceRef"), attr("targetRef"), attr("name")].join(" ");
  });
}

const operationAnswer = (page: Page) =>
  page.waitForResponse((r) => r.url().includes("/blueprint/operations") && r.request().method() === "POST");

/** Picks a shape by its own hit area: a flow drawn across it can cover its middle. */
async function pick(page: Page, elementId: string) {
  await page.getByTestId("bpmn-zoom-controls").getByRole("button", { name: "Sovita näkymään" }).click();
  const shape = page.locator(`.bpmn-editable .djs-shape[data-element-id="${elementId}"]`);
  await shape.locator(".djs-hit").first().dispatchEvent("click");
  await expect(shape).toHaveClass(/selected/);
}

const APPROVAL = "Gateway_approve_review";

test.describe("BPMN rework paths (stack)", () => {
  test.skip(!STACK_E2E, "set PLAYWRIGHT_STACK_E2E=true (docker-test.sh --step stack-e2e)");
  test.use({ viewport: { width: 1600, height: 1100 } });

  test.beforeAll(async ({ request }) => {
    await waitForApiHealthy(request);
  });

  test("a rework path on the review step is kept over a reload, then edited and removed", async ({ page, request }) => {
    test.setTimeout(240_000);
    const id = await sessionAtBpmn(page, request);
    await writeDraft(request, id);
    await page.reload();
    await openEditor(page);

    // On the review step: "Korjaus", back to the extraction.
    await page.getByTestId("flow-step-list").locator("li").nth(2).getByRole("button").first().click();
    await page.locator('.djs-context-pad .entry[data-action="gaik-add-rework"]').click();
    const dialog = page.getByTestId("bpmn-rework-dialog");
    await dialog.getByTestId("bpmn-rework-name").fill("Korjaus");
    await dialog.getByTestId("bpmn-rework-condition").fill("Virheitä");
    // Back to this step or an earlier one, or the end: never to the delivery after it.
    await expect(dialog.getByTestId("bpmn-rework-outcome").locator('option[value="loop_to:deliver"]')).toHaveCount(0);
    await dialog.getByTestId("bpmn-rework-outcome").selectOption("loop_to:extract");
    let answer = operationAnswer(page);
    await dialog.getByTestId("bpmn-rework-save").click();
    expect((await answer).status()).toBe(200);
    await expect(dialog).toHaveCount(0);
    await expect(page.locator(".bpmn-editable")).toHaveAttribute("aria-busy", "false");
    const added: Path = {
      id: "korjaus",
      name: "Korjaus",
      attached_to: "review",
      condition: "Virheitä",
      outcome: "loop_to:extract",
    };
    expect(await paths(request, id)).toEqual([added]);

    // After a reload: the approval's "No" loops back to the extraction, named by the condition.
    await page.reload();
    await openEditor(page);
    expect(await flows(page, id)).toContain(`${APPROVAL} Activity_extract Virheitä`);

    // Edit: prefilled; the path now ends the process.
    await pick(page, APPROVAL);
    await page.locator('.djs-context-pad .entry[data-action="gaik-rework-edit"]').click();
    await expect(dialog.getByTestId("bpmn-rework-name")).toHaveValue("Korjaus");
    await expect(dialog.getByTestId("bpmn-rework-outcome")).toHaveValue("loop_to:extract");
    await dialog.getByTestId("bpmn-rework-outcome").selectOption("end");
    answer = operationAnswer(page);
    await dialog.getByTestId("bpmn-rework-save").click();
    expect((await answer).status()).toBe(200);
    await expect(dialog).toHaveCount(0);
    await expect(page.locator(".bpmn-editable")).toHaveAttribute("aria-busy", "false");
    expect(await paths(request, id)).toEqual([{ ...added, outcome: "end" }]);
    const end = "EndEvent_korjaus";
    expect(await flows(page, id)).toContain(`${APPROVAL} ${end} Virheitä`);
    await expect(page.locator(`.bpmn-editable [data-element-id="${end}"]`)).toHaveCount(1);

    // Remove, from the path's end event: it goes, also after a reload.
    await pick(page, end);
    answer = operationAnswer(page);
    await page.locator('.djs-context-pad .entry[data-action="gaik-rework-remove"]').click();
    expect((await answer).status()).toBe(200);
    expect(await paths(request, id)).toEqual([]);
    await page.reload();
    await openEditor(page);
    await expect(page.locator(`.bpmn-editable [data-element-id="${end}"]`)).toHaveCount(0);
    expect(await flows(page, id)).toContain(`${APPROVAL} EndEvent_rejected_review No`);
  });
});
