import { test, expect, type Page } from "@playwright/test";
import { loginAsDev } from "./helpers/auth";
import { resetMockSessions } from "./helpers/mock";
import { openBpmnView, selectWorkspaceTab, setChatOpen } from "./helpers/workspace";

/**
 * What the Workflow tab's BPMN editor shows around the diagram: the minimap
 * over the canvas, bpmn.io's mark (bpmn-js's licence asks for it), and the
 * large view ("Suurenna kaavio"), which asks the browser for full screen and
 * lays itself over the window when the browser says no.
 */

const canvas = (page: Page) => page.locator(".bpmn-editable .djs-container");

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

test.describe("BPMN editor view", () => {
  test.beforeEach(async ({ request }) => {
    await resetMockSessions(request);
  });

  test("the editor shows a minimap, a visible bpmn.io mark and a full-screen mode", async ({ page }) => {
    await openEditor(page);

    // The minimap is part of the canvas, open, and named for a screen reader.
    const minimap = page.locator(".bpmn-editable .djs-minimap");
    await expect(minimap).toBeVisible();
    await expect(minimap).toHaveClass(/open/);
    await expect(minimap).toHaveAttribute("aria-label", "Kaavion pienoiskartta");

    // bpmn.io's mark is on the canvas, not hidden.
    await expect(page.locator(".bpmn-editable .bjs-powered-by")).toBeVisible();

    // The large view covers the window, by the browser's full screen or by itself,
    // and the canvas takes nearly all of it: its width less a margin, its height less
    // the AI notice above and the editing note below.
    const viewport = page.viewportSize()!;
    const box = page.getByTestId("flow-diagram-box");
    const beside = (await canvas(page).boundingBox())!;
    const controls = page.getByTestId("bpmn-zoom-controls");
    await expect(controls.getByRole("button")).toHaveCount(4);
    await controls.getByRole("button", { name: "Suurenna kaavio" }).click();
    await expect(box).toHaveAttribute("data-full-view", "true");
    await expect.poll(async () => Math.round((await box.boundingBox())!.width)).toBe(viewport.width);
    expect(Math.round((await box.boundingBox())!.height)).toBe(viewport.height);
    const large = (await canvas(page).boundingBox())!;
    expect(large.width).toBeGreaterThan(viewport.width - 40);
    expect(large.height).toBeGreaterThan(viewport.height * 0.8);
    expect(large.height).toBeGreaterThan(beside.height);
    await expect(minimap).toBeVisible();

    // Escape puts the page back, out of the browser's full screen too.
    await page.keyboard.press("Escape");
    await expect(box).toHaveAttribute("data-full-view", "false");
    await expect.poll(() => page.evaluate(() => document.fullscreenElement === null)).toBe(true);
    await expect.poll(async () => Math.round((await canvas(page).boundingBox())!.width)).toBe(Math.round(beside.width));
  });

  test("the large view stays open when the browser leaves full screen by itself", async ({ page }) => {
    await openEditor(page);
    const viewport = page.viewportSize()!;
    const box = page.getByTestId("flow-diagram-box");
    await page.getByTestId("bpmn-zoom-controls").getByRole("button", { name: "Suurenna kaavio" }).click();
    await expect(box).toHaveAttribute("data-full-view", "true");
    // Headless Chromium grants full screen: the page is in it.
    await expect.poll(() => page.evaluate(() => document.fullscreenElement !== null)).toBe(true);

    // The browser's own Esc or controls: the page cannot tell it from an Esc that cancels
    // a rename, so the large view stays, as the box laid over the window.
    await page.evaluate(() => document.fullscreenElement && document.exitFullscreen());
    await expect.poll(() => page.evaluate(() => document.fullscreenElement === null)).toBe(true);
    await page.evaluate(() => new Promise((done) => requestAnimationFrame(() => requestAnimationFrame(done))));
    await expect(box).toHaveAttribute("data-full-view", "true");
    await expect.poll(async () => Math.round((await box.boundingBox())!.width)).toBe(viewport.width);
    expect(Math.round((await box.boundingBox())!.height)).toBe(viewport.height);

    // The button still closes it.
    await page.getByTestId("bpmn-zoom-controls").getByRole("button", { name: "Pienennä kaavio" }).click();
    await expect(box).toHaveAttribute("data-full-view", "false");
  });
});
