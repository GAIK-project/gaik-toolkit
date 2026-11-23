import { test, expect, type APIRequestContext, type Page } from "@playwright/test";
import { getWizardApiUrl, waitForApiHealthy } from "./helpers/api";
import { openEditor, sessionAtBpmn, writeDraft } from "./helpers/bpmn-stack";

const STACK_E2E = process.env.PLAYWRIGHT_STACK_E2E === "true";

/**
 * Business decisions on the BPMN canvas against the real stack (UI +
 * wizard_api + Postgres): a decision added after a step with two branches is
 * drawn as its gateway and kept over a reload, in the canvas and in the
 * agent's draft; Edit changes its name and a branch, and Remove takes it
 * away. e2e/bpmn-decisions.spec.ts covers the dialog and what is sent on the
 * mock store.
 */

type Decision = { id: string; name: string; after: string; branches: { condition: string; target: string }[] };

async function decisions(request: APIRequestContext, id: string): Promise<Decision[]> {
  const res = await request.get(`${getWizardApiUrl()}/test/sessions/${id}/draft`);
  expect(res.ok()).toBe(true);
  const draft = (await res.json()) as { business_process?: { decision_points?: Decision[] } };
  return draft.business_process?.decision_points ?? [];
}

const operationAnswer = (page: Page) =>
  page.waitForResponse((r) => r.url().includes("/blueprint/operations") && r.request().method() === "POST");

const GATEWAY = "Gateway_decision_varma";

/** Picks the decision's gateway: a flow drawn across it can cover its middle, so the click goes to the gateway itself. */
async function pickGateway(page: Page) {
  await page.getByTestId("bpmn-zoom-controls").getByRole("button", { name: "Sovita näkymään" }).click();
  const gateway = page.locator(`.bpmn-editable .djs-shape[data-element-id="${GATEWAY}"]`);
  await gateway.locator(".djs-hit").first().dispatchEvent("click");
  await expect(gateway).toHaveClass(/selected/);
}

test.describe("BPMN decisions (stack)", () => {
  test.skip(!STACK_E2E, "set PLAYWRIGHT_STACK_E2E=true (docker-test.sh --step stack-e2e)");
  test.use({ viewport: { width: 1600, height: 1100 } });

  test.beforeAll(async ({ request }) => {
    await waitForApiHealthy(request);
  });

  test("a decision with two branches is kept over a reload, then edited and removed", async ({ page, request }) => {
    test.setTimeout(240_000);
    const id = await sessionAtBpmn(page, request);
    await writeDraft(request, id);
    await page.reload();
    await openEditor(page);

    // After the extract step: "Varma?", sure → review, unsure → the end.
    await page.getByTestId("flow-step-list").locator("li").nth(1).getByRole("button").first().click();
    await page.locator('.djs-context-pad .entry[data-action="gaik-add-decision"]').click();
    const dialog = page.getByTestId("bpmn-branch-dialog");
    await dialog.getByTestId("bpmn-branch-name").fill("Varma?");
    await dialog.getByTestId("bpmn-branch-condition").nth(0).fill("Varma");
    await dialog.getByTestId("bpmn-branch-target").nth(0).selectOption("review");
    await dialog.getByTestId("bpmn-branch-condition").nth(1).fill("Epävarma");
    await dialog.getByTestId("bpmn-branch-target").nth(1).selectOption("end");
    let answer = operationAnswer(page);
    await dialog.getByTestId("bpmn-branch-save").click();
    expect((await answer).status()).toBe(200);
    await expect(dialog).toHaveCount(0);
    await expect(page.locator(".bpmn-editable")).toHaveAttribute("aria-busy", "false");
    await expect(page.locator(`.bpmn-editable [data-element-id="${GATEWAY}"]`)).toHaveCount(1);
    const added: Decision = {
      id: "varma",
      name: "Varma?",
      after: "extract",
      branches: [
        { condition: "Varma", target: "review" },
        { condition: "Epävarma", target: "end" },
      ],
    };
    expect(await decisions(request, id)).toEqual([added]);

    // After a reload: drawn with its two branches, named by their conditions; the step has no second one offered.
    await page.reload();
    await openEditor(page);
    const gateway = page.locator(`.bpmn-editable [data-element-id="${GATEWAY}"]`);
    await expect(gateway).toHaveCount(1);
    const xml = await (await page.request.get(`/api/sessions/${id}/bpmn?data_objects=1`)).text();
    const flows = [...xml.matchAll(/<bpmn:sequenceFlow [^>]*>/g)].map((m) => {
      const attr = (name: string) => new RegExp(`${name}="([^"]*)"`).exec(m[0])?.[1] ?? "";
      return [attr("sourceRef"), attr("targetRef"), attr("name")].join(" ");
    });
    expect(flows).toContain(`${GATEWAY} Activity_review Varma`);
    expect(flows).toContain(`${GATEWAY} EndEvent_success Epävarma`);
    await page.getByTestId("flow-step-list").locator("li").nth(1).getByRole("button").first().click();
    await expect(page.locator('.djs-context-pad .entry[data-action="append"]')).toBeVisible();
    await expect(page.locator('.djs-context-pad .entry[data-action="gaik-add-decision"]')).toHaveCount(0);
    await page.getByTestId("bpmn-properties").getByRole("button", { name: "Sulje" }).click();

    // Edit: prefilled; renamed, and the unsure branch goes to the delivery.
    await pickGateway(page);
    await page.locator('.djs-context-pad .entry[data-action="gaik-decision-edit"]').click();
    await expect(dialog.getByTestId("bpmn-branch-name")).toHaveValue("Varma?");
    await expect(dialog.getByTestId("bpmn-branch-target").nth(1)).toHaveValue("end");
    await dialog.getByTestId("bpmn-branch-name").fill("Onko varma?");
    await dialog.getByTestId("bpmn-branch-target").nth(1).selectOption("deliver");
    answer = operationAnswer(page);
    await dialog.getByTestId("bpmn-branch-save").click();
    expect((await answer).status()).toBe(200);
    await expect(dialog).toHaveCount(0);
    await expect(page.locator(".bpmn-editable")).toHaveAttribute("aria-busy", "false");
    expect(await decisions(request, id)).toEqual([
      {
        ...added,
        name: "Onko varma?",
        branches: [added.branches[0], { condition: "Epävarma", target: "deliver" }],
      },
    ]);

    // Remove: the gateway goes, on the canvas and in the draft, also after a reload.
    // Another element first: the gateway is picked anew, and its pad opens again.
    await page.getByTestId("flow-step-list").locator("li").nth(0).getByRole("button").first().click();
    await pickGateway(page);
    answer = operationAnswer(page);
    await page.locator('.djs-context-pad .entry[data-action="gaik-decision-remove"]').click();
    expect((await answer).status()).toBe(200);
    await expect(gateway).toHaveCount(0);
    expect(await decisions(request, id)).toEqual([]);
    await page.reload();
    await openEditor(page);
    await expect(page.locator(`.bpmn-editable [data-element-id="${GATEWAY}"]`)).toHaveCount(0);
  });
});
