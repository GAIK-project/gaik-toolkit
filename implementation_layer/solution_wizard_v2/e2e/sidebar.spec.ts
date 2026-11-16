import { test, expect, type Page } from "@playwright/test";
import { DEV_USERS, loginAsDev, openAccountMenu, signOutDev } from "./helpers/auth";
import { resetMockSessions } from "./helpers/mock";
import { forgetMotion, motion, recordMotion } from "./helpers/motion";
import { createSession, hydrated } from "./helpers/session";

/**
 * The shell's sidebar: the user's sessions beside every page, a new session,
 * and the signed-in user. It took over what the session list page did (the
 * rows with their gates, the search, download and delete) and what the top
 * bar did (the language, the privacy notice, signing out): those are in the
 * menu of the account row at its foot.
 */

// A sidebar action is a server action: on a busy dev server it takes a few seconds.
const AFTER_ACTION = { timeout: 20_000 };

const sidebar = (page: Page) => page.getByTestId("sidebar");
const cards = (page: Page) => page.getByTestId("session-card");
const card = (page: Page, title: string) => cards(page).filter({ hasText: title });
/** The row of a session: its link and the menu button beside it. */
const row = (page: Page, title: string) =>
  sidebar(page).locator("li").filter({ has: card(page, title) });
const noSidewaysScroll = (page: Page) =>
  page.evaluate(() => document.scrollingElement!.scrollWidth - window.innerWidth);

test.beforeEach(async ({ request }) => {
  await resetMockSessions(request);
});

