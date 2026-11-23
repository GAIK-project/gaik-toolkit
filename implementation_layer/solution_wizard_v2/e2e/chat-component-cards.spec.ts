import { test, expect, type Locator, type Page } from "@playwright/test";
import { loginAsDev } from "./helpers/auth";
import { resetMockSessions } from "./helpers/mock";

/**
 * A GAIK component named in the wizard's reply (lib/component-links.ts): the
 * name is a quiet inline control, and its card (name, one line, documentation
 * link) opens on hover, on keyboard focus and on a press. The reply is the
 * seeded one of ses_ui_basics (lib/mock-sessions.ts).
 */

const DOCS = "https://github.com/GAIK-project/gaik-toolkit/blob/main/implementation_layer/src/gaik/software_components/";

async function openChat(page: Page) {
  await loginAsDev(page);
  await page.goto("/sessions/ses_ui_basics");
  await expect(page.getByRole("log")).toBeVisible();
}

const nameOf = (page: Page, name: string) => page.getByRole("log").getByRole("button", { name, exact: true });
const cardOf = (name: Locator) => name.locator("xpath=..").getByTestId("component-card");

/** The card is all inside the window and does not cover its name. */
async function expectPlaced(page: Page, name: Locator) {
  const card = (await cardOf(name).boundingBox())!;
  const at = (await name.boundingBox())!;
  const view = page.viewportSize()!;
  expect(card.x).toBeGreaterThanOrEqual(0);
  expect(card.x + card.width).toBeLessThanOrEqual(view.width);
  expect(card.y).toBeGreaterThanOrEqual(0);
  expect(card.y + card.height).toBeLessThanOrEqual(view.height);
  const below = card.y >= at.y + at.height - 1;
  const above = card.y + card.height <= at.y + 1;
  expect(below || above).toBe(true);
}

test.describe("component names in a reply", () => {
  test.beforeEach(async ({ request }) => {
    await resetMockSessions(request);
  });

  test("the first mention of a component is a control; the card opens on hover", async ({ page }) => {
    await openChat(page);
    const log = page.getByRole("log");
    // Named twice in the reply, linked once; a name in inline code and one in a table too.
    await expect(log.getByTestId("component-name")).toHaveText(["VisionExtractor", "SchemaGenerator", "SourceTracing"]);

    const name = nameOf(page, "VisionExtractor");
    const card = cardOf(name);
    await expect(card).toBeHidden();
    await name.hover();
    await expect(card).toBeVisible();
    await expect(card).toContainText("VisionExtractor");
    await expect(card).toContainText("Ottaa: PDF, kuva, dokumentti. Tuottaa: jäsennelty data.");
    const docs = card.getByRole("link", { name: "Dokumentaatio" });
    await expect(docs).toHaveAttribute("href", `${DOCS}vision_extractor/README.md`);
    await expect(docs).toHaveAttribute("target", "_blank");
    await expect(docs).toHaveAttribute("rel", /noopener/);
    await expectPlaced(page, name);

    // The pointer can travel from the name to the link without the card closing.
    await docs.hover();
    await expect(card).toBeVisible();
    await page.getByTestId("chat-ai-notice").hover();
    await expect(card).toBeHidden();
  });

  test("keyboard: focus opens the card, Tab reaches its link, Esc closes it", async ({ page }) => {
    await openChat(page);
    const name = nameOf(page, "VisionExtractor");
    const card = cardOf(name);
    // The name is described by the card's line.
    const described = await name.getAttribute("aria-describedby");
    await expect(page.locator(`[id="${described}"]`)).toHaveText(/Ottaa: PDF/);

    // Arrive with the keyboard, as Tab does.
    await name.evaluate((el: HTMLElement) => el.focus({ focusVisible: true } as FocusOptions));
    await expect(card).toBeVisible();
    await page.keyboard.press("Tab");
    await expect(card.getByRole("link", { name: "Dokumentaatio" })).toBeFocused();
    await expect(card).toBeVisible();

    await page.keyboard.press("Escape");
    await expect(card).toBeHidden();
    await expect(name).toBeFocused();

    // Leaving and coming back opens it again.
    await page.keyboard.press("Tab");
    await page.keyboard.press("Shift+Tab");
    await expect(name).toBeFocused();
    await expect(card).toBeVisible();
  });

  test("a press opens the card and keeps it open until a press elsewhere", async ({ page }) => {
    await openChat(page);
    const name = nameOf(page, "SchemaGenerator");
    const card = cardOf(name);
    await name.click();
    await page.mouse.move(0, 0);
    await expect(card).toBeVisible();
    await expect(card).toContainText("Ottaa: teksti. Tuottaa: jäsennelty data.");

    // Another component's name closes this one and opens its own.
    const other = nameOf(page, "VisionExtractor");
    await other.click();
    await page.mouse.move(0, 0);
    await expect(card).toBeHidden();
    await expect(cardOf(other)).toBeVisible();

    await page.getByTestId("chat-ai-notice").click();
    await expect(cardOf(other)).toBeHidden();
  });

  test("a card in a table that scrolls sideways is not cut off", async ({ page }) => {
    await openChat(page);
    const name = nameOf(page, "SourceTracing");
    await name.scrollIntoViewIfNeeded();
    await name.hover();
    const card = cardOf(name);
    await expect(card).toBeVisible();
    await expectPlaced(page, name);
    // All of the card can be pressed: nothing clips it.
    const docs = card.getByRole("link", { name: "Dokumentaatio" });
    const box = (await docs.boundingBox())!;
    const top = await page.evaluate(
      ([x, y]) => document.elementFromPoint(x, y)?.closest("a")?.className ?? "",
      [box.x + box.width / 2, box.y + box.height / 2],
    );
    expect(top).toBe("cmp-card-docs");
  });

  test("with reduced motion the card appears without moving", async ({ page }) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    await openChat(page);
    const name = nameOf(page, "VisionExtractor");
    await name.hover();
    const animation = await cardOf(name)
      .locator(".cmp-card-box")
      .evaluate((el) => getComputedStyle(el).animationName);
    expect(animation).toBe("none");
  });
});

test.describe("component names on a phone", () => {
  test.use({ viewport: { width: 390, height: 844 }, hasTouch: true });

  test.beforeEach(async ({ request }) => {
    await resetMockSessions(request);
  });

  test("a tap opens the card inside the screen; a tap elsewhere closes it", async ({ page }) => {
    await loginAsDev(page);
    await page.goto("/sessions/ses_ui_basics");
    const name = page.getByRole("button", { name: "SourceTracing", exact: true });
    // On a phone the chat is a sheet, closed at first.
    const dock = page.getByTestId("chat-dock");
    await expect(dock).toHaveAttribute("data-chat-open", "false");
    await page.getByRole("button", { name: "Keskustelu", exact: true }).click();
    await expect(dock).toHaveAttribute("data-chat-open", "true");
    await name.scrollIntoViewIfNeeded();
    const card = cardOf(name);
    await expect(card).toBeHidden();
    await name.tap();
    await expect(card).toBeVisible();
    await expectPlaced(page, name);
    await expect(card.getByRole("link", { name: "Dokumentaatio" })).toBeVisible();

    await page.getByTestId("chat-ai-notice").tap();
    await expect(card).toBeHidden();
  });
});
