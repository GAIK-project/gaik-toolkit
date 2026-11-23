import { test, expect } from "@playwright/test";
import { loginAsDev } from "./helpers/auth";
import { resetMockSessions } from "./helpers/mock";
import { setMockSessionStep } from "./helpers/dev-step";
import { openBpmnView, selectWorkspaceTab } from "./helpers/workspace";
import fs from "node:fs";
import path from "node:path";

/**
 * Screenshots: V2 BPMN with integration_targets → data store.
 *
 *   PLAYWRIGHT_SKIP_WEBSERVER=true \
 *   PLAYWRIGHT_BASE_URL=http://127.0.0.1:3040 \
 *   npx playwright test e2e/bpmn-data-stores.spec.ts --project=chromium
 */
const SHOT_DIR = path.join(__dirname, "screenshots", "bpmn-data-stores");

test.describe("BPMN data stores", () => {
  test.beforeEach(async ({ request }) => {
    await resetMockSessions(request);
  });

  test("chatbot BPMN shows Knowledge Base data store", async ({ page, request, baseURL }) => {
    test.setTimeout(120_000);
    fs.mkdirSync(SHOT_DIR, { recursive: true });

    await loginAsDev(page);
    // step 6 → 8 (Visuaalinen työnkulku): the page has no step buttons.
    await setMockSessionStep(request, baseURL as string, "ses_chatbot", 8);
    await page.goto("/sessions/ses_chatbot");
    await page.waitForURL(/\/sessions\/ses_chatbot$/);
    await expect(
      page.getByRole("heading", { name: "Visuaalinen työnkulku (BPMN)" }),
    ).toBeVisible();

    const workspacePanel = page.locator('[role="tabpanel"]:visible');
    // The tab opens on the simple flow; the data store is drawn in the BPMN view.
    await openBpmnView(page);
    await expect(
      workspacePanel.locator(".bpmn-viewer-themed .djs-container"),
    ).toBeVisible({ timeout: 20_000 });

    // Fit the whole diagram so the data store is in frame
    await workspacePanel.getByRole("button", { name: "Sovita näkymään" }).click();
    await page.waitForTimeout(1200);

    await page.screenshot({
      path: path.join(SHOT_DIR, "01-bpmn-with-data-store.png"),
      fullPage: true,
    });

    // Diagram canvas only
    await workspacePanel
      .locator(".bpmn-viewer-themed")
      .screenshot({ path: path.join(SHOT_DIR, "02-canvas-data-store.png") });

    // Invoice session — finance_system store
    await page.goto("/sessions/ses_laskut");
    await page.waitForURL(/\/sessions\/ses_laskut$/);
    // ses_laskut is already at step 11, so it opens on the PoC tab: the
    // diagram is on Työnkulku.
    await selectWorkspaceTab(page, "Työnkulku");
    await openBpmnView(page);
    // The diagram is fetched when its tab opens, no longer with the page.
    await expect(
      page.locator(".bpmn-viewer-themed .djs-container"),
    ).toBeVisible({ timeout: 45_000 });
    await page.waitForTimeout(1000);
    await page.screenshot({
      path: path.join(SHOT_DIR, "03-invoice-finance-store.png"),
      fullPage: true,
    });
  });
});
