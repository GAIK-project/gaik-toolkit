import { test, expect, type Page } from "@playwright/test";
import { DEV_USERS, loginAsDev } from "./helpers/auth";
import { setMockSessionStep } from "./helpers/dev-step";
import { resetMockSessions } from "./helpers/mock";
import { motion, recordMotion } from "./helpers/motion";
import { createSession, hydrated, startFromMessage } from "./helpers/session";
import { choiceOption, choicePill, choose } from "./helpers/start-choice";
import { PACE_SENTENCES, START_LINES_ROOM } from "../lib/chat-background";
import { MAX_CHAT_MESSAGE_CHARS } from "../lib/chat-limits";

/**
 * A session starts from the user's first message: the start view at "/" has
 * one field, the message sent from it creates the session, named from what it
 * says, and the session's chat sends it as its first turn.
 *
 * And the start of a session with the live agent. That agent asks in the chat and
 * keeps no requirement checklist, so before the specification the workspace
 * had one paragraph that sent the reader to the chat beside it. There the chat
 * is the page: an empty one opens with a question, the field and examples, and
 * the workspace comes in beside the conversation at the specification.
 *
 * The mock store these specs run on seeds a checklist and an opening question;
 * /api/dev/live-start takes them out, as a live session has neither.
 */

async function newLiveSession(page: Page): Promise<string> {
  await loginAsDev(page);
  await createSession(page, `start ${Date.now()}`);
  const id = new URL(page.url()).pathname.split("/")[2];
  const res = await page.request.post("/api/dev/live-start", { data: { id } });
  expect(res.ok(), `live-start failed: ${res.status()}`).toBe(true);
  await page.reload();
  await hydrated(page);
  return id;
}

const startField = (page: Page) =>
  page.getByTestId("start-view").locator('textarea[name="message"]');
const title = (page: Page) => page.getByRole("heading", { level: 1 });
const cards = (page: Page) => page.getByTestId("session-card");
// A session starts with a server action: on a busy dev server it takes a few seconds.
const AFTER_ACTION = { timeout: 20_000 };

/** The messages the page posts to the wizard, in order. */
function chatPosts(page: Page): () => string[] {
  const sent: string[] = [];
  page.on("request", (request) => {
    if (request.method() !== "POST" || !/\/api\/sessions\/[^/]+\/chat$/.test(request.url())) return;
    sent.push((request.postDataJSON() as { message: string }).message);
  });
  return () => sent;
}

/** A first message as the wizard gets it when nothing is chosen: the default
 *  pace's line, then the user's words (lib/chat-background). */
const QUICK = PACE_SENTENCES.fi.quick;
const asFirst = (text: string) => `${QUICK}\n${text}`;

const field = (page: Page) => page.locator('textarea[name="message"]');
const send = (page: Page) =>
  page.locator('form:has(textarea[name="message"]) button[type="submit"]');
const noSidewaysScroll = (page: Page) =>
  page.evaluate(() => document.scrollingElement!.scrollWidth - window.innerWidth);

