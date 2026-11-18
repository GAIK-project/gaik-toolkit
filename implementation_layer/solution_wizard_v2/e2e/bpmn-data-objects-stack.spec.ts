import { test, expect, type APIRequestContext, type Page } from "@playwright/test";
import { getWizardApiUrl, waitForApiHealthy } from "./helpers/api";
import { openEditor, sessionAtBpmn, writeDraft } from "./helpers/bpmn-stack";

const STACK_E2E = process.env.PLAYWRIGHT_STACK_E2E === "true";

/**
 * Data objects on the BPMN canvas against the real stack (UI + wizard_api +
 * Postgres): a data object renamed in place keeps its name over a reload, in
 * the canvas and as the artifact's label in the agent's draft; a line from it
 * to another step makes it that step's input, and deleting that association
 * takes the input away again. e2e/bpmn-data-objects.spec.ts covers what is
 * sent, the refusals and the read-only canvas on the mock store.
 */

type Draft = {
  artifacts: Record<string, { label?: string }>;
  workflow: { steps: { id: string; inputs: string[]; outputs: string[] }[] };
};

async function readDraft(request: APIRequestContext, id: string): Promise<Draft> {
  const res = await request.get(`${getWizardApiUrl()}/test/sessions/${id}/draft`);
  expect(res.ok()).toBe(true);
  return (await res.json()) as Draft;
}

const inputsOf = async (request: APIRequestContext, id: string, step: string) =>
  (await readDraft(request, id)).workflow.steps.find((s) => s.id === step)?.inputs ?? [];

/** The id of the data association between `data` and `task` the server draws, or null. */
async function association(
  page: Page,
  id: string,
  data: string,
  task: string,
  role: "input" | "output" = "input",
): Promise<string | null> {
  const xml = await (await page.request.get(`/api/sessions/${id}/bpmn?data_objects=1`)).text();
  return page.evaluate(
    ({ text, data, task, role }) => {
      const doc = new DOMParser().parseFromString(text, "application/xml");
      const kind = role === "input" ? "dataInputAssociation" : "dataOutputAssociation";
      for (const e of doc.getElementsByTagName("*")) {
        if (e.localName !== kind || e.parentElement?.getAttribute("id") !== task) continue;
        const ref = [...e.children].find((c) => c.localName === (role === "input" ? "sourceRef" : "targetRef"));
        if (ref?.textContent?.trim() === data) return e.getAttribute("id");
      }
      return null;
    },
    { text: xml, data, task, role },
  );
}

const operationAnswer = (page: Page) =>
  page.waitForResponse((r) => r.url().includes("/blueprint/operations") && r.request().method() === "POST");

const element = (page: Page, id: string) => page.locator(`.bpmn-editable .djs-element[data-element-id="${id}"]`);

/** Picks an element by its own hit area: a flow drawn across it can cover its middle. */
async function pick(page: Page, id: string) {
  await page.getByTestId("bpmn-zoom-controls").getByRole("button", { name: "Sovita näkymään" }).click();
  await element(page, id).locator(".djs-hit").first().dispatchEvent("click");
  await expect(element(page, id)).toHaveClass(/selected/);
}

const FIELDS = "DataObjectRef_fields";

test.describe("BPMN data objects (stack)", () => {
  test.skip(!STACK_E2E, "set PLAYWRIGHT_STACK_E2E=true (docker-test.sh --step stack-e2e)");
  test.use({ viewport: { width: 1600, height: 1100 } });

  test.beforeAll(async ({ request }) => {
    await waitForApiHealthy(request);
  });

  test("a data object renamed and linked to another step is kept over a reload, then unlinked", async ({
    page,
    request,
  }) => {
    test.setTimeout(240_000);
    const id = await sessionAtBpmn(page, request);
    await writeDraft(request, id);
    await page.reload();
    await openEditor(page);

    // Rename the extracted fields in place.
    await pick(page, FIELDS);
    await page.locator('.djs-context-pad .entry[data-action="gaik-data-rename"]').click();
    await expect(page.locator(".djs-direct-editing-parent")).toBeVisible();
    await page.keyboard.press("ControlOrMeta+a");
    await page.keyboard.type("Laskun kentät");
    const renamed = operationAnswer(page);
    await pick(page, "Activity_upload");
    expect((await renamed).status()).toBe(200);
    await expect(page.getByTestId("bpmn-status")).toContainText("Tallennettu", { timeout: 20_000 });

    // Link it to the deliver step: a line from the data object to the step, an input.
    await pick(page, FIELDS);
    const linked = operationAnswer(page);
    await page.locator('.djs-context-pad .entry[data-action="connect"]').click();
    await element(page, "Activity_deliver").hover();
    await element(page, "Activity_deliver").click();
    expect((await linked).status()).toBe(200);
    await expect(page.getByTestId("bpmn-status")).toContainText("Tallennettu", { timeout: 20_000 });

    await page.reload();
    await openEditor(page);
    await expect(element(page, `${FIELDS}_label`)).toContainText("Laskun kentät");
    expect((await readDraft(request, id)).artifacts.fields.label).toBe("Laskun kentät");
    expect(await inputsOf(request, id, "deliver")).toContain("fields");
    const input = await association(page, id, FIELDS, "Activity_deliver");
    expect(input).not.toBeNull();

    // Delete the association: deliver no longer uses the fields.
    await pick(page, input!);
    const unlinked = operationAnswer(page);
    await page.locator('.djs-context-pad .entry[data-action="delete"]').click();
    expect((await unlinked).status()).toBe(200);
    await expect(page.getByTestId("bpmn-status")).toContainText("Tallennettu", { timeout: 20_000 });
    await page.reload();
    await openEditor(page);
    expect(await inputsOf(request, id, "deliver")).not.toContain("fields");
    expect(await association(page, id, FIELDS, "Activity_deliver")).toBeNull();
    await expect(element(page, `${FIELDS}_label`)).toContainText("Laskun kentät");

    // The report's only producer: the line from deliver stays, and so does the report.
    const output = await association(page, id, "DataObjectRef_report", "Activity_deliver", "output");
    expect(output).not.toBeNull();
    await pick(page, output!);
    const refused = operationAnswer(page);
    await page.locator('.djs-context-pad .entry[data-action="delete"]').click();
    expect((await refused).status()).toBe(422);
    await expect(page.getByTestId("bpmn-status")).toContainText("joten yhteys pysyy", { timeout: 20_000 });
    expect((await readDraft(request, id)).artifacts.report).toBeTruthy();
    expect(await association(page, id, "DataObjectRef_report", "Activity_deliver", "output")).not.toBeNull();
  });
});
