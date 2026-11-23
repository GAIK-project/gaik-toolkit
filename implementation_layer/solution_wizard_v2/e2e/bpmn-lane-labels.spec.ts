import { test, expect } from "@playwright/test";
import { loginAsDev } from "./helpers/auth";
import { resetMockSessions } from "./helpers/mock";
import { openBpmnView } from "./helpers/workspace";

/**
 * The Workflow tab's editor shows each lane's name. A rule written for the read-only viewer,
 * which draws lane names as overlay captions, hid bpmn-js's own lane text in the editor too,
 * and there the lanes had no names at all. This checks the rendered visibility, not the CSS.
 */
test.describe("BPMN editor lanes", () => {
  test.beforeEach(async ({ request }) => {
    await resetMockSessions(request);
  });

  test("show their names", async ({ page }) => {
    await loginAsDev(page);
    await page.goto("/sessions/ses_laskut");
    await page.getByRole("tab", { name: "Työnkulku" }).click();
    await openBpmnView(page);

    const lanes = page.locator('.bpmn-editable [data-element-id^="Lane_"] > .djs-visual text');
    await expect(lanes.first()).toBeAttached({ timeout: 20_000 });
    expect(await lanes.count()).toBeGreaterThanOrEqual(2);

    for (const lane of await lanes.all()) {
      await expect(lane).toBeVisible();
      expect((await lane.textContent())?.trim()).not.toBe("");
    }
  });
});