test.describe("a session starts from the first message", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test.beforeEach(async ({ page, request }) => {
    await resetMockSessions(request);
    // The second dev user starts without sessions.
    await loginAsDev(page, DEV_USERS.secondary);
    await hydrated(page);
  });

  test("a signed-in user lands on the start view: the wizard's name, the question and the field", async ({
    page,
  }) => {
    await expect(page.getByRole("heading", { name: "GAIK Solution Wizard", level: 1 })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Mitä haluat ratkaista?", level: 2 })).toBeVisible();
    await expect(startField(page)).toBeFocused();
    await expect(startField(page)).toHaveAccessibleName("Viesti wizardille");
    // Legal: the replies come from an AI, said before the first message too.
    await expect(page.getByTestId("chat-ai-notice")).toHaveText(
      "Vastaukset tuottaa tekoäly. Tarkista ne ennen käyttöä.",
    );
    await expect(page.getByTestId("chat-examples").getByRole("button")).toHaveCount(4);
    // Nothing exists before the first send, and nobody is asked for a name.
    await expect(cards(page)).toHaveCount(0);
    await expect(page.getByTestId("sidebar")).toContainText("Ei vielä sessioita.");
    await expect(page.getByLabel("Session nimi")).toHaveCount(0);
    await expect(page.locator("#main-content")).toHaveCount(1);

    // An empty field sends nothing.
    await startField(page).press("Enter");
    await expect(page).toHaveURL(/\/$/);
    await expect(cards(page)).toHaveCount(0);

    // The field sits on the middle line of the space beside the sidebar.
    const view = (await page.locator("#main-content").boundingBox())!;
    const input = (await startField(page).boundingBox())!;
    expect(Math.abs(input.x + input.width / 2 - (view.x + view.width / 2))).toBeLessThan(40);
    expect(await noSidewaysScroll(page)).toBeLessThanOrEqual(0);
  });

  test("the first message creates one session, named from it, and goes out as its first turn", async ({
    page,
  }) => {
    const sent = chatPosts(page);
    const text = "Luokittele saapuvat reklamaatiot. Niitä tulee satoja päivässä.";
    await startField(page).fill(text);
    // A second Enter before the session exists starts nothing more.
    await startField(page).press("Enter");
    await startField(page).press("Enter");

    await page.waitForURL(/\/sessions\/[^/]+$/, AFTER_ACTION);
    await expect(title(page)).toHaveText("Luokittele saapuvat reklamaatiot");
    // The message is in the conversation once, and gets its reply.
    const messages = page.getByTestId("chat-message");
    await expect(messages).toHaveCount(2);
    await expect(messages.first()).toHaveText(text);
    await expect(send(page)).toBeEnabled({ timeout: 30_000 });
    await expect(messages.nth(1)).toContainText("Kiitos viestistä");
    // The wizard got it once, behind the line that says how much to ask.
    expect(sent()).toEqual([asFirst(text)]);
    // The empty chat's own start view was not on the way, and the field is
    // empty at the bottom of the conversation.
    await expect(page.getByTestId("chat-start")).toHaveCount(0);
    await expect(field(page)).toHaveValue("");
    expect((await field(page).boundingBox())!.y).toBeGreaterThan(700);
    await expect(page.getByRole("main", { name: "Keskustelu" })).toBeVisible();

    // One session, listed in the sidebar as the open one.
    await expect(cards(page)).toHaveCount(1);
    await expect(cards(page)).toContainText("Luokittele saapuvat reklamaatiot");
    await expect(cards(page)).toHaveAttribute("aria-current", "page");

    // A reload shows the same conversation and sends nothing again.
    await page.reload();
    await expect(messages).toHaveCount(2);
    await expect(cards(page)).toHaveCount(1);
    expect(sent()).toEqual([asFirst(text)]);
  });

  test("the start view's field is carried to the foot of the conversation, once", async ({ page }) => {
    await recordMotion(page);
    await page.reload();
    await hydrated(page);
    const text = "Tiivistä asiakaspalautteet viikoittain.";
    const from = (await page.getByTestId("start-view").locator("form > div").first().boundingBox())!;
    await startFromMessage(page, text);
    await expect(page.getByTestId("chat-message").first()).toHaveText(text);

    // One movement of the chat's form, from where the start view's field stood.
    const form = page.locator('form:has(textarea[name="message"])');
    const fieldGlides = async () =>
      (await motion(page)).filter(
        (move) => move.kind === "script" && move.name.includes("translateY") && move.at.startsWith("chat-dock"),
      );
    const glides = await fieldGlides();
    expect(glides).toHaveLength(1);
    await expect.poll(() => form.evaluate((el) => el.getAnimations().length)).toBe(0);
    const landed = (await form.locator("div:has(> textarea)").boundingBox())!;
    const shift = Number(/translateY\((-?[\d.]+)px\)/.exec(glides[0].name)?.[1]);
    // The field arrives as the one line it stays (components/composer-card):
    // shorter than the start view's card, which also held the choices. Its top
    // edge started where the start view's field had its top, and it did not
    // change height on the way.
    expect(landed.height).toBeLessThan(from.height);
    expect(Math.abs(landed.y + shift - from.y)).toBeLessThan(4);
    // The page's own arrival gave way to it: the bar rises, the content does not.
    const arrivals = (await motion(page)).filter((move) => move.name === "session-in");
    expect(arrivals.map((move) => move.at)).toEqual(["session-bar"]);

    // A reply later, nothing of it has run again.
    await expect(send(page)).toBeEnabled({ timeout: 30_000 });
    await field(page).fill("Ja lajittele ne aiheen mukaan.");
    await field(page).press("Enter");
    await expect(page.getByTestId("chat-message")).toHaveCount(4, { timeout: 30_000 });
    await expect(send(page)).toBeEnabled({ timeout: 30_000 });
    expect(await fieldGlides()).toHaveLength(1);
    expect((await motion(page)).filter((move) => move.name === "session-in")).toHaveLength(1);
  });

  test("with reduced motion the start view becomes the conversation at once", async ({ page }) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    await recordMotion(page);
    await page.reload();
    await hydrated(page);
    const text = "Poimi sopimuksista irtisanomisajat.";
    await startFromMessage(page, text);

    // The message is in the log and the field is at the bottom, empty.
    await expect(page.getByTestId("chat-message").first()).toHaveText(text);
    await expect(field(page)).toHaveValue("");
    const form = (await page.locator('form:has(textarea[name="message"])').boundingBox())!;
    expect(form.y + form.height).toBeGreaterThan(900 - 4);
    // Nothing was started from script: the field and the page are simply there.
    expect((await motion(page)).filter((move) => move.kind === "script")).toEqual([]);
    await expect(send(page)).toBeEnabled({ timeout: 30_000 });
  });

  test("a session started from an example is named by the example", async ({ page }) => {
    const sent = chatPosts(page);
    const prompt = "Haluamme poimia toimittajien PDF-laskuista keskeiset kentät.";
    // Who the user is is chosen beside the field; the field holds the example only.
    await choose(page, "chat-background", "Tekninen");
    await expect(startField(page)).toHaveValue("");
    await page.getByTestId("chat-examples").getByRole("button", { name: "Laskun kentät" }).click();
    await expect(startField(page)).toHaveValue(prompt);
    await expect(startField(page)).toBeFocused();
    await startField(page).press("Enter");

    await page.waitForURL(/\/sessions\/[^/]+$/, AFTER_ACTION);
    await expect(title(page)).toHaveText("Laskun kentät");
    // The wizard got the background sentence as the message's first line and
    // the pace as its second; the user's own bubble shows what they sent from
    // the field.
    await expect(page.getByTestId("chat-message").first()).toHaveText(prompt);
    await expect.poll(sent).toHaveLength(1);
    expect(sent()[0].split("\n")).toEqual([
      expect.stringMatching(/^Taustani: olen tekninen\./),
      QUICK,
      prompt,
    ]);
    await expect(field(page)).toHaveValue("");
    await expect(send(page)).toBeEnabled({ timeout: 30_000 });
    await expect(field(page)).toHaveValue("");
    // Read again from the server, the message is still the user's words only.
    await page.reload();
    await hydrated(page);
    await expect(page.getByTestId("chat-message").first()).toHaveText(prompt);

    // The next start remembers who the user said they are, and its field is empty.
    await page.getByTestId("new-session").click();
    await page.waitForURL("/");
    await expect(choicePill(page, "chat-background")).toHaveAccessibleName("Taustasi: Tekninen");
    await expect(startField(page)).toHaveValue("");
  });

  test("a first message left over for a session that already has its conversation is not sent", async ({
    page,
  }) => {
    const sent = chatPosts(page);
    // The mock store opens a session made without a message with the wizard's question.
    const id = await createSession(page, "Aiempi keskustelu");
    await expect(page.getByTestId("chat-message").first()).toBeVisible();
    const before = await page.getByTestId("chat-message").count();
    const key = `gaik-wizard:pending-first-message:${id}`;
    const leftOver = "Tämä viesti kirjoitettiin toista keskustelua varten.";
    await page.evaluate(
      ([name, text]) => window.sessionStorage.setItem(name, JSON.stringify({ text, fieldTop: 400 })),
      [key, leftOver],
    );

    await page.reload();
    await hydrated(page);
    await expect(send(page)).toBeVisible();
    // Taken once and dropped: not sent, not shown, not left for the next load.
    await expect.poll(() => page.evaluate((name) => window.sessionStorage.getItem(name), key)).toBeNull();
    await expect(page.getByTestId("chat-message")).toHaveCount(before);
    await expect(page.getByTestId("chat-dock")).not.toContainText(leftOver);
    expect(sent()).toEqual([]);
  });

  test("a message that could not start a session stays in the field, with the reason", async ({ page }) => {
    const text = "Tiivistä kokousmuistiot päätöksiksi ja tehtäviksi.";
    // The request that would create the session never reaches the server.
    await page.route("**/*", (route) =>
      route.request().method() === "POST" && route.request().headers()["next-action"]
        ? route.abort()
        : route.continue(),
    );
    await startField(page).fill(text);
    await startField(page).press("Enter");

    await expect(page.getByTestId("start-error")).toHaveText(
      "Session aloitus ei onnistunut. Yritä uudelleen.",
    );
    await expect(startField(page)).toHaveValue(text);
    await expect(page).toHaveURL(/\/$/);
    await expect(cards(page)).toHaveCount(0);

    // Sent again once the server answers, the same words start the session.
    await page.unroute("**/*");
    await startField(page).press("Enter");
    await page.waitForURL(/\/sessions\/[^/]+$/, AFTER_ACTION);
    await expect(page.getByTestId("chat-message").first()).toHaveText(text);
    await expect(cards(page)).toHaveCount(1);
  });

  test("a first message the wizard refuses is back in the field, under the warning", async ({ page }) => {
    const text = "Poimi sopimuksista irtisanomisajat.";
    // The wizard has no room for another session right now.
    await page.route("**/api/sessions/*/chat", (route) =>
      route.request().method() === "POST" ? route.fulfill({ status: 503, body: "" }) : route.continue(),
    );
    await startField(page).fill(text);
    await startField(page).press("Enter");

    await page.waitForURL(/\/sessions\/[^/]+$/, AFTER_ACTION);
    const messages = page.getByTestId("chat-message");
    await expect(messages).toHaveCount(2);
    await expect(messages.first()).toHaveText(text);
    await expect(messages.nth(1)).toContainText("⚠︎");
    // Nothing is lost: the words are in the field, to send again.
    await expect(field(page)).toHaveValue(text);
    await expect(title(page)).toHaveText("Poimi sopimuksista irtisanomisajat");
  });

  test("a refused first message is still in the field after a reload, and is not sent a second time", async ({
    page,
  }) => {
    const text = "Poimi sopimuksista irtisanomisajat.";
    const sent: string[] = [];
    let refuse = true;
    const reply = [{ delta: "Selvä." }, { done: true }].map((e) => `data: ${JSON.stringify(e)}\n\n`).join("");
    // The wizard has no room for another session right now.
    await page.route("**/api/sessions/*/chat", (route) => {
      if (route.request().method() !== "POST") return route.continue();
      sent.push((route.request().postDataJSON() as { message: string }).message);
      return refuse
        ? route.fulfill({ status: 503, body: "" })
        : route.fulfill({ status: 200, contentType: "text/event-stream", body: reply });
    });
    await startField(page).fill(text);
    await startField(page).press("Enter");
    await page.waitForURL(/\/sessions\/[^/]+$/, AFTER_ACTION);
    await expect(page.getByTestId("chat-message").nth(1)).toContainText("⚠︎");
    await expect(field(page)).toHaveValue(text);
    expect(sent).toHaveLength(1);
    const key = `gaik-wizard:pending-first-message:${new URL(page.url()).pathname.split("/")[2]}`;

    // The session is named after words the server never got: a reload must
    // not lose them, and must not send them by itself.
    await page.reload();
    await hydrated(page);
    await expect(title(page)).toHaveText("Poimi sopimuksista irtisanomisajat");
    await expect(field(page)).toHaveValue(text);
    await expect(page.getByTestId("chat-message")).toHaveCount(0);
    await page.waitForTimeout(500);
    expect(sent).toHaveLength(1);

    // Sent by the user once the wizard has room: it goes out with its first
    // lines, and nothing is kept for another load.
    refuse = false;
    await field(page).press("Enter");
    await expect.poll(() => sent.length).toBe(2);
    expect(sent[1]).toBe(asFirst(text));
    await expect(page.locator('[data-testid="chat-message"][data-role="user"]')).toHaveText([text]);
    await expect.poll(() => page.evaluate((name) => window.sessionStorage.getItem(name), key)).toBeNull();
    await page.reload();
    await hydrated(page);
    await expect(field(page)).toHaveValue("");
    expect(sent).toHaveLength(2);
  });

  test("a first message the wizard took is not kept for another load", async ({ page }) => {
    const sent = chatPosts(page);
    const reply = [{ delta: "Selvä." }, { done: true }].map((e) => `data: ${JSON.stringify(e)}\n\n`).join("");
    await page.route("**/api/sessions/*/chat", (route) =>
      route.request().method() === "POST"
        ? route.fulfill({ status: 200, contentType: "text/event-stream", body: reply })
        : route.continue(),
    );
    const id = await startFromMessage(page, "Poimi sopimuksista irtisanomisajat.");
    await expect.poll(() => sent().length, AFTER_ACTION).toBe(1);
    await expect
      .poll(() => page.evaluate((name) => window.sessionStorage.getItem(name), `gaik-wizard:pending-first-message:${id}`))
      .toBeNull();
  });

  test("after a refused first message the field keeps room for the lines its resend carries", async ({ page }) => {
    const text = "Poimi sopimuksista irtisanomisajat.";
    let refuse = true;
    const reply = [{ delta: "Selvä." }, { done: true }].map((e) => `data: ${JSON.stringify(e)}\n\n`).join("");
    await page.route("**/api/sessions/*/chat", (route) => {
      if (route.request().method() !== "POST") return route.continue();
      return refuse
        ? route.fulfill({ status: 503, body: "" })
        : route.fulfill({ status: 200, contentType: "text/event-stream", body: reply });
    });
    await startField(page).fill(text);
    await startField(page).press("Enter");
    await page.waitForURL(/\/sessions\/[^/]+$/, AFTER_ACTION);
    await expect(page.getByTestId("chat-message").nth(1)).toContainText("⚠︎");
    await expect(field(page)).toHaveValue(text);

    // The refused message is in the chat, and the wizard has still heard
    // nothing: the resend goes out with the background and pace lines, so the
    // field may hold only what leaves room for them.
    const withRoom = String(MAX_CHAT_MESSAGE_CHARS - START_LINES_ROOM);
    await expect(field(page)).toHaveAttribute("maxlength", withRoom);

    // Once the wizard has taken a message, the next ones carry no lines.
    refuse = false;
    await field(page).press("Enter");
    await expect(page.getByTestId("chat-message").last()).toContainText("Selvä.");
    await expect(field(page)).toHaveAttribute("maxlength", String(MAX_CHAT_MESSAGE_CHARS));
  });

  test("a refused first message is back as the user's words, and its background goes out with the next send", async ({
    page,
  }) => {
    const text = "Poimi sopimuksista irtisanomisajat.";
    const sent: string[] = [];
    let refuse = true;
    const reply = [{ delta: "Selvä." }, { done: true }].map((e) => `data: ${JSON.stringify(e)}\n\n`).join("");
    await page.route("**/api/sessions/*/chat", (route) => {
      if (route.request().method() !== "POST") return route.continue();
      sent.push((route.request().postDataJSON() as { message: string }).message);
      return refuse
        ? route.fulfill({ status: 503, body: "" })
        : route.fulfill({ status: 200, contentType: "text/event-stream", body: reply });
    });
    await choose(page, "chat-background", "En ole tekninen");
    await startField(page).fill(text);
    await startField(page).press("Enter");

    await page.waitForURL(/\/sessions\/[^/]+$/, AFTER_ACTION);
    const mine = page.locator('[data-testid="chat-message"][data-role="user"]');
    await expect(mine).toHaveText([text]);
    // The wizard was sent the background and pace lines; the field gets only the words back.
    const whole = /^Taustani: en ole tekninen\.[^\n]*\nTahti: nopea\.[^\n]*\nPoimi sopimuksista irtisanomisajat\.$/;
    expect(sent).toHaveLength(1);
    expect(sent[0]).toMatch(whole);
    await expect(field(page)).toHaveValue(text);
    await expect(title(page)).toHaveText("Poimi sopimuksista irtisanomisajat");

    // Sent again, it still tells the wizard who the user is.
    refuse = false;
    await field(page).press("Enter");
    await expect.poll(() => sent.length).toBe(2);
    expect(sent[1]).toMatch(whole);
    await expect(mine).toHaveText([text, text]);
    await expect(field(page)).toHaveValue("");
  });

  test("the background choice is a pill that opens a menu saying what each option changes", async ({ page }) => {
    const pill = choicePill(page, "chat-background");
    const menu = page.getByTestId("chat-background").getByRole("menu");
    const technical = choiceOption(page, "chat-background", "Tekninen");
    const nonTechnical = choiceOption(page, "chat-background", "En ole tekninen");

    // Nothing is chosen yet: the pill says what the choice is about, and no menu is open.
    await expect(pill).toHaveAccessibleName("Taustasi");
    await expect(pill).toHaveText("Taustasi");
    await expect(pill).toHaveAttribute("aria-expanded", "false");
    await expect(menu).toHaveCount(0);

    // A press opens the menu over the card, starting at its pill: both options, each with a line on what it changes.
    await pill.click();
    await expect(pill).toHaveAttribute("aria-expanded", "true");
    await expect(menu).toHaveAccessibleName("Taustasi");
    await expect(menu.getByRole("menuitemradio")).toHaveCount(2);
    await expect(nonTechnical).toContainText("Wizard kysyy arkikielellä ja ehdottaa oletukset teknisiin kohtiin.");
    await expect(technical).toContainText("Wizard käyttää teknisiä termejä ja kysyy teknisistä valinnoista suoraan.");
    await expect(nonTechnical).toHaveAttribute("aria-checked", "false");
    await expect(technical).toHaveAttribute("aria-checked", "false");
    const card = (await page.getByTestId("start-view").locator("form > div").first().boundingBox())!;
    const box = (await menu.boundingBox())!;
    expect(box.x).toBeGreaterThanOrEqual(card.x);
    expect(box.x + box.width).toBeLessThanOrEqual(card.x + card.width);
    expect(box.y + box.height).toBeLessThanOrEqual(card.y);
    expect(await noSidewaysScroll(page)).toBeLessThanOrEqual(0);
    // The AI notice under the card is not under the menu.
    const notice = page.getByTestId("chat-ai-notice");
    await expect(notice).toBeVisible();
    expect(
      await notice.evaluate((el) => {
        const at = el.getBoundingClientRect();
        return el.contains(document.elementFromPoint(at.left + at.width / 2, at.top + at.height / 2));
      }),
    ).toBe(true);
    // A window that changes size puts the menu away: it was placed for the card as it was.
    await page.setViewportSize({ width: 900, height: 900 });
    await expect(menu).toHaveCount(0);
    await page.setViewportSize({ width: 1440, height: 900 });
    await pill.click();

    // Choosing closes the menu, shows the choice on the pill and hands the cursor to the field, which stays empty.
    await technical.click();
    await expect(menu).toHaveCount(0);
    await expect(pill).toHaveAccessibleName("Taustasi: Tekninen");
    await expect(pill).toHaveText("Tekninen");
    await expect(startField(page)).toBeFocused();
    await expect(startField(page)).toHaveValue("");

    // From the keyboard: the arrow opens the menu on what is chosen, the arrows move in it, Enter chooses.
    await pill.focus();
    await page.keyboard.press("ArrowDown");
    await expect(technical).toBeFocused();
    await expect(technical).toHaveAttribute("aria-checked", "true");
    await page.keyboard.press("ArrowUp");
    await expect(nonTechnical).toBeFocused();
    await page.keyboard.press("Enter");
    await expect(menu).toHaveCount(0);
    await expect(pill).toHaveAccessibleName("Taustasi: En ole tekninen");

    // Esc and a press elsewhere close the menu without choosing; Esc leaves the focus on the pill.
    await pill.click();
    await page.keyboard.press("Escape");
    await expect(menu).toHaveCount(0);
    await expect(pill).toBeFocused();
    await pill.click();
    await page.getByRole("heading", { name: "Mitä haluat ratkaista?" }).click();
    await expect(menu).toHaveCount(0);
    await expect(pill).toHaveAccessibleName("Taustasi: En ole tekninen");

    // A choice remembered from before is simply there when the view opens.
    await page.reload();
    await hydrated(page);
    await expect(pill).toHaveAccessibleName("Taustasi: En ole tekninen");

    // Choosing the chosen one again takes the choice back.
    await choose(page, "chat-background", "En ole tekninen");
    await expect(pill).toHaveAccessibleName("Taustasi");
  });

  test("how much the wizard asks is chosen beside the field: quick unless the user says thorough", async ({
    page,
  }) => {
    const sent = chatPosts(page);
    const text = "Poimi sopimuksista irtisanomisajat.";
    const pill = choicePill(page, "chat-pace");
    const quick = choiceOption(page, "chat-pace", "Nopea");
    const thorough = choiceOption(page, "chat-pace", "Perusteellinen");

    // Quick to begin with, said on the pill without a press.
    await expect(pill).toHaveAccessibleName("Kysymysten määrä: Nopea");
    await pill.click();
    await expect(quick).toHaveAttribute("aria-checked", "true");
    await expect(thorough).toHaveAttribute("aria-checked", "false");
    await expect(quick).toContainText("Kysyy vain välttämättömän, mieluiten yhdellä kierroksella, ja olettaa loput.");
    await expect(thorough).toContainText("Kysyy kaiken, mitä yksityiskohtien saamiseksi oikein tarvitaan.");
    await page.keyboard.press("Escape");

    // The choice writes nothing into the field, empty or not, and one of the
    // two is always chosen: choosing the chosen one again leaves it chosen.
    await startField(page).fill(text);
    await choose(page, "chat-pace", "Perusteellinen");
    await expect(pill).toHaveAccessibleName("Kysymysten määrä: Perusteellinen");
    await expect(startField(page)).toHaveValue(text);
    await choose(page, "chat-pace", "Perusteellinen");
    await expect(pill).toHaveAccessibleName("Kysymysten määrä: Perusteellinen");
    // The arrow keys move in the menu, as in the background's.
    await pill.focus();
    await page.keyboard.press("ArrowDown");
    await expect(thorough).toBeFocused();
    await page.keyboard.press("ArrowDown");
    await expect(quick).toBeFocused();
    await page.keyboard.press("Escape");
    await expect(pill).toHaveAccessibleName("Kysymysten määrä: Perusteellinen");
    await expect(startField(page)).toHaveValue(text);

    // The first message carries the pace as a line ahead of the user's words;
    // their own bubble and the session's name do not show it.
    await startField(page).press("Enter");
    await page.waitForURL(/\/sessions\/[^/]+$/, AFTER_ACTION);
    await expect(page.getByTestId("chat-message").first()).toHaveText(text);
    await expect(title(page)).toHaveText("Poimi sopimuksista irtisanomisajat");
    await expect.poll(sent).toHaveLength(1);
    expect(sent()[0]).toBe(`${PACE_SENTENCES.fi.thorough}\n${text}`);
    await expect(send(page)).toBeEnabled({ timeout: 30_000 });
    // The next message is the user's words alone.
    await field(page).fill("Niitä on satoja.");
    await field(page).press("Enter");
    await expect.poll(sent).toHaveLength(2);
    expect(sent()[1]).toBe("Niitä on satoja.");

    // The choice is remembered for the next session.
    await page.getByTestId("new-session").click();
    await page.waitForURL("/");
    await expect(pill).toHaveAccessibleName("Kysymysten määrä: Perusteellinen");
    await expect(startField(page)).toHaveValue("");
  });
});