test.describe("the sidebar on a desktop", () => {
  test("lists the sessions by day, each with its gates and where it stands", async ({ page }) => {
    await loginAsDev(page);
    const list = sidebar(page).getByRole("navigation", { name: "Sessiot" });
    await expect(list.getByRole("heading", { name: "Tänään" })).toBeVisible();
    expect(await cards(page).count()).toBeGreaterThan(5);

    // A session waiting at a gate says so; one between gates names its phase.
    // One short text per row, with the step count for a screen reader.
    const atGate = card(page, "Gate 2 — pending review");
    await expect(atGate).toContainText("Odottaa hyväksyntää");
    await expect(atGate).toContainText("Vaihe 9/13");
    await expect(atGate).not.toContainText("Gate 2: ratkaisun rakenne");
    const between = card(page, "UI basics");
    await expect(between).toContainText("Komponenttivalinta");
    await expect(between).not.toContainText("Odottaa hyväksyntää");
    await expect(list).not.toContainText(/blueprint v\d/i);
    // The link is named by the session's title alone; the rest of the row
    // describes it.
    await expect(atGate).toHaveAccessibleName("Gate 2 — pending review (e2e fixture)");
    await expect(atGate).toHaveAccessibleDescription(/Vaihe 9\/13.*Odottaa hyväksyntää/);

    // A row is as wide as the list, and its text stays inside it.
    const listBox = (await list.boundingBox())!;
    for (const one of await cards(page).all()) {
      const box = (await one.boundingBox())!;
      expect(box.x).toBeGreaterThanOrEqual(listBox.x);
      expect(box.x + box.width).toBeLessThanOrEqual(listBox.x + listBox.width);
    }
    expect(await noSidewaysScroll(page)).toBeLessThanOrEqual(0);
  });

  test("opens a session from its row and marks it as the open one", async ({ page }) => {
    await loginAsDev(page);
    await expect(sidebar(page).locator('[aria-current="page"]')).toHaveCount(0);

    await card(page, "UI basics").click();
    await page.waitForURL(/\/sessions\/ses_ui_basics$/);
    await expect(page.getByRole("heading", { level: 1 })).toHaveText("UI basics (e2e fixture)");
    await expect(card(page, "UI basics")).toHaveAttribute("aria-current", "page");
    await expect(sidebar(page).locator('[aria-current="page"]')).toHaveCount(1);

    // Another session: the mark moves, and the page is the other session's.
    await card(page, "Gate 2 — pending review").click();
    await page.waitForURL(/\/sessions\/ses_gate2_pending$/);
    await expect(page.getByRole("heading", { level: 1 })).toHaveText("Gate 2 — pending review (e2e fixture)");
    await expect(card(page, "Gate 2 — pending review")).toHaveAttribute("aria-current", "page");
    await expect(card(page, "UI basics")).not.toHaveAttribute("aria-current", "page");

    // One landmark of each kind, each with its own name.
    await expect(page.locator("#main-content")).toHaveCount(1);
    await expect(page.getByRole("complementary", { name: "Sivupalkki" })).toBeVisible();
    await expect(page.getByRole("navigation", { name: "Sessiot" })).toBeVisible();
    await expect(page.getByRole("navigation", { name: "Vaiheet" })).toBeVisible();
  });

  test("a name cut short by its row or the bar is read in full from its title", async ({ page }) => {
    await loginAsDev(page);
    const long = "Asiakaspalvelun yhteydenottojen luokittelu ja reititys oikealle tiimille";
    await createSession(page, long);
    const name = (title: string) => card(page, title).locator(".session-row-title");
    await expect(name(long)).toHaveAttribute("title", long);
    expect(await name(long).evaluate((el) => el.scrollWidth > el.clientWidth)).toBe(true);
    const heading = page.getByRole("heading", { level: 1 });
    await expect(heading).toHaveText(long);
    await expect(heading).toHaveAttribute("title", long);

    // A row keeps room for its actions button only while the button is there.
    await heading.hover();
    await expect(name(long)).toHaveCSS("padding-right", "32px");
    await expect(name("UI basics")).toHaveCSS("padding-right", "0px");
    await card(page, "UI basics").hover();
    await expect(name("UI basics")).toHaveCSS("padding-right", "32px");
  });

  test("the start view says the wizard's name once, and the sidebar's mark still leads home", async ({ page }) => {
    await loginAsDev(page);
    await hydrated(page);
    const home = sidebar(page).getByRole("link", { name: "GAIK Solution Wizard" });
    await expect(home).toBeVisible();
    await expect(page.getByRole("heading", { level: 1 })).toContainText("Solution Wizard");
    await expect(sidebar(page)).not.toContainText("Solution Wizard");

    // Beside a session the name is in the sidebar's head, and it leads back to the start.
    await card(page, "UI basics").click();
    await page.waitForURL(/\/sessions\/ses_ui_basics$/);
    await expect(home).toHaveText("Solution Wizard");
    await home.click();
    await page.waitForURL("/");
    await expect(page.getByTestId("start-view")).toBeVisible();
  });

  test("follows the open session: a reply moves it to the top of today", async ({ page }) => {
    await loginAsDev(page);
    await page.goto("/sessions/ses_chatbot");
    await hydrated(page);
    const open = card(page, "Customer service chatbot");
    await expect(open).toHaveAttribute("aria-current", "page");
    // Last touched days ago, it is far down the list.
    await expect(cards(page).first()).not.toContainText("Customer service chatbot");

    const field = page.locator('textarea[name="message"]');
    await field.fill("Lisää vaihe, joka tarkistaa vastauksen lähteet.");
    await field.press("Enter");
    await expect(
      page.locator('form:has(textarea[name="message"]) button[type="submit"]'),
    ).toBeEnabled({ timeout: 30_000 });

    // The page reads the session again after a reply, and the sidebar with it.
    await expect(cards(page).first()).toContainText("Customer service chatbot", AFTER_ACTION);
    await expect(cards(page).first()).toHaveAttribute("aria-current", "page");
    const today = sidebar(page).getByRole("region", { name: "Tänään" });
    await expect(today.getByTestId("session-card").first()).toContainText("Customer service chatbot");
  });

  test("a reply to the chat moves nothing in the sidebar, the session bar or the page", async ({ page }) => {
    await recordMotion(page);
    await loginAsDev(page);
    await page.goto("/sessions/ses_chatbot");
    await hydrated(page);
    // Opening the session is an action and has its own short arrival; let it end.
    await expect
      .poll(() => page.evaluate(() => document.getAnimations().length), AFTER_ACTION)
      .toBe(0);
    await forgetMotion(page);

    // Three messages in a row: after each reply the page reads the session,
    // and the sidebar with it, again.
    const field = page.locator('textarea[name="message"]');
    const submit = page.locator('form:has(textarea[name="message"]) button[type="submit"]');
    for (const text of ["Lisää lähteiden tarkistus.", "Entä englanninkieliset kysymykset?", "Kiitos."]) {
      await field.fill(text);
      await field.press("Enter");
      await expect(page.getByTestId("chat-message").filter({ hasText: text })).toHaveCount(1);
      await expect(submit).toBeEnabled({ timeout: 30_000 });
    }
    // The reply moved the session to the top of today: the list was read again.
    await expect(cards(page).first()).toContainText("Customer service chatbot", AFTER_ACTION);

    // Only the chat itself showed that the wizard was working.
    const outsideChat = (await motion(page)).filter((move) => !move.at.includes("chat-dock"));
    expect(outsideChat).toEqual([]);
    // And nothing is left running in the shell.
    const running = await page.evaluate(() => {
      const shell = ['[data-testid="sidebar"]', '[data-testid="session-bar"]'].map((part) =>
        document.querySelector(part),
      );
      return document.getAnimations().filter((animation) => {
        const target = (animation.effect as KeyframeEffect | null)?.target;
        return target && shell.some((part) => part?.contains(target));
      }).length;
    });
    expect(running).toBe(0);
  });

  test("folding the sidebar moves the page once, and not at all with reduced motion", async ({ page }) => {
    await recordMotion(page);
    await loginAsDev(page);
    await page.goto("/sessions/ses_ui_basics");
    await hydrated(page);
    await expect
      .poll(() => page.evaluate(() => document.getAnimations().length), AFTER_ACTION)
      .toBe(0);
    await forgetMotion(page);
    const toggle = page.getByTestId("sidebar-toggle");

    // The page glides the 212 px the column gave up, and the rail fades in.
    await toggle.click();
    await expect(toggle).toHaveAccessibleName("Avaa sivupalkki");
    const folded = (await motion(page)).filter((move) => move.kind === "script");
    expect(folded.map((move) => move.name)).toEqual([
      '[{"transform":"translateX(212px)"},{"transform":"none"}]',
      '[{"opacity":0},{"opacity":1}]',
    ]);

    await page.emulateMedia({ reducedMotion: "reduce" });
    await forgetMotion(page);
    await toggle.click();
    await expect(toggle).toHaveAccessibleName("Pienennä sivupalkki");
    expect((await motion(page)).filter((move) => move.kind === "script")).toEqual([]);
  });

  test("the search narrows the list at once, on any page, and leaves the address alone", async ({ page }) => {
    await loginAsDev(page);
    await page.goto("/sessions/ses_ui_basics");
    const all = await cards(page).count();

    const search = page.getByRole("searchbox", { name: "Hae sessioita" });
    await search.fill("gate 2");
    await expect(cards(page)).toHaveCount(1);
    await expect(cards(page)).toContainText("Gate 2 — pending review");
    await expect(page).toHaveURL(/\/sessions\/ses_ui_basics$/);

    // The search stays while the page beside it changes.
    await cards(page).click();
    await page.waitForURL(/\/sessions\/ses_gate2_pending$/);
    await expect(search).toHaveValue("gate 2");
    await expect(cards(page)).toHaveCount(1);

    // Nothing found: the search is said as it was typed, and one press clears it.
    await search.fill("$&");
    await expect(sidebar(page)).toContainText('Ei sessioita haulla "$&".');
    await sidebar(page).getByRole("button", { name: "Näytä kaikki" }).click();
    await expect(search).toHaveValue("");
    await expect(search).toBeFocused();
    await expect(cards(page)).toHaveCount(all);
  });

  test("a few sessions need no search field", async ({ page }) => {
    await loginAsDev(page, DEV_USERS.secondary);
    await expect(sidebar(page)).toContainText("Ei vielä sessioita.");
    await createSession(page, "Hakutesti");
    await expect(cards(page)).toHaveCount(1);
    await expect(page.getByRole("searchbox")).toHaveCount(0);
  });

  test("folds to a rail and stays folded over a reload", async ({ page }) => {
    await loginAsDev(page);
    await page.goto("/sessions/ses_ui_basics");
    await hydrated(page);
    const toggle = page.getByTestId("sidebar-toggle");
    const width = async () => Math.round((await sidebar(page).boundingBox())!.width);
    expect(await width()).toBe(264);
    await expect(toggle).toHaveAccessibleName("Pienennä sivupalkki");

    await toggle.click();
    expect(await width()).toBe(52);
    await expect(cards(page).first()).toBeHidden();
    // The pressed button went with the full column; its counterpart has the focus.
    await expect(toggle).toHaveAccessibleName("Avaa sivupalkki");
    await expect(toggle).toHaveAttribute("aria-expanded", "false");
    await expect(toggle).toBeFocused();
    // A new session is one press away on the rail too.
    await expect(sidebar(page).getByRole("link", { name: "Uusi sessio" })).toBeVisible();
    // And so is the account: the initial alone opens the same menu, which
    // says whose it is.
    const railAccount = sidebar(page).locator('[data-testid="account-menu"]:visible');
    await expect(railAccount).toHaveAccessibleName(`Käyttäjä: ${DEV_USERS.primary.email}`);
    await railAccount.click();
    const railMenu = sidebar(page).locator('[data-testid="account-menu-items"]:visible');
    await expect(railMenu).toContainText(DEV_USERS.primary.email);
    await expect(railMenu.locator('button[name="locale"]')).toHaveCount(2);
    await expect(railMenu.getByTestId("privacy-link")).toBeVisible();
    await expect(railMenu.getByRole("button", { name: "Kirjaudu ulos" })).toBeVisible();
    const railBox = (await railMenu.boundingBox())!;
    expect(railBox.x).toBeGreaterThanOrEqual(0);
    expect(railBox.y).toBeGreaterThanOrEqual(0);
    await page.keyboard.press("Escape");
    await expect(railMenu).toHaveCount(0);
    await expect(railAccount).toBeFocused();

    // The server renders the rail: no full column for a moment after a reload.
    await page.reload();
    expect(await width()).toBe(52);
    await expect(cards(page).first()).toBeHidden();

    await hydrated(page);
    await toggle.click();
    expect(await width()).toBe(264);
    await expect(cards(page).first()).toBeVisible();
    await expect(toggle).toBeFocused();
    await page.reload();
    expect(await width()).toBe(264);
  });

  test("renames a session from its row's menu: the row and the page's heading follow", async ({ page }) => {
    await loginAsDev(page);
    await page.goto("/sessions/ses_ui_basics");
    await hydrated(page);
    const old = "UI basics (e2e fixture)";

    await row(page, old).getByTestId("session-actions").click();
    await row(page, old).getByTestId("rename-session").click();
    const name = page.getByTestId("rename-session-input");
    await expect(name).toBeFocused();
    await expect(name).toHaveValue(old);
    await expect(name).toHaveAccessibleName("Session nimi");

    // Esc leaves the name as it was.
    await name.fill("Hylätty nimi");
    await name.press("Escape");
    await expect(name).toHaveCount(0);
    await expect(card(page, old)).toBeVisible();
    await expect(card(page, old)).toBeFocused();

    // Enter saves it.
    await row(page, old).getByTestId("session-actions").click();
    await row(page, old).getByTestId("rename-session").click();
    await name.fill("  Laskujen   luokittelu ");
    await name.press("Enter");
    await expect(card(page, "Laskujen luokittelu")).toBeVisible(AFTER_ACTION);
    await expect(card(page, old)).toHaveCount(0);
    await expect(page.getByRole("heading", { level: 1 })).toHaveText("Laskujen luokittelu", AFTER_ACTION);
    await expect(card(page, "Laskujen luokittelu")).toHaveAttribute("aria-current", "page");

    // Leaving the field saves too, and the name is there after a reload.
    await row(page, "Laskujen luokittelu").getByTestId("session-actions").click();
    await row(page, "Laskujen luokittelu").getByTestId("rename-session").click();
    await name.fill("Ostolaskut");
    await page.getByRole("heading", { level: 1 }).click();
    await expect(page.getByRole("heading", { level: 1 })).toHaveText("Ostolaskut", AFTER_ACTION);
    await page.reload();
    await expect(card(page, "Ostolaskut")).toHaveAttribute("aria-current", "page");
  });

  test("a name that could not be saved stays in its field, with the reason under it", async ({ page }) => {
    await loginAsDev(page);
    await page.goto("/sessions/ses_ui_basics");
    await hydrated(page);
    const old = "UI basics (e2e fixture)";
    await row(page, old).getByTestId("session-actions").click();
    await row(page, old).getByTestId("rename-session").click();
    const name = page.getByTestId("rename-session-input");

    // The request that would save the name never reaches the server.
    await page.route("**/*", (route) =>
      route.request().method() === "POST" && route.request().headers()["next-action"]
        ? route.abort()
        : route.continue(),
    );
    await name.fill("Laskujen luokittelu");
    await name.press("Enter");
    const reason = sidebar(page).getByRole("alert");
    await expect(reason).toHaveText("Nimen tallennus ei onnistunut.", AFTER_ACTION);
    await expect(name).toHaveValue("Laskujen luokittelu");
    await expect(name).toHaveAttribute("aria-invalid", "true");
    await expect(name).toHaveAccessibleDescription("Nimen tallennus ei onnistunut.");
    await expect(page.getByRole("heading", { level: 1 })).toHaveText(old);

    // Typing takes the reason away; sent again once the server answers, the name is saved.
    await page.unroute("**/*");
    await name.fill("Ostolaskut");
    await expect(reason).toHaveCount(0);
    await name.press("Enter");
    await expect(card(page, "Ostolaskut")).toBeVisible(AFTER_ACTION);
    await expect(page.getByRole("heading", { level: 1 })).toHaveText("Ostolaskut", AFTER_ACTION);
  });

  test("opening the sidebar beside a wide chat leaves the workspace its room", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await loginAsDev(page);
    await page.goto("/sessions/ses_gate2_pending");
    await hydrated(page);
    const chat = page.getByTestId("chat-dock");
    const workspace = page.locator("#main-content");
    const width = async (of: typeof chat) => Math.round((await of.boundingBox())!.width);

    // Folded, the sidebar leaves room for the chat at its widest.
    await page.getByTestId("sidebar-toggle").click();
    await expect.poll(() => width(sidebar(page))).toBe(52);
    await page.getByTestId("chat-resize").focus();
    await page.keyboard.press("End");
    await expect.poll(() => width(chat)).toBe(720);
    expect(await width(workspace)).toBeGreaterThanOrEqual(440);

    // Opened, it takes 212 px from the row: the chat gives way, not the workspace.
    await page.getByTestId("sidebar-toggle").click();
    await expect.poll(() => width(sidebar(page))).toBe(264);
    await expect.poll(() => width(workspace)).toBeGreaterThanOrEqual(440);
    expect(await width(chat)).toBeLessThan(720);
    await expect(page.getByTestId("chat-resize")).toHaveAttribute(
      "aria-valuemax",
      String(await width(chat)),
    );

    // Folded again, the chat has the width the viewer gave it.
    await page.getByTestId("sidebar-toggle").click();
    await expect.poll(() => width(chat)).toBe(720);
    expect(await noSidewaysScroll(page)).toBeLessThanOrEqual(0);
  });

  test("End session in a row's menu ends it there, and the session stays where it is", async ({ page }) => {
    await loginAsDev(page);
    await page.goto("/sessions/ses_ui_basics");
    await hydrated(page);
    const title = "UI basics (e2e fixture)";
    const note = row(page, title).getByTestId("end-session-note");

    // A request that never reaches the server: the row says it was not ended.
    await page.route("**/*", (route) =>
      route.request().method() === "POST" && route.request().headers()["next-action"]
        ? route.abort()
        : route.continue(),
    );
    await row(page, title).getByTestId("session-actions").click();
    const end = row(page, title).getByTestId("end-session");
    await expect(end).toHaveAccessibleName(`Lopeta sessio: ${title}`);
    await end.click();
    await expect(note).toHaveText("Sessiota ei voitu lopettaa. Yritä hetken kuluttua uudelleen.", AFTER_ACTION);
    await expect(note).toHaveRole("status");

    // Asked again once the server answers: ended, and nothing else changed.
    await page.unroute("**/*");
    await row(page, title).getByTestId("session-actions").click();
    await end.click();
    await expect(note).toHaveText("Sessio lopetettu. Voit jatkaa sitä myöhemmin.", AFTER_ACTION);
    await expect(card(page, title)).toHaveAttribute("aria-current", "page");
    await expect(page).toHaveURL(/\/sessions\/ses_ui_basics$/);
    await expect(page.getByRole("heading", { level: 1 })).toHaveText(title);
    // That it was ended is said for a moment only.
    await expect(note).toHaveCount(0, AFTER_ACTION);
  });

  test("a row's menu and the account menu are moved in with the arrow keys", async ({ page }) => {
    await loginAsDev(page);
    await page.goto("/sessions/ses_ui_basics");
    await hydrated(page);
    const one = row(page, "UI basics (e2e fixture)");
    await one.getByTestId("session-actions").click();
    // Open, the first item has the focus.
    await expect(one.getByTestId("rename-session")).toBeFocused();
    await page.keyboard.press("ArrowDown");
    await expect(one.getByTestId("export-session")).toBeFocused();
    await page.keyboard.press("ArrowDown");
    await expect(one.getByTestId("end-session")).toBeFocused();
    await page.keyboard.press("End");
    await expect(one.getByTestId("delete-session-open")).toBeFocused();
    await page.keyboard.press("ArrowDown");
    await expect(one.getByTestId("rename-session")).toBeFocused();
    await page.keyboard.press("ArrowUp");
    await expect(one.getByTestId("delete-session-open")).toBeFocused();
    await page.keyboard.press("Escape");
    await expect(one.getByTestId("rename-session")).toBeHidden();
    await expect(one.getByTestId("session-actions")).toBeFocused();

    const account = sidebar(page).getByRole("group", { name: "Käyttäjä" });
    const opener = account.getByTestId("account-menu");
    const menu = account.getByTestId("account-menu-items");
    const fi = menu.locator('button[name="locale"][value="fi"]');
    const en = menu.locator('button[name="locale"][value="en"]');
    const signOut = menu.getByRole("button", { name: "Kirjaudu ulos" });
    // An arrow on the row opens its menu too.
    await opener.focus();
    await page.keyboard.press("ArrowUp");
    await expect(fi).toBeFocused();
    await page.keyboard.press("ArrowDown");
    await expect(en).toBeFocused();
    await page.keyboard.press("ArrowDown");
    await expect(menu.getByTestId("help-link")).toBeFocused();
    await page.keyboard.press("ArrowDown");
    await expect(menu.getByTestId("privacy-link")).toBeFocused();
    await page.keyboard.press("ArrowDown");
    await expect(menu.getByTestId("gaik-demos-link")).toBeFocused();
    await page.keyboard.press("ArrowDown");
    await expect(signOut).toBeFocused();
    await page.keyboard.press("ArrowDown");
    await expect(fi).toBeFocused();
    await page.keyboard.press("ArrowUp");
    await expect(signOut).toBeFocused();
    await page.keyboard.press("Home");
    await expect(fi).toBeFocused();
    // Esc closes it, and the row has the focus again.
    await page.keyboard.press("Escape");
    await expect(menu).toBeHidden();
    await expect(opener).toBeFocused();
  });

  test("the account row says who is signed in; its menu switches the language and signs out", async ({ page }) => {
    await loginAsDev(page);
    await hydrated(page);
    const account = sidebar(page).getByRole("group", { name: "Käyttäjä" });
    const opener = account.getByTestId("account-menu");
    const menu = account.getByTestId("account-menu-items");
    // One row: who is signed in is in view, the rest is behind it.
    await expect(account.getByTestId("user-email")).toHaveText(DEV_USERS.primary.email);
    await expect(opener).toHaveAccessibleName(`Käyttäjä: ${DEV_USERS.primary.email}`);
    await expect(menu).toBeHidden();
    await expect(account.getByRole("button")).toHaveCount(1);

    // The menu opens upward from the row, inside the window: the language,
    // the help page, the privacy notice, the way back to the GAIK demos,
    // signing out.
    await opener.click();
    await expect(menu).toBeVisible();
    await expect(menu.getByRole("group", { name: "Kieli" })).toBeVisible();
    await expect(menu.locator("a[href], button")).toHaveText([
      "Suomi",
      "English",
      "Ohje",
      "Tietosuojaseloste",
      "GAIK-demot",
      "Kirjaudu ulos",
    ]);
    await expect(menu.getByTestId("gaik-demos-link")).toHaveAttribute(
      "href",
      "https://gaik-demo.2.rahtiapp.fi/",
    );
    await expect(menu.locator('button[name="locale"][value="fi"]')).toHaveAttribute("aria-current", "true");
    await expect(menu.locator('button[name="locale"][value="en"]')).not.toHaveAttribute("aria-current", "true");
    await expect.poll(() => menu.evaluate((el) => el.getAnimations().length)).toBe(0);
    const from = (await opener.boundingBox())!;
    const box = (await menu.boundingBox())!;
    expect(box.y).toBeGreaterThanOrEqual(0);
    expect(box.y + box.height).toBeLessThanOrEqual(from.y);
    expect(Math.round(box.x)).toBe(Math.round(from.x));
    // Who is signed in stays in view under it.
    await expect(account.getByTestId("user-email")).toBeVisible();

    await menu.locator('button[name="locale"][value="en"]').click();
    const inEnglish = sidebar(page).getByRole("group", { name: "Account" });
    await expect(sidebar(page).getByRole("link", { name: "New session" })).toBeVisible(AFTER_ACTION);
    await openAccountMenu(page);
    await expect(inEnglish.getByRole("group", { name: "Language" })).toBeVisible();
    await expect(inEnglish.getByRole("button", { name: "Sign out" })).toBeVisible();
    await expect(inEnglish.locator('button[name="locale"][value="en"]')).toHaveAttribute("aria-current", "true");
    await inEnglish.locator('button[name="locale"][value="fi"]').click();
    await expect(sidebar(page).getByRole("link", { name: "Uusi sessio" })).toBeVisible(AFTER_ACTION);
    await openAccountMenu(page);
    await expect(account.getByRole("button", { name: "Kirjaudu ulos" })).toBeVisible();

    await signOutDev(page);
    // Signed out, the shell is out of reach.
    await page.goto("/");
    await page.waitForURL("/login");
  });

  test("New session leads to the start view, and on it puts the cursor in the field", async ({ page }) => {
    await loginAsDev(page);
    await page.goto("/sessions/ses_ui_basics");
    await hydrated(page);
    await page.getByTestId("new-session").click();
    await page.waitForURL("/");
    const start = page.getByTestId("start-view").locator('textarea[name="message"]');
    await expect(start).toBeFocused();

    // Already on the start view: there is no page to go to, so the field takes the cursor.
    await page.getByRole("searchbox", { name: "Hae sessioita" }).focus();
    await expect(start).not.toBeFocused();
    await page.getByTestId("new-session").click();
    await expect(start).toBeFocused();
    await expect(page).toHaveURL(/\/$/);
  });
});

