import { test, expect } from "@playwright/test";
import { loginAsDev } from "./helpers/auth";
import { openBlueprintEditor, openBpmnView, selectWorkspaceTab } from "./helpers/workspace";
import { setMockSessionStep } from "./helpers/dev-step";
import { resetMockSessions } from "./helpers/mock";
import { createSession } from "./helpers/session";

/**
 * #74: create from scratch → dummy blueprint → BPMN visible at phase 8,
 * chat collapsed by default.
 */
test.describe("New session dummy BPMN + collapsed chat", () => {
  test.beforeEach(async ({ request }) => {
    await resetMockSessions(request);
  });

  test("create session → advance to BPMN → canvas + chat rail", async ({
    page,
    request,
    baseURL,
  }) => {
    test.setTimeout(120_000);
    await loginAsDev(page);

    const title = `Dummy BPMN ${Date.now()}`;
    await createSession(page, title);
    await expect(page.getByRole("heading", { name: title, level: 1 })).toBeVisible();

    // Gathering: chat open by default.
    await expect(page.getByTestId("chat-dock")).toHaveAttribute(
      "data-chat-open",
      "true",
    );

    // Gathering (steps 1-3) no longer advances from the UI — the agent moves
    // the session on, and "Seuraava vaihe →" only explains that. So put the
    // session on the BPMN phase (8) directly; this spec is about what the BPMN
    // phase renders, not about how the flow gets there.
    const sessionId = new URL(page.url()).pathname.split("/").pop() as string;
    await setMockSessionStep(request, baseURL as string, sessionId, 8);
    await page.reload({ waitUntil: "domcontentloaded" });

    // One heading, addressed by test id: the inner views repeat the phase name.
    await expect(page.getByTestId("workspace-phase")).toHaveText(
      /Visuaalinen työnkulku/,
      { timeout: 15_000 },
    );

    await expect(
      page.getByRole("heading", { name: "Visuaalinen työnkulku (BPMN)" }),
    ).toBeVisible({ timeout: 15_000 });

    // Chat collapsed so canvas has room.
    await expect(page.getByTestId("chat-dock")).toHaveAttribute(
      "data-chat-open",
      "false",
    );
    await expect(page.getByTestId("chat-dock-toggle")).toHaveAttribute(
      "aria-expanded",
      "false",
    );

    const workspacePanel = page.locator('[role="tabpanel"]:visible');
    // The tab opens on the simple flow; this spec edits on the BPMN canvas.
    await openBpmnView(page);
    // The diagram is generated in a child process; give it time on a busy machine.
    await expect(workspacePanel.getByTestId("bpmn-zoom-controls")).toBeVisible({
      timeout: 45_000,
    });
    await expect(
      workspacePanel.locator(".bpmn-viewer-themed .djs-container"),
    ).toBeVisible({ timeout: 15_000 });

    // The Blueprint tab does not show the session's first draft as the
    // solution: one line in the steps' place, and nothing to edit yet.
    await selectWorkspaceTab(page, /Blueprint/);
    await expect(page.getByTestId("plan-preparing")).toHaveText(
      "Wizard valmistelee ratkaisun rakennetta. Se näkyy tässä, kun se on valmis.",
    );
    await expect(page.getByTestId(/^plan-step-\d+$/)).toHaveCount(0);
    await expect(page.getByTestId("blueprint-edit")).toHaveCount(0);

    // BPMN property edit on the canvas.
    await page.getByRole("tab", { name: "Työnkulku" }).click();
    await expect(
      workspacePanel.locator(".bpmn-viewer-themed .djs-container"),
    ).toBeVisible({ timeout: 15_000 });

    // Pick the second step from the list beside the diagram; a rename saves itself.
    await workspacePanel.getByTestId("flow-step-1").getByRole("button").first().click();
    const nameInput = workspacePanel.getByTestId("bpmn-property-name");
    await expect(nameInput).toBeVisible({ timeout: 10_000 });
    const sync = page.waitForResponse(
      (r) => r.url().includes("/bpmn/sync") && r.request().method() === "POST",
    );
    await nameInput.fill("Assess factory risk");
    expect((await sync).status()).toBe(200);
    await expect(workspacePanel.getByTestId("bpmn-status")).toContainText("Tallennettu", {
      timeout: 20_000,
    });

    // The steps are someone's design now: the Blueprint tab shows them and
    // can be edited. JSON edit on the blueprint.
    await openBlueprintEditor(page);
    await page.getByTestId("blueprint-json-toggle").click();
    const editor = page.getByTestId("blueprint-json-editor");
    await expect(editor).toBeVisible();
    const parsed = JSON.parse(await editor.inputValue()) as {
      description: string;
      steps: Array<{ id: string; name: string }>;
    };
    expect(parsed.steps.length).toBeGreaterThanOrEqual(3);
    expect(parsed.description.toLowerCase()).toContain("placeholder");
    parsed.steps = parsed.steps.map((s) =>
      s.id === "input" ? { ...s, name: "Safety observation note" } : s,
    );
    // The form saves by itself a moment after the edit.
    const patched = page.waitForResponse(
      (r) => r.url().endsWith("/blueprint") && r.request().method() === "PATCH",
    );
    await editor.fill(JSON.stringify(parsed, null, 2));
    expect((await patched).status()).toBe(200);
    await expect(page.getByTestId("blueprint-save-status")).toHaveText("Tallennettu", {
      timeout: 15_000,
    });

    const after = JSON.parse(await editor.inputValue()) as {
      steps: Array<{ id: string; name: string }>;
    };
    const names = after.steps.map((s) => s.name);
    expect(names).toContain("Safety observation note");
    expect(names).toContain("Assess factory risk");
  });
});