test.describe("a session starts from the first message, on a phone", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("the start view fits the window, and the first message opens the conversation", async ({
    page,
    request,
  }) => {
    await resetMockSessions(request);
    await loginAsDev(page, DEV_USERS.secondary);
    await hydrated(page);

    await expect(page.getByRole("heading", { name: "GAIK Solution Wizard", level: 1 })).toBeVisible();
    await expect(page.getByTestId("chat-examples").getByRole("button")).toHaveCount(4);
    await expect(page.getByTestId("chat-ai-notice")).toBeInViewport();
    // The button that opens the sidebar stands clear of the view's content.
    const opener = (await page.getByTestId("sidebar-open").boundingBox())!;
    const heading = (await page.getByRole("heading", { level: 1 }).boundingBox())!;
    expect(heading.y).toBeGreaterThanOrEqual(opener.y + opener.height);
    expect(await noSidewaysScroll(page)).toBeLessThanOrEqual(0);

    await startField(page).fill("Lajittelemme asiakkaiden sähköpostit käsin.");
    await page.getByTestId("start-view").getByRole("button", { name: "Lähetä" }).click();
    await page.waitForURL(/\/sessions\/[^/]+$/, AFTER_ACTION);
    await expect(title(page)).toHaveText("Lajittelemme asiakkaiden sähköpostit");
    await expect(page.getByTestId("chat-message")).toHaveCount(2);
    // The chat is the page here, not a sheet over it.
    const chat = page.getByRole("main", { name: "Keskustelu" });
    expect(await chat.evaluate((el) => getComputedStyle(el).position)).not.toBe("fixed");
    expect(await noSidewaysScroll(page)).toBeLessThanOrEqual(0);
  });

  test("the two choices and the send button share one row of the message card", async ({ page, request }) => {
    await resetMockSessions(request);
    await loginAsDev(page, DEV_USERS.secondary);
    await hydrated(page);

    const card = (await page.getByTestId("start-view").locator("form > div").first().boundingBox())!;
    const background = (await page.getByTestId("chat-background").boundingBox())!;
    const pace = (await page.getByTestId("chat-pace").boundingBox())!;
    const button = (await page.getByTestId("start-view").getByRole("button", { name: "Lähetä" }).boundingBox())!;
    // Side by side inside the card, in that order, none over another.
    const middle = (box: { y: number; height: number }) => box.y + box.height / 2;
    expect(Math.abs(middle(background) - middle(pace))).toBeLessThan(2);
    expect(Math.abs(middle(pace) - middle(button))).toBeLessThan(2);
    expect(background.x).toBeGreaterThanOrEqual(card.x);
    expect(background.x + background.width).toBeLessThanOrEqual(pace.x);
    expect(pace.x + pace.width).toBeLessThanOrEqual(button.x);
    expect(button.x + button.width).toBeLessThanOrEqual(card.x + card.width);
    expect(await noSidewaysScroll(page)).toBeLessThanOrEqual(0);

    // The longest pair of choices on a narrow phone: the pills give way, and none reaches the send button.
    await choose(page, "chat-background", "En ole tekninen");
    await choose(page, "chat-pace", "Perusteellinen");
    await page.setViewportSize({ width: 360, height: 780 });
    const tight = {
      background: (await page.getByTestId("chat-background").boundingBox())!,
      pace: (await choicePill(page, "chat-pace").boundingBox())!,
      send: (await page.getByTestId("start-view").getByRole("button", { name: "Lähetä" }).boundingBox())!,
    };
    expect(tight.background.x + tight.background.width).toBeLessThanOrEqual(tight.pace.x);
    expect(tight.pace.x + tight.pace.width).toBeLessThanOrEqual(tight.send.x);
    expect(await noSidewaysScroll(page)).toBeLessThanOrEqual(0);
    await choose(page, "chat-pace", "Nopea");
    await page.setViewportSize({ width: 390, height: 844 });

    // Each pill names its choice, also where it is drawn as its icon alone, and its menu stays on the screen.
    const pill = choicePill(page, "chat-pace");
    await expect(pill).toHaveAccessibleName("Kysymysten määrä: Nopea");
    await pill.click();
    const menu = (await page.getByTestId("chat-pace").getByRole("menu").boundingBox())!;
    expect(menu.x).toBeGreaterThanOrEqual(0);
    expect(menu.x + menu.width).toBeLessThanOrEqual(390);
    await choose(page, "chat-pace", "Perusteellinen");
    await expect(pill).toHaveAccessibleName("Kysymysten määrä: Perusteellinen");
    await expect(startField(page)).toHaveValue("");
  });
});

