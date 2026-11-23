import { test, expect } from "@playwright/test";
import { loginAsDev, openAccountMenu } from "./helpers/auth";
import { setMockSessionStep } from "./helpers/dev-step";
import { resetMockSessions } from "./helpers/mock";
import { createSession } from "./helpers/session";

// A step action is a server action: on a busy dev server it takes a few seconds.
const AFTER_ACTION = { timeout: 20_000 };

/**
 * Cross-cutting UI behaviour that had no e2e coverage at all: locale
 * switching, that the steps have no "Edellinen" (previous) or "Seuraava vaihe"
 * (next) button, the Specification step, markdown rendering in assistant chat
 * messages, and the sign-in page saying the wizard is an AI assistant.
 */
test.describe("UI basics", () => {
  test.beforeEach(async ({ request }) => {
    await resetMockSessions(request);
  });

  test("the sign-in page says the wizard is an AI assistant", async ({ page }) => {
    await page.goto("/login");
    await expect(page.getByTestId("login-ai-notice")).toHaveText(
      "Wizard on tekoälyavustaja: sen vastaukset ja tuottamat luonnokset ovat tekoälyn tuottamia.",
    );
  });

  test("the workspace says its tabs show AI output", async ({ page }) => {
    await loginAsDev(page);
    await page.goto("/sessions/ses_ui_basics");
    await expect(page.getByTestId("workspace-ai-mark")).toHaveText(
      "Ratkaisun, kaavion ja paketin on tuottanut tekoäly. Tarkista ne ennen käyttöä.",
    );
  });

  test("locale switcher changes the visible language", async ({ page }) => {
    await loginAsDev(page);
    await expect(page.getByRole("navigation", { name: "Sessiot" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Mitä haluat ratkaista?" })).toBeVisible();

    // Scoped by the LocaleSwitcher form's own button value — "EN"/"FI" role
    // lookups are ambiguous against Next.js's dev-tools button in dev mode.
    // The choice is in the menu of the account row at the sidebar's foot.
    await (await openAccountMenu(page)).locator('button[name="locale"][value="en"]').click();
    await expect(page.getByRole("navigation", { name: "Sessions" })).toBeVisible();
    await expect(page.getByRole("link", { name: "New session" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "What do you want to solve?" })).toBeVisible();

    // Switching back is symmetric.
    await (await openAccountMenu(page)).locator('button[name="locale"][value="fi"]').click();
    await expect(page.getByRole("navigation", { name: "Sessiot" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Uusi sessio" })).toBeVisible();
  });

  test("between gates there are no step buttons, and the page follows the session's step", async ({
    page,
    request,
    baseURL,
  }) => {
    await loginAsDev(page);
    await page.goto("/sessions/ses_ui_basics");

    await expect(page.getByText("VAIHE 6 / 13")).toBeVisible();
    await expect(page.getByTestId("workspace-phase")).toHaveText("Komponenttivalinta");
    // What to do now is one line under the title.
    await expect(page.getByTestId("now-line")).toContainText(
      "Wizard valitsee kullekin vaiheelle komponentin ja perustelee valinnan chatissa.",
    );

    // The steps between gates carry no decision of the user's: the wizard
    // works through them in the chat, and the step follows what it writes.
    await expect(page.getByRole("button", { name: "Edellinen" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Seuraava vaihe" })).toHaveCount(0);

    // The session has moved on, the way the wizard's files move it.
    await setMockSessionStep(request, baseURL as string, "ses_ui_basics", 7);
    await page.reload();

    await expect(page.getByText("VAIHE 7 / 13")).toBeVisible(AFTER_ACTION);
    await expect(page.getByTestId("workspace-phase")).toHaveText("Blueprint-kokoaminen");
    await expect(page.getByRole("button", { name: "Edellinen" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Seuraava vaihe" })).toHaveCount(0);
  });

  test("the first step has neither a previous nor a next button", async ({ page }) => {
    await loginAsDev(page);
    const title = `regress-guard ${Date.now()}`;
    await createSession(page, title);

    await expect(page.getByText("VAIHE 1 / 13")).toBeVisible();
    // Gathering moves on when the wizard has the requirements, so there is no
    // "next step" to press, and nothing before the first step.
    await expect(page.getByRole("button", { name: "Edellinen" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Seuraava vaihe" })).toHaveCount(0);
  });

  test("Gate 1 and the steps before it have no previous button", async ({ page, request, baseURL }) => {
    await loginAsDev(page);
    await page.goto("/sessions/ses_gate1_blocked");
    await expect(page.getByTestId("workspace-phase")).toHaveText("Gate 1: vaatimukset");
    // The gate's bar asks for changes or approves; a change goes through the chat.
    await expect(page.getByRole("button", { name: "Edellinen" })).toHaveCount(0);

    await setMockSessionStep(request, baseURL as string, "ses_gate1_blocked", 3);
    await page.reload();
    await expect(page.getByText("VAIHE 3 / 13")).toBeVisible();
    await expect(page.getByRole("heading", { name: "Poimittavat kentät" })).toBeVisible();
    // Before Gate 1 too a change goes through the chat, not a step back.
    await expect(page.getByRole("button", { name: "Edellinen" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Seuraava vaihe" })).toHaveCount(0);
  });

  test("assistant messages render markdown as HTML, not raw syntax", async ({ page }) => {
    await loginAsDev(page);
    await page.goto("/sessions/ses_ui_basics");

    const chatLog = page.getByRole("log");
    // Bold, list item, and inline code all present as real elements.
    await expect(chatLog.locator("strong", { hasText: "Component A" })).toBeVisible();
    await expect(chatLog.locator("li", { hasText: "Component B" })).toBeVisible();
    await expect(chatLog.locator("code", { hasText: "lookup(id)" })).toBeVisible();

    // The raw markdown characters must not leak through as visible text.
    await expect(chatLog.getByText("**Component A**")).toHaveCount(0);
  });
});
