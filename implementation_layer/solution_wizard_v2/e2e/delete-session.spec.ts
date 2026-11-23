import { test, expect, type Page } from "@playwright/test";
import { loginAsDev } from "./helpers/auth";
import { resetMockSessions } from "./helpers/mock";
import { hydrated } from "./helpers/session";

/**
 * A session's download and delete, behind the one button of its row in the
 * sidebar. Deleting still asks for the session's name first.
 */

// The delete is a server action: on a busy dev server it takes a few seconds.
const AFTER_ACTION = { timeout: 20_000 };

const cards = (page: Page) => page.getByTestId("session-card");
const row = (page: Page, title: string) =>
  page
    .getByTestId("sidebar")
    .locator("li")
    .filter({ has: cards(page).filter({ hasText: title }) });

/** Opens the menu of the session's row and returns the row. */
async function openMenu(page: Page, title: string) {
  const session = row(page, title);
  await session.getByTestId("session-actions").click();
  await expect(session.getByTestId("delete-session-open")).toBeVisible();
  return session;
}

test.describe.configure({ mode: "serial" });

test.describe("Deleting a session", () => {
  test.beforeEach(async ({ page, request }) => {
    await resetMockSessions(request);
    await loginAsDev(page);
    await hydrated(page);
  });

  test("needs the session's name, then removes it from the list", async ({ page }) => {
    const title = "UI basics (e2e fixture)";
    const before = await cards(page).count();
    const session = await openMenu(page, title);
    await session.getByTestId("delete-session-open").click();

    // The menu has made way for the question, which names the session.
    await expect(session.getByTestId("delete-session-open")).toBeHidden();
    const dialog = page.getByRole("dialog", { name: "Poista sessio pysyvästi" });
    await expect(dialog).toContainText(title);
    const confirm = page.getByTestId("delete-session-confirm");
    const typed = page.getByTestId("delete-session-confirmation");
    await expect(typed).toBeFocused();
    await expect(confirm).toBeDisabled();
    await typed.fill("something else");
    await expect(confirm).toBeDisabled();
    await typed.fill(title);
    await confirm.click();

    await expect(dialog).toBeHidden(AFTER_ACTION);
    await expect(cards(page).filter({ hasText: title })).toHaveCount(0);
    await expect(cards(page)).toHaveCount(before - 1);
    // Deleted from the start view, the user stays on it.
    await expect(page).toHaveURL(/\/$/);
    await expect(page.getByTestId("start-view")).toBeVisible();
    // The row's button went with the row: the focus stays in the sidebar.
    await expect(page.getByTestId("new-session")).toBeFocused();
  });

  test("cancel and Esc keep the session, and the focus goes back to its row", async ({ page }) => {
    const title = "UI basics (e2e fixture)";
    const before = await cards(page).count();
    const session = await openMenu(page, title);
    await session.getByTestId("delete-session-open").click();
    await page.getByRole("button", { name: "Peruuta" }).click();
    await expect(page.getByTestId("delete-session-confirm")).toBeHidden();
    await expect(cards(page)).toHaveCount(before);
    await expect(session.getByTestId("session-actions")).toBeFocused();

    await session.getByTestId("session-actions").click();
    await session.getByTestId("delete-session-open").click();
    await expect(page.getByTestId("delete-session-confirmation")).toBeFocused();
    await page.keyboard.press("Escape");
    await expect(page.getByTestId("delete-session-confirm")).toBeHidden();
    await expect(cards(page)).toHaveCount(before);
    await expect(session.getByTestId("session-actions")).toBeFocused();
  });

  test("deleting the session that is open leads to the start view", async ({ page }) => {
    const title = "UI basics (e2e fixture)";
    await page.goto("/sessions/ses_ui_basics");
    await hydrated(page);
    await expect(page.getByRole("heading", { level: 1 })).toHaveText(title);

    const session = await openMenu(page, title);
    await session.getByTestId("delete-session-open").click();
    await page.getByTestId("delete-session-confirmation").fill(title);
    await page.getByTestId("delete-session-confirm").click();

    await page.waitForURL("/", AFTER_ACTION);
    await expect(page.getByTestId("start-view")).toBeVisible();
    // The start view's field has the cursor, not the sidebar.
    await expect(page.getByTestId("start-view").locator('textarea[name="message"]')).toBeFocused();
    await expect(page.getByTestId("delete-session-confirm")).toHaveCount(0);
    await expect(cards(page).filter({ hasText: title })).toHaveCount(0);
    // The session is gone for good, not only from the list.
    const gone = await page.goto("/sessions/ses_ui_basics");
    expect(gone?.status()).toBe(404);
  });

  test("deleting another session leaves the open one as it is", async ({ page }) => {
    await page.goto("/sessions/ses_gate2_pending");
    await hydrated(page);
    const title = "UI basics (e2e fixture)";
    const session = await openMenu(page, title);
    await session.getByTestId("delete-session-open").click();
    await page.getByTestId("delete-session-confirmation").fill(title);
    await page.getByTestId("delete-session-confirm").click();

    await expect(cards(page).filter({ hasText: title })).toHaveCount(0, AFTER_ACTION);
    await expect(page).toHaveURL(/\/sessions\/ses_gate2_pending$/);
    await expect(page.getByRole("heading", { level: 1 })).toHaveText("Gate 2 — pending review (e2e fixture)");
    // The focus is not left on the page's body, from where Tab would leave the list.
    await expect(page.getByTestId("new-session")).toBeFocused();
  });
});

