import { test, expect, type Page } from "@playwright/test";
import { waitForApiHealthy } from "./helpers/api";
import { draftSteps, openEditor, sessionAtBpmn, writeDraft } from "./helpers/bpmn-stack";

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
});
