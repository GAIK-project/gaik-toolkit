import { test, expect } from "@playwright/test";
import { loginAsDev } from "./helpers/auth";
import { openBlueprintEditor, openBpmnView } from "./helpers/workspace";
import { resetMockSessions } from "./helpers/mock";
import { setMockSessionStep } from "./helpers/dev-step";
import fs from "node:fs";
import path from "node:path";

/**
 * Demo video — BPMN data stores from V2 integration_targets.
 *
 *   PLAYWRIGHT_SKIP_WEBSERVER=true \
 *   PLAYWRIGHT_BASE_URL=http://127.0.0.1:3040 \
 *   PLAYWRIGHT_SLOW_MO=700 \
 *   npx playwright test e2e/demo-bpmn-data-stores-video.spec.ts --project=chromium
 *
 * Output: e2e/videos/wizard-v2-bpmn-data-stores-demo-1080p.webm
 */
test.use({
  video: {
    mode: "on",
    size: { width: 1920, height: 1080 },
  },
  viewport: { width: 1920, height: 1080 },
  deviceScaleFactor: 2,
});

const OUT_DIR = path.join(__dirname, "videos");
const SHOT_DIR = path.join(__dirname, "screenshots", "bpmn-data-stores");

test.describe("Wizard V2 BPMN data stores demo video", () => {
  test.beforeEach(async ({ request }) => {
    await resetMockSessions(request);
  });

  test("show data store on canvas + JSON field", async ({ page, request, baseURL }) => {
    test.setTimeout(180_000);
    fs.mkdirSync(OUT_DIR, { recursive: true });
    fs.mkdirSync(SHOT_DIR, { recursive: true });
    const video = page.video();

    await loginAsDev(page);
    await page.waitForTimeout(800);

    // The diagram step: the page has no step buttons, so the session is put there.
    await setMockSessionStep(request, baseURL as string, "ses_chatbot", 8);
    await page.goto("/sessions/ses_chatbot");
    await page.waitForURL(/\/sessions\/ses_chatbot$/);
    await page.waitForTimeout(1000);
    await expect(
      page.getByRole("heading", { name: "Visuaalinen työnkulku (BPMN)" }),
    ).toBeVisible();
    await page.waitForTimeout(900);

    const workspacePanel = page.locator('[role="tabpanel"]:visible');
    // The tab opens on the simple flow; the data store is drawn in the BPMN view.
    await openBpmnView(page);
    // The diagram is generated in a child process; give it time on a busy machine.
    await expect(
      workspacePanel.locator(".bpmn-viewer-themed .djs-container"),
    ).toBeVisible({ timeout: 45_000 });

    await workspacePanel.getByRole("button", { name: "Sovita näkymään" }).click();
    await page.waitForTimeout(1800);

    await page.screenshot({
      path: path.join(SHOT_DIR, "demo-01-bpmn-overview.png"),
      fullPage: false,
    });

    // Show JSON source of truth with integration_targets
    await openBlueprintEditor(page);
    await page.waitForTimeout(1000);
    await page.getByTestId("blueprint-json-toggle").click();
    await page.waitForTimeout(400);
    const editor = page.getByTestId("blueprint-json-editor");
    await expect(editor).toBeVisible({ timeout: 15_000 });
    const text = await editor.inputValue();
    expect(text).toContain("integration_targets");
    expect(text).toContain("knowledge_base");

    // Focus editor so JSON is clearly in the recording
    await editor.click();
    await page.waitForTimeout(1200);
    await page.screenshot({
      path: path.join(SHOT_DIR, "demo-02-json-integration-targets.png"),
      fullPage: false,
    });

    // Back to BPMN — pause on canvas so store is visible
    await page.getByRole("tab", { name: /Työnkulku|Workflow/i }).click();
    await page.waitForTimeout(1200);
    await expect(
      workspacePanel.locator(".bpmn-viewer-themed .djs-container"),
    ).toBeVisible({ timeout: 45_000 });
    await workspacePanel.getByRole("button", { name: "Sovita näkymään" }).click();
    await page.waitForTimeout(2500);
    await page.screenshot({
      path: path.join(SHOT_DIR, "demo-03-bpmn-data-store-final.png"),
      fullPage: false,
    });
    await workspacePanel.locator(".bpmn-viewer-themed").screenshot({
      path: path.join(SHOT_DIR, "demo-04-canvas-closeup.png"),
    });

    if (video) {
      const tmp = await video.path();
      await page.close();
      const dest = path.join(OUT_DIR, "wizard-v2-bpmn-data-stores-demo-1080p.webm");
      if (tmp && fs.existsSync(tmp)) {
        fs.copyFileSync(tmp, dest);
      }
      expect(fs.existsSync(dest)).toBeTruthy();
    }
  });
});
