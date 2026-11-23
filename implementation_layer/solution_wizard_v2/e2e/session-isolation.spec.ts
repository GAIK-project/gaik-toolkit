import { test, expect } from "@playwright/test";
import { setMockSessionStep } from "./helpers/dev-step";
import { DEV_USERS, loginAsDev, signOutDev } from "./helpers/auth";
import { resetMockSessions } from "./helpers/mock";
import { createSession } from "./helpers/session";

/**
 * US-S1-01: per-user session list and access control (dev auth, mock or API store).
 */
test.describe("US-S1-01 session isolation", () => {
  test.beforeEach(async ({ request }) => {
    await resetMockSessions(request);
  });

  test("each user sees only their own sessions", async ({ page }) => {
    const user1Title = `User1 private ${Date.now()}`;
    const user2Title = `User2 private ${Date.now()}`;

    await loginAsDev(page, DEV_USERS.primary);
    await createSession(page, user1Title);
    const user1Url = page.url();

    await signOutDev(page);
    await loginAsDev(page, DEV_USERS.secondary);

    await expect(page.getByRole("navigation", { name: "Sessiot" })).toBeVisible();
    await expect(page.getByTestId("user-email")).toHaveText(DEV_USERS.secondary.email);
    await expect(page.getByRole("link", { name: user1Title })).toHaveCount(0);

    const blocked = await page.goto(user1Url);
    expect(blocked?.status()).toBe(404);

    await page.goto("/");
    await createSession(page, user2Title);

    await signOutDev(page);
    await loginAsDev(page, DEV_USERS.primary);

    // The card, not the download link beside it that also names the session.
    await expect(page.getByTestId("session-card").filter({ hasText: user1Title })).toBeVisible();
    await expect(page.getByRole("link", { name: user2Title })).toHaveCount(0);
  });

  test("secondary user has no seeded sessions from primary owner", async ({ page }) => {
    await loginAsDev(page, DEV_USERS.secondary);
    await expect(page.getByRole("link", { name: "Customer service chatbot" })).toHaveCount(0);
  });

  test("session progress survives reload for the owning user", async ({
    page,
    request,
    baseURL,
  }) => {
    const title = `Persist ${Date.now()}`;
    await loginAsDev(page, DEV_USERS.primary);
    await createSession(page, title);
    await expect(page.getByText("VAIHE 1 / 13")).toBeVisible();

    // Gathering does not advance from the UI: the agent moves the session on
    // once it has the requirements, so the step has no "next step" button.
    await expect(page.getByRole("button", { name: "Seuraava vaihe" })).toHaveCount(0);

    // Progress the session the way the agent would, then check it survives.
    const sessionId = new URL(page.url()).pathname.split("/").pop() as string;
    await setMockSessionStep(request, baseURL as string, sessionId, 2);
    await page.reload();
    await expect(page.getByText("VAIHE 2 / 13")).toBeVisible();

    await page.reload();
    await expect(page.getByText("VAIHE 2 / 13")).toBeVisible();
    await expect(page.getByRole("heading", { name: title, level: 1 })).toBeVisible();
  });
});