test.describe("session start in the chat", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test.beforeEach(async ({ request }) => {
    await resetMockSessions(request);
  });

  test("a new session opens on the chat, with the cursor in its field", async ({ page }) => {
    await newLiveSession(page);

    const chat = page.getByRole("main", { name: "Keskustelu" });
    await expect(chat).toBeVisible();
    await expect(page.getByRole("heading", { name: "Mitä haluat ratkaista?" })).toBeVisible();
    await expect(field(page)).toBeFocused();

    // No workspace beside it, and nothing to dock or close.
    await expect(page.getByTestId("workspace-phase")).toHaveCount(0);
    await expect(page.getByTestId("chat-dock-toggle")).toHaveCount(0);
    await expect(page.getByTestId("chat-resize")).toHaveCount(0);

    // The field sits on the middle line of the space beside the steps.
    const box = (await chat.boundingBox())!;
    const input = (await field(page).boundingBox())!;
    const middle = input.x + input.width / 2;
    expect(Math.abs(middle - (box.x + box.width / 2))).toBeLessThan(40);
    expect(await noSidewaysScroll(page)).toBeLessThanOrEqual(0);
  });

  test("an example fills the field with its prompt alone and steps back for the user's own words", async ({
    page,
  }) => {
    await newLiveSession(page);
    const input = field(page);
    const examples = page.getByTestId("chat-examples");

    // The background choice puts nothing into the field, before an example or after it.
    await choose(page, "chat-background", "En ole tekninen");
    await expect(choicePill(page, "chat-background")).toHaveAccessibleName("Taustasi: En ole tekninen");
    await expect(input).toHaveValue("");
    const invoice = examples.getByRole("button", { name: "Laskun kentät" });
    await invoice.click();
    await expect(invoice).toHaveAttribute("aria-pressed", "true");
    await expect(input).toHaveValue("Haluamme poimia toimittajien PDF-laskuista keskeiset kentät.");
    await expect(input).toBeFocused();
    await choose(page, "chat-background", "Tekninen");
    await expect(input).toHaveValue("Haluamme poimia toimittajien PDF-laskuista keskeiset kentät.");
    await expect(invoice).toHaveAttribute("aria-pressed", "true");

    // Another example takes its place; nothing is sent.
    await examples.getByRole("button", { name: "Kysymykset ohjeista" }).click();
    await expect(input).toHaveValue(
      "Haluamme avustajan, joka vastaa kysymyksiin sisäisten ohjeidemme pohjalta.",
    );
    await expect(page.getByTestId("chat-message")).toHaveCount(0);

    // The user's own words: the examples step back, and the field stays put.
    const before = (await input.boundingBox())!;
    await input.fill("Lajittelemme asiakkaiden sähköpostit käsin.");
    await expect(examples).toBeHidden();
    const after = (await input.boundingBox())!;
    expect(after.y).toBe(before.y);

    await input.fill("");
    await expect(examples).toBeVisible();
  });

  test("the first message starts the conversation, and the workspace comes in at the specification", async ({
    page,
    request,
    baseURL,
  }) => {
    const id = await newLiveSession(page);
    const input = field(page);

    await input.fill("Lajittelemme asiakkaiden sähköpostit käsin.");
    await input.press("Enter");
    await expect(page.getByTestId("chat-start")).toHaveCount(0);
    await expect(send(page)).toBeEnabled({ timeout: 30_000 });
    await expect(page.getByTestId("chat-message")).toHaveCount(2);
    // Still the page: the wizard is gathering requirements.
    await expect(page.getByRole("main", { name: "Keskustelu" })).toBeVisible();
    await expect(page.getByTestId("workspace-phase")).toHaveCount(0);
    // The field is at the bottom of the conversation now.
    const input1 = (await input.boundingBox())!;
    expect(input1.y).toBeGreaterThan(700);

    // The wizard moves the session on during a reply; the page follows when
    // the reply ends, and the conversation keeps what was said. Marked here,
    // the chat and its log are the same elements once docked: a chat built
    // again would have lost a reply that was still arriving.
    await page.getByTestId("chat-dock").evaluate((el) => el.setAttribute("data-e2e-kept", "1"));
    await page.getByRole("log").evaluate((el) => el.setAttribute("data-e2e-kept", "1"));
    await setMockSessionStep(request, baseURL!, id, 3);
    await input.fill("Kentät: lähettäjä, aihe ja kiireellisyys.");
    await input.press("Enter");
    await expect(page.getByTestId("workspace-phase")).toHaveText("Spesifikaatio", {
      timeout: 30_000,
    });
    const docked = page.getByRole("complementary", { name: "Keskustelu" });
    await expect(docked).toBeVisible();
    await expect(docked.getByTestId("chat-message")).toHaveCount(4);
    await expect(docked).toHaveAttribute("data-e2e-kept", "1");
    await expect(docked.getByRole("log")).toHaveAttribute("data-e2e-kept", "1");
    await expect(docked.getByTestId("chat-dock-toggle")).toBeVisible();
    expect(await noSidewaysScroll(page)).toBeLessThanOrEqual(0);
  });

  test("with the mock store's checklist the chat stays docked beside it", async ({ page }) => {
    await loginAsDev(page);
    await createSession(page, `checklist ${Date.now()}`);

    await expect(page.getByTestId("workspace-phase")).toBeVisible();
    await expect(page.getByRole("complementary", { name: "Keskustelu" })).toBeVisible();
    await expect(page.getByTestId("chat-start")).toHaveCount(0);
  });
});

