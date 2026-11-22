import { test, expect, type Page } from "@playwright/test";
import { waitForApiHealthy } from "./helpers/api";
import { draftSteps, openEditor, sessionAtBpmn, writeDraft } from "./helpers/bpmn-stack";
import { openBpmnView, selectWorkspaceTab, setChatOpen } from "./helpers/workspace";

const STACK_E2E = process.env.PLAYWRIGHT_STACK_E2E === "true";

/**
 * The Workflow tab's BPMN editor against the real stack (UI + wizard_api +
 * Postgres): each canvas edit is an operation on the agent's draft
 * (`use_case.blueprint.json`), and it is still there after a page reload.
 * Undo takes the last one back. e2e/bpmn-editing.spec.ts covers the editor
 * on the mock store, where it is read-only.
 *
 * The test writes and reads the agent's draft through wizard_api's test hook
 * (`/test/sessions/{id}/draft`, mounted only with WIZARD_TEST_HOOKS=1, as the
 * stack E2E's wizard-api-e2e sets it): the Playwright container cannot reach
 * the API's session folder.
 */

async function reopen(page: Page) {
  await page.reload();
  await openEditor(page);
}

const task = (page: Page, id: string) => page.locator(`.bpmn-editable .djs-shape[data-element-id="Activity_${id}"]`);
const rows = (page: Page) => page.getByTestId("flow-step-list").locator("li");

/** Picks a step from the list and presses one of its tools; waits for the operation's answer. */
async function padAction(page: Page, row: number, action: string) {
  await rows(page).nth(row).getByRole("button").first().click();
  const done = page.waitForResponse(
    (r) => r.url().includes("/blueprint/operations") && r.request().method() === "POST",
  );
  await page.locator(`.djs-context-pad .entry[data-action="${action}"]`).click();
  expect((await done).status()).toBe(200);
  await expect(page.getByTestId("bpmn-status")).toContainText("Tallennettu", { timeout: 20_000 });
}

