import { test, expect } from "@playwright/test";
import { loginAsDev } from "./helpers/auth";
import { openBlueprintEditor, openBpmnView } from "./helpers/workspace";
import { setMockSessionStep } from "./helpers/dev-step";
import { resetMockSessions } from "./helpers/mock";
import fs from "node:fs";
import path from "node:path";
import { createSession } from "./helpers/session";

/**
 * Demo — create from scratch → dummy BPMN → JSON + BPMN edits.
 *
 *   PLAYWRIGHT_SKIP_WEBSERVER=true \
 *   PLAYWRIGHT_BASE_URL=http://127.0.0.1:3026 \
 *   PLAYWRIGHT_SLOW_MO=700 \
 *   npx playwright test e2e/demo-new-session-bpmn-video.spec.ts --project=chromium
 *
 * Video → e2e/videos/wizard-v2-new-session-bpmn-demo-1080p.webm
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

test.describe("Wizard V2 new-session BPMN demo video", () => {
  // Demo recording only — keep CI focused on new-session-dummy-bpmn.spec.ts.
  test.skip(!!process.env.CI, "demo video — run locally with PLAYWRIGHT_SLOW_MO");

  test.beforeEach(async ({ request }) => {
    await resetMockSessions(request);
  });

  test("create → BPMN → JSON edit → BPMN edit", async ({ page, request, baseURL }) => {
    test.setTimeout(300_000);
    fs.mkdirSync(OUT_DIR, { recursive: true });
    const video = page.video();

    await loginAsDev(page);
    await page.waitForTimeout(900);

    const title = "Factory safety — new session demo";
    await createSession(page, title);
    await expect(page.getByRole("heading", { name: title, level: 1 })).toBeVisible();
    await page.waitForTimeout(1400);

    // Mock mode cannot walk this path any more: gathering (1-3) is the
    // agent's to advance, and Gate 1 holds approval until the requirements
    // are captured (#95/#98) — with a fresh mock session they never are. The
    // recording is about the BPMN phase, so go there directly.
    const sessionId = new URL(page.url()).pathname.split("/").pop() as string;
    await setMockSessionStep(request, baseURL as string, sessionId, 8);
    await page.reload({ waitUntil: "domcontentloaded" });
    await page.waitForTimeout(1200);

    await expect(page.getByTestId("workspace-phase")).toHaveText(
      /Visuaalinen työnkulku/,
      { timeout: 15_000 },
    );

    await expect(
      page.getByRole("heading", { name: "Visuaalinen työnkulku (BPMN)" }),
    ).toBeVisible();
    await page.waitForTimeout(1000);

    await expect(page.getByTestId("chat-dock")).toHaveAttribute(
      "data-chat-open",
      "false",
    );

    const workspacePanel = page.locator('[role="tabpanel"]:visible');
    // The tab opens on the simple flow; this recording edits on the BPMN canvas.
    await openBpmnView(page);
    // The diagram is generated in a child process; give it time on a busy machine.
    await expect(workspacePanel.getByTestId("bpmn-zoom-controls")).toBeVisible({
      timeout: 45_000,
    });
    await expect(
      workspacePanel.locator(".bpmn-viewer-themed .djs-container"),
    ).toBeVisible({ timeout: 15_000 });
    await page.waitForTimeout(1800);

    // --- JSON edit ---
    await openBlueprintEditor(page);
    await page.waitForTimeout(900);
    await page.getByTestId("blueprint-json-toggle").click();
    await page.waitForTimeout(400);
    const editor = page.getByTestId("blueprint-json-editor");
    await expect(editor).toBeVisible();
    const parsed = JSON.parse(await editor.inputValue()) as {
      description: string;
      steps: Array<{ id: string; name: string }>;
    };
    expect(parsed.steps.length).toBeGreaterThanOrEqual(3);
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
    await page.waitForTimeout(1400);

    // --- BPMN edit ---
    await page.getByRole("tab", { name: "Työnkulku" }).click();
    await expect(
      workspacePanel.locator(".bpmn-viewer-themed .djs-container"),
    ).toBeVisible({ timeout: 15_000 });
    await page.waitForTimeout(1600);

    // Pick the second step from the list beside the diagram; a rename saves itself.
    await workspacePanel.getByTestId("flow-step-1").getByRole("button").first().click();
    await page.waitForTimeout(900);

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
    await page.waitForTimeout(1600);

    await openBlueprintEditor(page);
    await page.waitForTimeout(1200);
    const after = JSON.parse(await editor.inputValue()) as {
      steps: Array<{ id: string; name: string }>;
    };
    const names = after.steps.map((s) => s.name);
    expect(names).toContain("Safety observation note");
    expect(names).toContain("Assess factory risk");
    await page.waitForTimeout(1400);

    await page.getByRole("tab", { name: "Työnkulku" }).click();
    await page.waitForTimeout(1800);

    await page.getByTestId("chat-dock-toggle").click();
    await expect(page.getByTestId("chat-dock")).toHaveAttribute(
      "data-chat-open",
      "true",
    );
    await page.waitForTimeout(1400);
    await page.getByTestId("chat-dock-toggle").click();
    await page.waitForTimeout(1600);

    await page.close();
    const videoPath = await video?.path();
    if (videoPath && fs.existsSync(videoPath)) {
      const dest1080 = path.join(
        OUT_DIR,
        "wizard-v2-new-session-bpmn-demo-1080p.webm",
      );
      const dest = path.join(OUT_DIR, "wizard-v2-new-session-bpmn-demo.webm");
      fs.copyFileSync(videoPath, dest1080);
      fs.copyFileSync(videoPath, dest);
    }
  });
});
