import { test, expect } from "@playwright/test";
import { loginAsDev } from "./helpers/auth";
import { resetMockSessions } from "./helpers/mock";
import { selectWorkspaceTab } from "./helpers/workspace";

/**
 * The Blueprint tab's two views on the mock store: "Työnkulun vaiheet", the
 * plan and its form as before, and "Koko blueprint", which needs wizard_api
 * and says so here, with no editor. e2e/full-blueprint-stack.spec.ts covers
 * the full blueprint itself: the download, the advanced editor and its saves.
 */

test.describe("Full blueprint (mock)", () => {
  test.beforeEach(async ({ request }) => {
    await resetMockSessions(request);
  });

  test("the Blueprint tab opens on the workflow steps; the full blueprint says it needs wizard_api", async ({
    page,
  }) => {
    await loginAsDev(page);
    await page.goto("/sessions/ses_ui_basics");
    await selectWorkspaceTab(page, /Blueprint/);

    const steps = page.getByTestId("blueprint-view-steps");
    const full = page.getByTestId("blueprint-view-full");
    await expect(steps).toHaveText("Työnkulun vaiheet");
    await expect(full).toHaveText("Koko blueprint");
    await expect(steps).toHaveAttribute("aria-pressed", "true");
    await expect(page.getByTestId("blueprint-edit")).toBeVisible();

    const read = page.waitForResponse(
      (r) => r.url().endsWith("/blueprint/full") && r.request().method() === "GET",
    );
    await full.click();
    expect((await read).status()).toBe(503);
    await expect(full).toHaveAttribute("aria-pressed", "true");
    const note = page.getByTestId("full-blueprint-note");
    await expect(note).toHaveAttribute("data-kind", "needsApi");
    await expect(note).toContainText("wizardin palvelin");
    await expect(page.getByTestId("full-blueprint-advanced")).toHaveCount(0);
    await expect(page.getByTestId("full-blueprint-download")).toHaveCount(0);
    await expect(page.getByTestId("code-editor")).toHaveCount(0);
    await expect(page.getByTestId("blueprint-edit")).toBeHidden();

    // Back on the steps: the plan and its "Muokkaa" as before.
    await steps.click();
    await expect(page.getByTestId("blueprint-edit")).toBeVisible();
    await expect(page.getByTestId("full-blueprint-view")).toHaveCount(0);
  });

  test("the views are named in English too", async ({ page, context }) => {
    await loginAsDev(page);
    const url = new URL(page.url());
    await context.addCookies([{ name: "gaik_locale", value: "en", domain: url.hostname, path: "/" }]);
    await page.goto("/sessions/ses_ui_basics");
    await selectWorkspaceTab(page, /Blueprint/);
    await expect(page.getByTestId("blueprint-view-steps")).toHaveText("Workflow steps");
    await page.getByTestId("blueprint-view-full").click();
    await expect(page.getByTestId("blueprint-view-full")).toHaveText("Full blueprint");
    await expect(page.getByTestId("full-blueprint-note")).toContainText("wizard's server");
  });
});
