import { test, expect } from "@playwright/test";
import { loginAsDev } from "./helpers/auth";
import { resetMockSessions } from "./helpers/mock";
import { openBpmnView } from "./helpers/workspace";

/**
 * The Workflow tab's editor shows a palette over the diagram. At bpmn-js's own size
 * (46 px entries, 94 px wide) it covered a third of the canvas, and a compact rule written
 * inside a CSS layer never applied, because bpmn-js's stylesheet is unlayered. This measures
 * the rendered palette, not the CSS text. The palette holds the two tools whose result a
 * save keeps (add a task, connect); see e2e/bpmn-editing.spec.ts for what they are.
 */
test.describe("BPMN editor palette", () => {
  test.beforeEach(async ({ request }) => {
    await resetMockSessions(request);
  });

  test("is compact and holds its two tools", async ({ page }) => {
    await loginAsDev(page);
    await page.goto("/sessions/ses_laskut");
    await page.getByRole("tab", { name: "Työnkulku" }).click();
    await openBpmnView(page);

    const palette = page.locator(".bpmn-editable .djs-palette");
    await expect(palette).toBeVisible({ timeout: 20_000 });

    const entries = palette.locator(".entry");
    await expect(entries).toHaveCount(2);
    const entry = await entries.first().boundingBox();
    expect(entry!.width).toBeLessThanOrEqual(32);

    const box = await palette.boundingBox();
    expect(box!.width).toBeLessThanOrEqual(40);
  });
});