test.describe("A row's menu", () => {
  test.beforeEach(async ({ page, request }) => {
    await resetMockSessions(request);
    await loginAsDev(page);
    await hydrated(page);
  });

  test("each control's own name says what it does and to which session", async ({ page }) => {
    // A touch screen has no hover, and a screen reader reads the name.
    const title = "Customer service chatbot";
    const session = row(page, title);
    await expect(session.getByTestId("session-actions")).toHaveAccessibleName(`Toiminnot: ${title}`);
    await session.getByTestId("session-actions").click();
    await expect(session.getByTestId("rename-session")).toHaveText("Nimeä uudelleen");
    await expect(session.getByTestId("export-session")).toHaveText("Lataa ZIP");
    await expect(session.getByTestId("export-session")).toHaveAccessibleName(
      `Lataa session tiedot ZIP-tiedostona: ${title}`,
    );
    await expect(session.getByTestId("delete-session-open")).toHaveAccessibleName(`Poista: ${title}`);
  });

  test("offers the session's data as a download", async ({ page }) => {
    const session = row(page, "Customer service chatbot");
    await session.getByTestId("session-actions").click();
    await expect(session.getByTestId("export-session")).toHaveAttribute(
      "href",
      "/api/sessions/ses_chatbot/export",
    );
  });

  test("closes on Esc and on a press elsewhere, and the button shows on hover and on the open session", async ({
    page,
  }) => {
    const title = "Customer service chatbot";
    const session = row(page, title);
    const button = session.getByTestId("session-actions");
    // Out of sight until the row is pointed at or reached with the keyboard.
    await expect(button).toHaveCSS("opacity", "0");
    await session.hover();
    await expect(button).toHaveCSS("opacity", "1");

    await button.click();
    await expect(session.getByTestId("rename-session")).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(session.getByTestId("rename-session")).toBeHidden();
    await expect(button).toBeFocused();

    await button.click();
    await expect(session.getByTestId("rename-session")).toBeVisible();
    await page.getByTestId("start-view").click({ position: { x: 5, y: 5 } });
    await expect(session.getByTestId("rename-session")).toBeHidden();

    // The open session's row keeps its button in view.
    await cards(page).filter({ hasText: title }).click();
    await page.waitForURL(/\/sessions\/ses_chatbot$/);
    await page.getByRole("heading", { level: 1 }).hover();
    await expect(button).toHaveCSS("opacity", "1");
  });

  test("stays open while the chat scrolls under a reply, and closes when its own list scrolls", async ({
    page,
  }) => {
    await page.goto("/sessions/ses_gate2_pending");
    await hydrated(page);
    const session = row(page, "Customer service chatbot");
    await session.getByTestId("session-actions").click();
    const rename = session.getByTestId("rename-session");
    await expect(rename).toBeVisible();

    // The chat's log scrolls to its end with every word of a reply.
    const scroll = (selector: string) =>
      page.evaluate((target) => {
        document.querySelector(target)!.dispatchEvent(new Event("scroll"));
      }, selector);
    await scroll('[data-testid="chat-dock"] [role="log"]');
    await scroll("#main-content");
    await expect(rename).toBeVisible();

    // The list its row is in moved: the menu would point at another row.
    await scroll('[data-testid="sidebar"] nav');
    await expect(rename).toBeHidden();
  });
});
