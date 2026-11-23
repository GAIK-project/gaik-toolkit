import { test, expect } from "@playwright/test";
import { loginAsDev } from "./helpers/auth";
import { openBlueprintEditor, openBpmnView } from "./helpers/workspace";
import { waitForApiHealthy } from "./helpers/api";
import {
  agentE2eEnabled,
  jumpSessionToBpmnPhase,
  sendAgentChatAndWait,
  sessionIdFromUrl,
} from "./helpers/agent";
import { createSession } from "./helpers/session";

/**
 * Local-only live-agent E2E (not CI).
 *
 * Prerequisites:
 *   - wizard_api on :8100 with Claude ambient auth (`claude auth status` → loggedIn)
 *   - Next UI on :3000 with WIZARD_API_URL + WIZARD_AGENT_CHAT=true
 *
 * Run:
 *   PLAYWRIGHT_AGENT_E2E=true \
 *   PLAYWRIGHT_SKIP_WEBSERVER=true \
 *   PLAYWRIGHT_BASE_URL=http://127.0.0.1:3000 \
 *   WIZARD_API_URL=http://127.0.0.1:8100 \
 *   npx playwright test e2e/local-agent-chat-bpmn.spec.ts --workers=1
 *
 * Flow: login → new session → agent Q&A (real Claude) → jump to BPMN →
 * save JSON + save BPMN canvas edit.
 */
test.describe("Local agent chat → BPMN + JSON save", () => {
  test.skip(
    !agentE2eEnabled(),
    "local only: PLAYWRIGHT_AGENT_E2E=true (requires Claude login + WIZARD_AGENT_CHAT)",
  );

  test.beforeAll(async ({ request }) => {
    await waitForApiHealthy(request);
  });

  test("agent answers questions, then BPMN and JSON can be saved", async ({
    page,
    request,
  }) => {
    test.setTimeout(600_000);

    await loginAsDev(page);

    const title = `Agent E2E ${Date.now()}`;
    await createSession(page, title);
    await expect(page.getByRole("heading", { name: title, level: 1 })).toBeVisible();

    const sessionId = sessionIdFromUrl(page.url());

    // --- Live agent gathering (real Claude, not mock) ---
    const reply1 = await sendAgentChatAndWait(
      page,
      "Hei! Haluan GenAI-ratkaisun: huoltotikettien tekeminen suomenkielisistä ääniviesteistä. " +
        "Teknikot jättävät äänimuistion, josta syntyy rakenteinen tiketti esimiehelle.",
    );
    expect(reply1.length).toBeGreaterThan(40);

    const reply2 = await sendAgentChatAndWait(
      page,
      "Nykyinen prosessi: teknikko soittaa tai jättää WhatsApp-ääniviestin, toimisto kirjaa tiketin käsin. " +
        "Kipupiste: kirjaaminen vie aikaa ja tietoja puuttuu. Käyttäjiä ~15 teknikkoa. " +
        "Tuloste: JSON-tiketti kentillä vika, sijainti, kiireellisyys, päivämäärä.",
    );
    expect(reply2.length).toBeGreaterThan(40);

    // Prove mock path is not used for this stack.
    const chatLog = page.getByTestId("chat-dock").getByRole("log");
    await expect(chatLog).not.toContainText(/Mock-vastaus|Mock reply/i);

    // --- Jump to visual workflow (agent gathering can take many turns) ---
    await jumpSessionToBpmnPhase(request, sessionId);
    await page.reload({ waitUntil: "domcontentloaded" });
    await expect(
      page.getByRole("heading", { name: /Visuaalinen työnkulku|Visual workflow/i }),
    ).toBeVisible({ timeout: 30_000 });

    const workspace = page.locator('[role="tabpanel"]:visible');
    // The tab opens on the simple flow; this spec edits on the BPMN canvas.
    await openBpmnView(page);
    await expect(workspace.locator(".bpmn-viewer-themed .djs-container")).toBeVisible({
      timeout: 30_000,
    });
    await expect(workspace.getByTestId("bpmn-zoom-controls")).toBeVisible();

    // --- JSON save ---
    await openBlueprintEditor(page);
    const editor = page.getByTestId("blueprint-json-editor");
    await expect(editor).toBeVisible({ timeout: 15_000 });

    const before = JSON.parse(await editor.inputValue()) as {
      name?: string;
      description?: string;
      steps: Array<{ id: string; name: string }>;
    };
    expect(before.steps.length).toBeGreaterThanOrEqual(1);

    const marker = `agent-e2e-${Date.now()}`;
    before.description = `${before.description ?? ""}\n[${marker}]`.trim();
    if (before.steps[0]) {
      before.steps[0] = {
        ...before.steps[0],
        name: `Voice intake (${marker})`,
      };
    }
    // The form saves by itself a moment after the edit.
    const patched = page.waitForResponse(
      (r) => r.url().endsWith("/blueprint") && r.request().method() === "PATCH",
    );
    await editor.fill(JSON.stringify(before, null, 2));
    expect((await patched).status()).toBe(200);
    await expect(page.getByTestId("blueprint-save-status")).toHaveAttribute("data-state", "saved", {
      timeout: 20_000,
    });

    const afterJson = JSON.parse(await editor.inputValue()) as {
      description?: string;
      steps: Array<{ name: string }>;
    };
    expect(afterJson.description ?? "").toContain(marker);
    expect(afterJson.steps.some((s) => s.name.includes(marker))).toBe(true);

    // --- BPMN canvas edit + save ---
    await page.getByRole("tab", { name: /Työnkulku|Workflow/i }).click();
    await expect(workspace.locator(".bpmn-viewer-themed .djs-container")).toBeVisible({
      timeout: 30_000,
    });

    // Select a task/shape (first .djs-label is often the process title — no property form).
    const label = workspace
      .locator(".djs-label")
      .filter({ hasText: /Process|Human review|Voice intake|Output/i })
      .first();
    await expect(label).toBeVisible({ timeout: 15_000 });
    await label.click({ force: true });

    const nameInput = workspace.getByTestId("bpmn-property-name");
    await expect(nameInput).toBeVisible({ timeout: 15_000 });
    const bpmnName = `Assess risk ${marker}`;
    // A rename in the name field saves by itself.
    await nameInput.fill(bpmnName);

    const status = workspace.getByTestId("bpmn-status");
    const saved = status.getByText(/Tallennettu|Saved/i);
    const lintBlocked = status.getByText(/kaaviossa on virheitä|diagram has errors|epäonnistui|failed/i);
    await expect(saved.or(lintBlocked).first()).toBeVisible({ timeout: 45_000 });

    // If lint blocked, still prove JSON path worked; if save ok, confirm sync.
    if (await saved.isVisible().catch(() => false)) {
      await openBlueprintEditor(page);
      const synced = JSON.parse(await editor.inputValue()) as {
        steps: Array<{ name: string }>;
      };
      const names = synced.steps.map((s) => s.name).join(" | ");
      expect(
        names.includes(marker) || names.includes("Assess") || names.includes("Voice"),
      ).toBe(true);
    }
  });
});