test.describe("session start in the chat on a phone", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test.beforeEach(async ({ request }) => {
    await resetMockSessions(request);
  });

  test("the chat is the page, not a sheet over it, and the steps open above it", async ({
    page,
  }) => {
    await newLiveSession(page);

    const chat = page.getByRole("main", { name: "Keskustelu" });
    await expect(chat).toBeVisible();
    expect(await chat.evaluate((el) => getComputedStyle(el).position)).not.toBe("fixed");
    await expect(page.getByRole("heading", { name: "Mitä haluat ratkaista?" })).toBeVisible();
    await expect(page.getByTestId("chat-examples").getByRole("button")).toHaveCount(4);
    expect(await noSidewaysScroll(page)).toBeLessThanOrEqual(0);

    // The steps column is hidden here; the step line opens the list. The
    // start view no longer fits under it: it starts below the list and
    // scrolls in its own box, instead of being drawn over the steps.
    await page.getByTestId("steps-disclosure").click();
    const steps = page.getByRole("navigation", { name: "Vaiheet" });
    await expect(steps).toBeVisible();
    const list = (await steps.boundingBox())!;
    const heading = page.getByRole("heading", { name: "Mitä haluat ratkaista?" });
    const top = (await heading.boundingBox())!;
    expect(top.y).toBeGreaterThanOrEqual(list.y + list.height);
    // Everything in the start view can be reached: the last line scrolls into view.
    const notice = page.getByTestId("chat-ai-notice");
    await notice.scrollIntoViewIfNeeded();
    await expect(notice).toBeInViewport();
    expect(await noSidewaysScroll(page)).toBeLessThanOrEqual(0);
    expect(
      await page.evaluate(() => document.scrollingElement!.scrollHeight - window.innerHeight),
    ).toBeLessThanOrEqual(0);
  });
});
