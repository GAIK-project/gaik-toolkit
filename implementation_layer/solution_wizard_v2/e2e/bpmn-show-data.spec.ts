import { test, expect, type Page } from "@playwright/test";
import { loginAsDev } from "./helpers/auth";
import { resetMockSessions } from "./helpers/mock";
import { openBpmnView, selectWorkspaceTab, setChatOpen } from "./helpers/workspace";

/**
 * "Näytä data" on the Workflow tab's BPMN canvas: off, the diagram is drawn
 * without data objects, so it is smaller. The choice is kept in this browser
 * (localStorage gaik.bpmn.showData) and the diagram comes from the server with
 * ?data_objects=0.
 */

const dataObjects = (page: Page) => page.locator(".bpmn-editable .djs-element[data-element-id^='DataObjectRef_']");

async function openEditor(page: Page) {
  await loginAsDev(page);
  await page.goto("/sessions/ses_laskut");
  await setChatOpen(page, false);
  await selectWorkspaceTab(page, "Työnkulku");
  await openBpmnView(page);
  await expect(page.locator('.bpmn-editable [data-element-id="Activity_classify"]')).toBeVisible({
    timeout: 30_000,
  });
  await expect(page.locator(".bpmn-editable")).toHaveAttribute("aria-busy", "false");
}

test.describe("BPMN Show data", () => {
  test.beforeEach(async ({ request }) => {
    await resetMockSessions(request);
  });

  test("hides the data objects, keeps the choice and shows them again", async ({ page }) => {
    await openEditor(page);
    const toggle = page.getByTestId("bpmn-show-data");
    await expect(toggle).toHaveText("Näytä data");
    await expect(toggle).toHaveAttribute("aria-pressed", "true");
    await expect(dataObjects(page).first()).toBeVisible();

    const compact = page.waitForRequest((r) => r.url().includes("/bpmn?data_objects=0"));
    await toggle.click();
    await compact;
    await expect(toggle).toHaveAttribute("aria-pressed", "false");
    await expect(dataObjects(page)).toHaveCount(0);
    await expect(page.locator('.bpmn-editable [data-element-id="Activity_classify"]')).toBeVisible();
    expect(await page.evaluate(() => localStorage.getItem("gaik.bpmn.showData"))).toBe("0");

    // The choice holds over a reload.
    await openEditor(page);
    await expect(page.getByTestId("bpmn-show-data")).toHaveAttribute("aria-pressed", "false");
    await expect(dataObjects(page)).toHaveCount(0);

    await page.getByTestId("bpmn-show-data").click();
    await expect(page.getByTestId("bpmn-show-data")).toHaveAttribute("aria-pressed", "true");
    await expect(dataObjects(page).first()).toBeVisible();
    expect(await page.evaluate(() => localStorage.getItem("gaik.bpmn.showData"))).toBe("1");
  });
});
