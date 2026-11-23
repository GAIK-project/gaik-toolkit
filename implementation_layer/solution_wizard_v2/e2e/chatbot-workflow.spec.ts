import { expect, test } from "@playwright/test";
import { loginAsDev } from "./helpers/auth";
import { openBlueprintEditor, openBpmnView } from "./helpers/workspace";
import { resetMockSessions } from "./helpers/mock";
import { setMockSessionStep } from "./helpers/dev-step";

/**
 * Smoke test for the seeded "Customer service chatbot" mock session (ses_chatbot).
 * Covers login → session list → wizard workspace → chat SSE → blueprint JSON → PoC mock run.
 * The PoC opens after Gate 2, so the session is moved to the PoC step for the last part.
 */
test.describe("Customer service chatbot (mock)", () => {
  test.beforeEach(async ({ request }) => {
    await resetMockSessions(request);
  });

  test("walks through chatbot use case in the wizard UI", async ({ page, request, baseURL }) => {
    // The walk now loads the session a second time, at the PoC step.
    test.setTimeout(120_000);
    await loginAsDev(page);
    await page.goto("/sessions/ses_chatbot");
    await page.waitForURL(/\/sessions\/ses_chatbot$/);

    await expect(
      page.getByRole("heading", { name: "Customer service chatbot", level: 1 }),
    ).toBeVisible();

    const workspacePanel = page.locator('[role="tabpanel"]:visible');

    // Step 6 — before phase 8: the blueprint's read view, no BPMN and no Työnkulku tab yet.
    await expect(page.getByRole("tab", { name: "Työnkulku" })).toHaveCount(0);
    await expect(workspacePanel.getByTestId("bpmn-zoom-controls")).toHaveCount(0);
    await expect(workspacePanel.getByText("Retrieval (RAG)")).toBeVisible();
    // The component sits behind the step's disclosure.
    await workspacePanel.getByTestId("plan-step-1").getByText("Komponentti ja asetukset").click();
    await expect(workspacePanel.getByText("pgvector")).toBeVisible();

    // On to phase 8 (Visuaalinen työnkulku / BPMN). The page has no step
    // buttons: the session moves as the wizard writes its files.
    await setMockSessionStep(request, baseURL as string, "ses_chatbot", 8);
    const bpmnAnswer = page.waitForResponse((r) => r.url().includes("/bpmn"), { timeout: 15_000 });
    await page.reload();
    // The phase is named above the workspace (and on the session's row in the sidebar).
    await expect(page.getByTestId("workspace-phase")).toHaveText("Visuaalinen työnkulku (BPMN)");

    const bpmnResponse = await bpmnAnswer;
    expect(bpmnResponse.status()).toBe(200);

    // The tab opens on the simple flow; the BPMN editor is one click away.
    await expect(workspacePanel.getByTestId("simple-flow-node-0")).toBeVisible({ timeout: 20_000 });
    await openBpmnView(page);
    // The Työnkulku tab mounts at this step, and in dev React runs its fetch
    // twice: the editor is drawn after the second answer, not the one above.
    await expect(workspacePanel.getByTestId("bpmn-zoom-controls")).toBeVisible({ timeout: 20_000 });
    await expect(
      workspacePanel.locator(".bpmn-viewer-themed .djs-container"),
    ).toBeVisible({ timeout: 15_000 });
    await expect(
      workspacePanel.getByRole("button", { name: "Sovita näkymään" }),
    ).toBeVisible();
    // Nothing has been edited, so there is nothing to save.
    await expect(workspacePanel.getByTestId("bpmn-save")).toHaveCount(0);

    // Chat — mock SSE reply references current phase (step 8 = BPMN).
    // BPMN phase collapses chat by default (GAIK review); open it before typing.
    const chatDock = page.getByTestId("chat-dock");
    if ((await chatDock.getAttribute("data-chat-open")) === "false") {
      await page.getByTestId("chat-dock-toggle").click();
    }
    await expect(chatDock).toHaveAttribute("data-chat-open", "true");
    const chatPanel = page.getByRole("complementary", { name: "Keskustelu" });
    await expect(chatPanel.getByTestId("chat-ai-notice")).toHaveText(
      "Vastaukset tuottaa tekoäly. Tarkista ne ennen käyttöä.",
    );
    // Screen readers hear who is speaking before each assistant message.
    await expect(chatPanel.getByRole("log").getByText("Tekoälyavustaja:").first()).toBeAttached();
    const chatInput = chatPanel.getByLabel("Viesti wizardille");
    const sendButton = chatPanel.getByRole("button", { name: "Lähetä" });
    await chatInput.fill("Haluaisimme vastata tuotekysymyksiin automaattisesti.");
    await expect(sendButton).toBeEnabled();
    await sendButton.click();

    await expect(chatPanel.getByRole("log").getByText("Mock-vastaus")).toBeVisible({
      timeout: 15_000,
    });

    // Blueprint tab: component surfaces in the JSON escape hatch.
    await openBlueprintEditor(page);
    await page.getByTestId("blueprint-json-toggle").click();
    await expect(page.getByTestId("blueprint-json-editor")).toHaveValue(/"pgvector"/);

    // PoC mock run. The tab is locked until Gate 2 is approved; a session at
    // the PoC step opens on it.
    await expect(page.getByRole("tab", { name: "PoC" })).toHaveAttribute("aria-disabled", "true");
    await setMockSessionStep(request, baseURL as string, "ses_chatbot", 10);
    await page.reload();
    await expect(page.getByRole("tab", { name: "PoC" })).toHaveAttribute("aria-selected", "true");
    await workspacePanel.getByRole("button", { name: "Generoi PoC-paketti" }).click();
    await expect(workspacePanel.getByText("Onnistui")).toBeVisible({
      timeout: 15_000,
    });
  });
});