test.describe("BPMN canvas edits as operations (stack)", () => {
  test.skip(!STACK_E2E, "set PLAYWRIGHT_STACK_E2E=true (docker-test.sh --step stack-e2e)");

  test.beforeAll(async ({ request }) => {
    await waitForApiHealthy(request);
  });

  test("rename, append, move earlier, connect and delete each survive a reload; Undo reverts the last", async ({
    page,
    request,
  }) => {
    test.setTimeout(240_000);
    const id = await sessionAtBpmn(page, request);

    // Before the agent has written its draft the diagram is read-only, and says why.
    await page.reload();
    await setChatOpen(page, false);
    await selectWorkspaceTab(page, "Työnkulku");
    await openBpmnView(page);
    await expect(page.getByTestId("bpmn-panel")).toHaveAttribute("data-ops", "no_draft", { timeout: 45_000 });
    await expect(page.getByTestId("bpmn-readonly-editing")).toContainText(
      "kun wizard on kirjoittanut ensimmäisen blueprintin",
    );
    await expect(page.locator(".bpmn-editable .djs-palette")).toHaveCount(0);

    await writeDraft(request, id);
    const steps = () => draftSteps(request, id);
    await page.reload();
    await openEditor(page);
    await expect(rows(page)).toHaveCount(4);

    // Rename in the name field.
    await rows(page).nth(1).getByRole("button").first().click();
    const name = page.getByTestId("bpmn-property-name");
    await expect(name).toHaveValue("Extract fields");
    const renamed = page.waitForResponse((r) => r.url().includes("/blueprint/operations"));
    await name.fill("Read the fields");
    await name.press("Enter");
    expect((await renamed).status()).toBe(200);
    // The step list and the canvas take it at once, without a reload.
    await expect(rows(page).nth(1)).toContainText("Read the fields");
    await expect(task(page, "extract")).toContainText("Read the fields");
    await reopen(page);
    await expect(task(page, "extract")).toContainText("Read the fields");
    expect((await steps()).find((s) => s.id === "extract")?.name).toBe("Read the fields");

    // Append a step after the first one.
    await padAction(page, 0, "append");
    await reopen(page);
    await expect(rows(page)).toHaveCount(5);
    const added = (await steps())[1];
    expect(added.depends_on).toEqual(["upload"]);
    await expect(task(page, added.id)).toBeVisible();

    // Move the new step one place earlier, to the start: the old first step follows it.
    // (A step that reads what the step before it writes cannot move before it: the
    // server refuses that, rule 7.)
    await padAction(page, 1, "move-earlier");
    await reopen(page);
    const moved = (await steps());
    expect(moved.map((s) => s.id).slice(0, 2)).toEqual([added.id, "upload"]);
    expect(moved.find((s) => s.id === "upload")?.depends_on).toEqual([added.id]);
    await expect(rows(page).nth(0)).toContainText("Uusi vaihe");

    // Connect the first step to the last one with the connect tool. The first
    // step's panel is closed first: it stays closed while that step is picked,
    // and would cover the last step at the canvas's right edge.
    await rows(page).nth(1).getByRole("button").first().click();
    await page.getByTestId("bpmn-properties").getByRole("button", { name: "Sulje" }).click();
    await page.getByTestId("bpmn-zoom-controls").getByRole("button", { name: "Sovita näkymään" }).click();
    const connected = page.waitForResponse((r) => r.url().includes("/blueprint/operations"));
    await page.locator('.bpmn-editable .djs-palette .entry[data-action="global-connect-tool"]').click();
    await task(page, "upload").click();
    await task(page, "deliver").hover();
    await task(page, "deliver").click();
    expect((await connected).status()).toBe(200);
    await reopen(page);
    expect((await steps()).find((s) => s.id === "deliver")?.depends_on).toContain("upload");

    // Delete the deliver step.
    const count = (await steps()).length;
    await padAction(page, count - 1, "delete");
    // The server's warnings are said with "Tallennettu": the report the step made went with it.
    await expect(page.getByTestId("bpmn-warnings")).toContainText('Removed artifact "report"');
    await reopen(page);
    await expect(task(page, "deliver")).toHaveCount(0);
    expect((await steps()).some((s) => s.id === "deliver")).toBe(false);

    // Undo brings the deleted step back, also after a reload.
    const undone = page.waitForResponse((r) => r.url().includes("/blueprint/undo"));
    await page.getByTestId("bpmn-undo").click();
    expect((await undone).status()).toBe(200);
    await expect(page.getByTestId("bpmn-status")).toContainText("Viimeisin muutos kumottu.");
    await reopen(page);
    await expect(task(page, "deliver")).toBeVisible();
    expect((await steps()).some((s) => s.id === "deliver")).toBe(true);
    expect((await steps()).find((s) => s.id === "extract")?.name).toBe("Read the fields");
  });

  test("the editor comes back from the simple flow with the last edit in the diagram, also after an Undo", async ({
    page,
    request,
  }) => {
    test.setTimeout(240_000);
    const id = await sessionAtBpmn(page, request);
    await writeDraft(request, id);
    const steps = () => draftSteps(request, id);
    await page.reload();
    await openEditor(page);
    await expect(rows(page)).toHaveCount(4);
    const rename = async (row: number, value: string) => {
      await rows(page).nth(row).getByRole("button").first().click();
      const answered = page.waitForResponse((r) => r.url().includes("/blueprint/operations"));
      const field = page.getByTestId("bpmn-property-name");
      await field.fill(value);
      await field.press("Enter");
      expect((await answered).status()).toBe(200);
      await expect(page.getByTestId("bpmn-status")).toContainText("Tallennettu", { timeout: 20_000 });
    };
    const throughTheSimpleFlow = async () => {
      await page.getByTestId("flow-view-diagram").click();
      await expect(page.getByTestId("bpmn-panel")).toHaveCount(0);
      await page.getByTestId("flow-view-bpmn").click();
      await expect(page.getByTestId("bpmn-panel")).toHaveAttribute("data-ops", "on", { timeout: 45_000 });
    };

    await rename(1, "Read the fields");
    await throughTheSimpleFlow();
    await expect(task(page, "extract")).toContainText("Read the fields");

    // An edit made from the remounted editor goes to the server on the newest version and stays.
    await rename(0, "Take the file in");
    await throughTheSimpleFlow();
    const [first] = await steps();
    expect(first.name).toBe("Take the file in");
    await expect(task(page, first.id)).toContainText("Take the file in");

    // Undo takes the second rename back; the editor shows that after the round trip too.
    const undone = page.waitForResponse((r) => r.url().includes("/blueprint/undo"));
    await page.getByTestId("bpmn-undo").click();
    expect((await undone).status()).toBe(200);
    await throughTheSimpleFlow();
    await expect(task(page, first.id)).not.toContainText("Take the file in");
    await expect(task(page, "extract")).toContainText("Read the fields");
  });
});
