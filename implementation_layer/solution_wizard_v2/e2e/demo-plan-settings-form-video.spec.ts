import { test, expect } from "@playwright/test";
import { loginAsDev } from "./helpers/auth";
import { openBlueprintEditor } from "./helpers/workspace";
import { resetMockSessions } from "./helpers/mock";
import fs from "node:fs";
import path from "node:path";

/**
 * Demo — Sprint 2 GAIK feedback T9 / T9b / T8.
 *
 * - T9  (#33/#81): Blueprint tab as a readable form, not raw JSON.
 * - T9b (#22): per-step component settings (key/value).
 * - T8  (#23): the business-language plan, now the Blueprint tab's read view.
 *
 *   WIZARD_API_URL= \
 *   PLAYWRIGHT_SLOW_MO=500 \
 *   npx playwright test e2e/demo-plan-settings-form-video.spec.ts --project=chromium --workers=1
 *
 * Video → e2e/videos/wizard-v2-plan-settings-form-demo-1080p.webm
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

test.describe("Wizard V2 Plan + settings + Blueprint form demo video", () => {
  test.skip(!!process.env.CI, "demo video — run locally with PLAYWRIGHT_SLOW_MO");

  test.beforeEach(async ({ request }) => {
    try {
      await resetMockSessions(request);
    } catch {
      /* API mode */
    }
  });

  test("readable Blueprint form, component settings, solution plan", async ({ page }) => {
    test.setTimeout(300_000);
    fs.mkdirSync(OUT_DIR, { recursive: true });
    const video = page.video();

    await loginAsDev(page);
    await page.waitForTimeout(900);

    // Seeded chatbot session already carries example RAG/generation settings.
    await page.goto("/sessions/ses_chatbot");
    await expect(
      page.getByRole("heading", { name: "Customer service chatbot", level: 1 }),
    ).toBeVisible();
    await page.waitForTimeout(1400);

    // --- T9: readable Blueprint form ---
    await openBlueprintEditor(page);
    await page.waitForTimeout(1600);

    await page.getByTestId("blueprint-field-goal").click();
    await page.waitForTimeout(1200);

    // Expand the RAG step to show its fields.
    await page.getByTestId("blueprint-step-1-toggle").click();
    await page.waitForTimeout(1600);

    // --- T9b: component settings, already seeded (top_k, similarity_threshold),
    // behind the step's "Tekniset asetukset" ---
    await page.getByTestId("blueprint-step-1-tech").click();
    await page.waitForTimeout(800);
    await page.getByTestId("blueprint-step-1-setting-0-value").click();
    await page.waitForTimeout(1000);
    await expect(page.getByTestId("blueprint-step-1-setting-0-key")).toHaveValue("top_k");
    await page.waitForTimeout(1000);

    // Add a third setting live, on camera.
    await page.getByTestId("blueprint-step-1-setting-add").click();
    await page.waitForTimeout(1000);
    const newKey = page.getByTestId("blueprint-step-1-setting-2-key");
    await newKey.fill("provider");
    await page.waitForTimeout(600);
    const newValue = page.getByTestId("blueprint-step-1-setting-2-value");
    await newValue.click();
    // The form saves by itself a moment after the edit.
    const patched = page.waitForResponse(
      (r) =>
        r.url().endsWith("/blueprint") &&
        r.request().method() === "PATCH" &&
        (r.request().postData() ?? "").includes("Azure AI Search"),
    );
    await newValue.fill("Azure AI Search");
    expect((await patched).status()).toBe(200);
    await expect(page.getByTestId("blueprint-save-status")).toHaveText("Tallennettu", {
      timeout: 15_000,
    });
    await page.waitForTimeout(1400);

    // Raw JSON escape hatch — settings are real blueprint fields, not UI-only.
    await page.getByTestId("blueprint-json-toggle").click();
    await page.waitForTimeout(1200);
    await expect(page.getByTestId("blueprint-json-editor")).toHaveValue(/"top_k"/);
    await page.waitForTimeout(1400);
    await page.getByTestId("blueprint-json-toggle").click();
    await page.waitForTimeout(800);

    await page.getByTestId("blueprint-step-1-toggle").click();
    await page.waitForTimeout(1800);

    // --- T8: the plan, the Blueprint tab's read view ("Valmis" leaves the form) ---
    await page.getByTestId("blueprint-done").click();
    await page.waitForTimeout(1800);
    await expect(page.getByTestId("solution-plan-view")).toBeVisible();
    // A step's component and settings are behind its disclosure.
    const ragStep = page.getByTestId("plan-step-1");
    await ragStep.getByText("Komponentti ja asetukset").click();
    await expect(ragStep.getByText("provider", { exact: true })).toBeVisible();
    await expect(ragStep.getByText("Azure AI Search")).toBeVisible();
    await page.waitForTimeout(1200);

    await page.getByTestId("plan-step-1").scrollIntoViewIfNeeded();
    await page.waitForTimeout(1600);
    await page.getByTestId("plan-step-3").scrollIntoViewIfNeeded();
    await page.waitForTimeout(1800);

    await page.close();
    const videoPath = await video?.path();
    if (videoPath && fs.existsSync(videoPath)) {
      const dest1080 = path.join(
        OUT_DIR,
        "wizard-v2-plan-settings-form-demo-1080p.webm",
      );
      const dest = path.join(OUT_DIR, "wizard-v2-plan-settings-form-demo.webm");
      fs.copyFileSync(videoPath, dest1080);
      fs.copyFileSync(videoPath, dest);
    }
  });
});
