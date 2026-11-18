import { test, expect, type Page } from "@playwright/test";
import { getWizardApiUrl, waitForApiHealthy } from "./helpers/api";
import { draft, draftSteps, openEditor, sessionAtBpmn, writeDraft } from "./helpers/bpmn-stack";

const STACK_E2E = process.env.PLAYWRIGHT_STACK_E2E === "true";

/**
 * The BPMN editor's step type menu and step panel against the real stack (UI
 * + wizard_api + Postgres): a type picked in the menu and a description
 * written in the panel are operations on the agent's draft, and both are
 * still there after a page reload. e2e/bpmn-step-panel.spec.ts covers the
 * panel on the mock store, where it is read-only.
 */

const rows = (page: Page) => page.getByTestId("flow-step-list").locator("li");

/** Waits for the next operation's answer and the saved line. */
async function saved(page: Page, act: () => Promise<void>) {
  const done = page.waitForResponse(
    (r) => r.url().includes("/blueprint/operations") && r.request().method() === "POST",
  );
  await act();
  expect((await done).status()).toBe(200);
  await expect(page.getByTestId("bpmn-status")).toContainText("Tallennettu", { timeout: 20_000 });
}

test.describe("BPMN step type and step panel (stack)", () => {
  test.skip(!STACK_E2E, "set PLAYWRIGHT_STACK_E2E=true (docker-test.sh --step stack-e2e)");

  test.beforeAll(async ({ request }) => {
    await waitForApiHealthy(request);
  });

  test("a type changed in the menu and a description written in the panel are both kept over a reload", async ({
    page,
    request,
  }) => {
    test.setTimeout(240_000);
    const id = await sessionAtBpmn(page, request);
    await writeDraft(request, id);
    await page.reload();
    await openEditor(page);
    await expect(rows(page)).toHaveCount(4);

    // The review step becomes an AI step in the type menu. It has no component, so the panel says so.
    await rows(page).nth(2).getByRole("button").first().click();
    const type = page.getByTestId("bpmn-step-type");
    await expect(type).toHaveValue("human_review");
    await page.locator('.djs-context-pad .entry[data-action="gaik-step-type"]').click();
    const menu = page.locator('.djs-popup-parent[data-popup="gaik-step-type"]');
    await saved(page, () => menu.locator('.entry[data-id="gaik-step-type-automated_task"]').click());
    await expect(type).toHaveValue("automated_task");
    await expect(page.getByTestId("bpmn-step-needs-component")).toBeVisible();
    // The step list shows it as an AI step at once.
    await expect(rows(page).nth(2)).toContainText("Tekoäly");

    // A description written in the panel, saved with Enter.
    const description = page.getByTestId("bpmn-step-description");
    await expect(description).toHaveValue("");
    await saved(page, async () => {
      await description.fill("The controller checks the fields by hand.");
      await description.press("Enter");
    });
    await expect(description).toHaveValue("The controller checks the fields by hand.");

    // Both are there after a reload: in the panel, in the step list and in the agent's draft.
    await page.reload();
    await openEditor(page);
    await expect(rows(page).nth(2)).toContainText("Tekoäly");
    await rows(page).nth(2).getByRole("button").first().click();
    await expect(page.getByTestId("bpmn-step-type")).toHaveValue("automated_task");
    await expect(page.getByTestId("bpmn-step-description")).toHaveValue("The controller checks the fields by hand.");
    // Still without a component in the blueprint the page loaded: the panel says so without an edit's answer.
    await expect(page.getByTestId("bpmn-step-needs-component")).toBeVisible();
    const review = (await draftSteps(request, id)).find((s) => s.id === "review");
    expect(review?.type).toBe("automated_task");
    expect(review?.description).toBe("The controller checks the fields by hand.");
    expect(review?.component).toBeUndefined();
  });
  test("a decision step has no type menu: it stays a gateway, while its other tools remain", async ({
    page,
    request,
  }) => {
    test.setTimeout(240_000);
    const id = await sessionAtBpmn(page, request);
    // The agent's draft with a decision after the review: drawn as Gateway_check, mapped as workflow.steps[3].
    const withDecision = draft();
    const steps = withDecision.workflow.steps as Record<string, unknown>[];
    steps.splice(3, 0, {
      id: "check",
      name: "Fields complete?",
      type: "decision",
      inputs: ["reviewed"],
      outputs: [],
      depends_on: ["review"],
    });
    steps[4].depends_on = ["check"];
    const written = await request.post(`${getWizardApiUrl()}/test/sessions/${id}/draft`, { data: withDecision });
    expect(written.status(), `write draft: ${await written.text()}`).toBe(204);
    // The page's version with the same five steps, as the chat sync would write it.
    const version = await request.post(`${getWizardApiUrl()}/sessions/${id}/versions`, {
      data: {
        note: "e2e: a decision",
        content: {
          name: "Invoices",
          description: "Invoice handling",
          goal: "",
          steps: [
            { id: "upload", name: "Upload invoice", type: "io" },
            { id: "extract", name: "Extract fields", type: "ai", component: "custom" },
            { id: "review", name: "Review fields", type: "human_review" },
            { id: "check", name: "Fields complete?", type: "ai" },
            { id: "deliver", name: "Deliver report", type: "ai", component: "custom" },
          ],
          integration_targets: [],
        },
      },
    });
    expect(version.ok(), `seed version: ${version.status()}`).toBe(true);
    await page.reload();
    await openEditor(page);
    await expect(rows(page)).toHaveCount(5);

    const gateway = page.locator('.bpmn-editable .djs-shape[data-element-id="Gateway_check"]');
    await page.getByTestId("bpmn-zoom-controls").getByRole("button", { name: "Sovita näkymään" }).click();
    // A flow the generator draws across it covers the gateway's middle; the click goes to the gateway itself.
    await gateway.locator(".djs-hit").first().dispatchEvent("click");
    await expect(gateway).toHaveClass(/selected/);
    // Its tools as a step (rename, append, move, delete, connect), but no type menu.
    const actions = await page
      .locator(".djs-context-pad .entry")
      .evaluateAll((els) => els.map((el) => el.getAttribute("data-action")));
    expect(actions).toEqual(["rename", "append", "gaik-add-decision", "gaik-add-rework", "move-earlier", "move-later", "delete", "connect"]);
    // The R key opens no menu either, and the step panel is not offered for it.
    await page.locator('.bpmn-editable svg[tabindex="0"]').focus();
    await page.keyboard.press("r");
    await expect(page.locator(".djs-popup-parent")).toHaveCount(0);
    await expect(page.getByTestId("bpmn-step-panel")).toHaveCount(0);
    expect((await draftSteps(request, id)).find((s) => s.id === "check")?.type).toBe("decision");

    // A task beside it still has the menu.
    await rows(page).nth(2).getByRole("button").first().click();
    await expect(page.locator('.djs-context-pad .entry[data-action="gaik-step-type"]')).toBeVisible();
  });
});