test.describe("the sidebar on a phone", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("is a drawer: opened from its button, closed by Esc and by opening a session", async ({ page }) => {
    await loginAsDev(page);
    await hydrated(page);
    const opener = page.getByTestId("sidebar-open");
    // Closed, the drawer is out of sight and out of the tab order.
    await expect(sidebar(page)).toBeHidden();
    await expect(page.getByTestId("start-view")).toBeVisible();
    expect(await noSidewaysScroll(page)).toBeLessThanOrEqual(0);

    await opener.click();
    await expect(sidebar(page)).toBeVisible();
    await expect(sidebar(page).getByRole("button", { name: "Sulje sivupalkki" })).toBeFocused();
    // It slides in from the left edge and stands against it.
    await expect.poll(async () => (await sidebar(page).boundingBox())!.x).toBe(0);
    expect((await sidebar(page).boundingBox())!.width).toBeLessThanOrEqual(390 * 0.86 + 1);
    // Everything is in it, also what a folded desktop column leaves out.
    await expect(cards(page).first()).toBeVisible();
    await expect(sidebar(page).getByTestId("user-email")).toBeVisible();
    await expect(sidebar(page).getByTestId("account-menu")).toBeVisible();
    // The page under it is out of reach meanwhile.
    await expect(page.locator("[data-shell-main]")).toHaveAttribute("inert", "");
    expect(await noSidewaysScroll(page)).toBeLessThanOrEqual(0);

    await page.keyboard.press("Escape");
    await expect(sidebar(page)).toBeHidden();
    await expect(opener).toBeFocused();
    await expect(page.locator("[data-shell-main]")).not.toHaveAttribute("inert", "");

    // Opening a session closes it, and the session's bar keeps clear of the button.
    await opener.click();
    await card(page, "Gate 2 — pending review").click();
    await page.waitForURL(/\/sessions\/ses_gate2_pending$/);
    await expect(sidebar(page)).toBeHidden();
    const title = page.getByRole("heading", { level: 1 });
    await expect(title).toHaveText("Gate 2 — pending review (e2e fixture)");
    const button = (await opener.boundingBox())!;
    const heading = (await title.boundingBox())!;
    expect(heading.x).toBeGreaterThanOrEqual(button.x + button.width);
    expect(await noSidewaysScroll(page)).toBeLessThanOrEqual(0);

    // The row of the open session closes the drawer too, though it leads nowhere new.
    await opener.click();
    await expect(card(page, "Gate 2 — pending review")).toHaveAttribute("aria-current", "page");
    await card(page, "Gate 2 — pending review").click();
    await expect(sidebar(page)).toBeHidden();
  });

  test.describe("with a touch screen", () => {
    test.use({ hasTouch: true, isMobile: true });

    test("every control of the drawer is tall enough for a finger", async ({ page }) => {
      await loginAsDev(page);
      await hydrated(page);
      expect(await page.evaluate(() => window.matchMedia("(pointer: coarse)").matches)).toBe(true);
      await page.getByTestId("sidebar-open").tap();
      await expect.poll(async () => (await sidebar(page).boundingBox())!.x).toBe(0);

      const account = sidebar(page).getByRole("group", { name: "Käyttäjä" });
      const controls = {
        home: sidebar(page).getByRole("link", { name: "GAIK Solution Wizard" }),
        close: sidebar(page).getByRole("button", { name: "Sulje sivupalkki" }),
        newSession: sidebar(page).getByTestId("new-session"),
        row: cards(page).first(),
        rowActions: sidebar(page).getByTestId("session-actions").first(),
        account: account.getByTestId("account-menu"),
      };
      for (const [name, control] of Object.entries(controls)) {
        expect((await control.boundingBox())!.height, name).toBeGreaterThanOrEqual(32);
      }
      // The account row and the items of its menu are 44 px tall at least.
      expect((await controls.account.boundingBox())!.height).toBeGreaterThanOrEqual(44);
      await controls.account.tap();
      const menu = account.getByTestId("account-menu-items");
      await expect(menu).toBeVisible();
      const items = {
        fi: menu.locator('button[name="locale"][value="fi"]'),
        en: menu.locator('button[name="locale"][value="en"]'),
        help: menu.getByTestId("help-link"),
        privacy: menu.getByTestId("privacy-link"),
        demos: menu.getByTestId("gaik-demos-link"),
        signOut: menu.getByRole("button", { name: "Kirjaudu ulos" }),
      };
      for (const [name, item] of Object.entries(items)) {
        expect((await item.boundingBox())!.height, name).toBeGreaterThanOrEqual(44);
      }
      await page.keyboard.press("Escape");
      await expect(menu).toBeHidden();
      // The user area still fits the drawer without pushing the list out of it.
      const drawer = (await sidebar(page).boundingBox())!;
      const area = (await account.boundingBox())!;
      expect(area.y + area.height).toBeLessThanOrEqual(drawer.y + drawer.height);
      expect(await noSidewaysScroll(page)).toBeLessThanOrEqual(0);
    });
  });

  test("the account menu opens inside the window, and Esc closes it before the drawer", async ({ page }) => {
    await loginAsDev(page);
    await hydrated(page);
    await page.getByTestId("sidebar-open").click();
    const account = sidebar(page).getByRole("group", { name: "Käyttäjä" });
    const opener = account.getByTestId("account-menu");
    const menu = account.getByTestId("account-menu-items");

    await opener.click();
    await expect(menu).toBeVisible();
    await expect.poll(() => menu.evaluate((el) => el.getAnimations().length)).toBe(0);
    const from = (await opener.boundingBox())!;
    const box = (await menu.boundingBox())!;
    expect(box.x).toBeGreaterThanOrEqual(0);
    expect(box.x + box.width).toBeLessThanOrEqual(390);
    expect(box.y).toBeGreaterThanOrEqual(0);
    expect(box.y + box.height).toBeLessThanOrEqual(from.y);
    // In the drawer its items are tall enough for a finger.
    for (const item of await menu.locator("a[href], button").all()) {
      expect((await item.boundingBox())!.height).toBeGreaterThanOrEqual(44);
    }
    expect(await noSidewaysScroll(page)).toBeLessThanOrEqual(0);

    // Esc closes the menu only; the drawer stays, and the row has the focus.
    await page.keyboard.press("Escape");
    await expect(menu).toBeHidden();
    await expect(sidebar(page)).toBeVisible();
    await expect(opener).toBeFocused();

    // The privacy notice is a page of its own, outside the shell.
    await opener.click();
    await menu.getByTestId("privacy-link").click();
    await page.waitForURL("/privacy");
  });

  test("a row's menu opens inside the window, and a press on the page behind closes the drawer", async ({ page }) => {
    await loginAsDev(page);
    await hydrated(page);
    await page.getByTestId("sidebar-open").click();

    // The last row, near the bottom of the list: its menu opens upward.
    const last = sidebar(page).locator("li").filter({ has: cards(page) }).last();
    await last.scrollIntoViewIfNeeded();
    const menuButton = last.getByTestId("session-actions");
    await menuButton.click();
    const rename = last.getByTestId("rename-session");
    await expect(rename).toBeVisible();
    const item = (await rename.boundingBox())!;
    expect(item.x).toBeGreaterThanOrEqual(0);
    expect(item.x + item.width).toBeLessThanOrEqual(390);
    expect(item.y).toBeGreaterThanOrEqual(0);
    expect(item.y + item.height).toBeLessThanOrEqual(844);
    // Esc closes the menu only; the drawer stays.
    await page.keyboard.press("Escape");
    await expect(rename).toBeHidden();
    await expect(sidebar(page)).toBeVisible();
    await expect(menuButton).toBeFocused();

    // The strip of the page left in view closes the drawer.
    await page.mouse.click(380, 400);
    await expect(sidebar(page)).toBeHidden();
  });
});
