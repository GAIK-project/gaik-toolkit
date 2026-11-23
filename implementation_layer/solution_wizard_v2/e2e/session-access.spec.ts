import { test, expect } from "@playwright/test";
import { loginAsDev } from "./helpers/auth";
import { createSession } from "./helpers/session";

test.describe("Session list and access", () => {
  test("a new session opens under its name and is listed in the sidebar", async ({ page }) => {
    await loginAsDev(page);

    await expect(page.getByRole("navigation", { name: "Sessiot" })).toBeVisible();

    const title = `E2E sessio ${Date.now()}`;
    await createSession(page, title);
    await expect(page.getByRole("heading", { name: title, level: 1 })).toBeVisible();
    await expect(page.getByTestId("session-card").filter({ hasText: title })).toHaveAttribute(
      "aria-current",
      "page",
    );
  });

  test("returns not found for unknown session id", async ({ page }) => {
    await loginAsDev(page);
    const response = await page.goto("/sessions/ses_nonexistent_e2e");
    expect(response?.status()).toBe(404);
    // Said beside the sidebar, where the user's own sessions still are.
    await expect(page.getByRole("heading", { name: "Sessiota ei löytynyt.", level: 1 })).toBeVisible();
    await expect(page.getByTestId("session-card").first()).toBeVisible();
  });

  test("a session cannot be created without signing in", async ({ request }) => {
    const res = await request.post("/api/sessions", { data: { title: "Ei kirjautumista" }, maxRedirects: 0 });
    expect(res.status()).not.toBe(201);
    expect([307, 401]).toContain(res.status());
  });

  test("seeded chatbot session is reachable for dev user", async ({ page }) => {
    await loginAsDev(page);
    // The card, not the download link beside it that also names the session.
    await page.getByTestId("session-card").filter({ hasText: "Customer service chatbot" }).click();
    await expect(page.getByRole("heading", { name: "Customer service chatbot", level: 1 })).toBeVisible();
  });
});
