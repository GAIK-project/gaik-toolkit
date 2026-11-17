import { test, expect, type Page, type Route } from "@playwright/test";
import { loginAsDev } from "./helpers/auth";
import { resetMockSessions } from "./helpers/mock";
import { createSession } from "./helpers/session";

/**
 * Answering a round of the wizard's questions one field per question, and the
 * chat and the steps on a phone. The wizard's replies are faked here: the
 * chat request is answered by the test, so a round of questions, a busy
 * wizard and a slow reply can each be produced on demand.
 */

async function newSession(page: Page) {
  await loginAsDev(page);
  await createSession(page, `questions ${Date.now()}`);
}

/** One reply as the chat route streams it. */
const reply = (text: string) => ({
  status: 200,
  contentType: "text/event-stream; charset=utf-8",
  body: `data: ${JSON.stringify({ delta: text })}\n\ndata: ${JSON.stringify({ done: true })}\n\n`,
});
const BUSY = { status: 409, contentType: "application/json", body: "{}" };

/**
 * Answers the chat requests of the page: `answer` gets the message sent and
 * how many came before it. Returns the messages the page has sent, in order.
 */
async function fakeWizard(
  page: Page,
  answer: (message: string, earlier: number) => Parameters<Route["fulfill"]>[0] | Promise<Parameters<Route["fulfill"]>[0]>,
): Promise<string[]> {
  const sent: string[] = [];
  await page.route("**/api/sessions/*/chat", async (route) => {
    if (route.request().method() !== "POST") return route.fallback();
    const message = (route.request().postDataJSON() as { message: string }).message;
    sent.push(message);
    await route.fulfill(await answer(message, sent.length - 1));
  });
  return sent;
}

// The first item is not a question, so the agent's numbers (2–4) differ from
// the questions' places in the form; the last lines only look like questions.
const ROUND = [
  "Kiitos! Tarkennan vielä muutaman asian:",
  "",
  "1. Taustaksi: tiedot viedään lopuksi ERP:hen.",
  "2. Missä muodossa ostotilaukset saapuvat?",
  "3. Mitä järjestelmiä käytätte?",
  "4. Kuinka monta tilausta käsittelette päivässä?",
  "",
  "Esimerkkikutsu:",
  "",
  "```",
  "- curl https://example.com/haku?q=tilaus",
  "```",
  "",
  "- Rajapinnan kuvaus: https://example.com/api?versio=2",
].join("\n");

const ANSWERS = [
  "Vastaukseni kysymyksiisi (kysymykset lainattuina):",
  '2. "Missä muodossa ostotilaukset saapuvat?": PDF sähköpostilla',
  '3. "Mitä järjestelmiä käytätte?": SAP',
  "   Lemonsoft",
  '4. "Kuinka monta tilausta käsittelette päivässä?": ohita',
].join("\n");

const chatField = (page: Page) => page.locator('textarea[name="message"]');
const messages = (page: Page) => page.getByTestId("chat-message");
const ownMessages = (page: Page) => page.locator('[data-testid="chat-message"][data-role="user"]');

/** Asks for the round of questions and fills in the answer fields. */
async function openRoundAndAnswer(page: Page) {
  await chatField(page).fill("Haluan automatisoida ostotilausten käsittelyn.");
  await chatField(page).press("Enter");
  // The answer fields are there as soon as the wizard has asked.
  const form = page.getByTestId("chat-questions");
  await expect(form).toBeVisible();
  await expect(page.getByTestId("chat-questions-open")).toHaveCount(0);
  await form.getByLabel("2. Missä muodossa ostotilaukset saapuvat?").fill("PDF sähköpostilla");
  await form.getByLabel("3. Mitä järjestelmiä käytätte?").fill("SAP\nLemonsoft");
  await expect(form.getByLabel("4. Kuinka monta tilausta käsittelette päivässä?")).toHaveValue("");
  return form;
}

test.describe("answering a round of questions", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test.beforeEach(async ({ request }) => {
    await resetMockSessions(request);
  });

  test("the answers go as one message under the agent's own numbers", async ({ page }) => {
    const sent = await fakeWizard(page, (_message, earlier) =>
      reply(earlier === 0 ? ROUND : "Kiitos, kirjasin vastauksesi."),
    );
    await newSession(page);
    const form = await openRoundAndAnswer(page);

    await form.getByRole("button", { name: "Lähetä vastaukset" }).click();
    await expect(messages(page).last()).toContainText("Kiitos, kirjasin vastauksesi.");
    expect(sent[1]).toBe(ANSWERS);
    // The answers are in the conversation as the user's message, and the
    // form is gone with the round it answered.
    await expect(ownMessages(page).filter({ hasText: "PDF sähköpostilla" })).toHaveCount(1);
    await expect(page.getByTestId("chat-questions")).toHaveCount(0);
    await expect(page.getByTestId("chat-questions-open")).toHaveCount(0);
  });

  test("Close folds the fields away, and they open again with what was written", async ({ page }) => {
    await fakeWizard(page, () => reply(ROUND));
    await newSession(page);
    const form = await openRoundAndAnswer(page);

    await form.getByRole("button", { name: "Sulje" }).click();
    await expect(form).toHaveCount(0);
    const open = page.getByTestId("chat-questions-open");
    await expect(open).toHaveText("Vastaa kysymyksiin yksitellen (3)");

    await open.click();
    await expect(
      page.getByTestId("chat-questions").getByLabel("2. Missä muodossa ostotilaukset saapuvat?"),
    ).toHaveValue("PDF sähköpostilla");
  });

  test("answers that could not be sent stay in the form, which says so", async ({ page }) => {
    let busy = true;
    const sent = await fakeWizard(page, (_message, earlier) =>
      earlier === 0 ? reply(ROUND) : busy ? BUSY : reply("Kiitos, kirjasin vastauksesi."),
    );
    await newSession(page);
    const form = await openRoundAndAnswer(page);
    const first = form.getByLabel("2. Missä muodossa ostotilaukset saapuvat?");
    const second = form.getByLabel("3. Mitä järjestelmiä käytätte?");
    const send = form.getByRole("button", { name: "Lähetä vastaukset" });

    // The wizard is busy with another turn: the send waits and tries again
    // every five seconds for a minute. The test turns that minute over.
    await page.clock.install();
    await send.click();
    await expect.poll(() => sent.length).toBe(2);
    // While the answers are on their way the form is still there with them.
    await expect(form).toBeVisible();
    await expect(send).toHaveAttribute("aria-busy", "true");
    await expect(first).toHaveValue("PDF sähköpostilla");
    for (let attempt = 1; attempt <= 12; attempt++) {
      await page.clock.fastForward(5000);
      await expect.poll(() => sent.length).toBe(2 + attempt);
    }

    await expect(form.getByRole("alert")).toContainText("Vastauksiasi ei lähetetty, ja ne ovat tallessa tässä.");
    await expect(form.getByRole("alert")).toContainText("Wizard vastaa vielä edelliseen viestiin");
    await expect(first).toHaveValue("PDF sähköpostilla");
    await expect(second).toHaveValue("SAP\nLemonsoft");
    // What was not sent is not left in the conversation as if it had been.
    await expect(ownMessages(page).filter({ hasText: "PDF sähköpostilla" })).toHaveCount(0);
    await expect(messages(page).last()).toContainText("Kuinka monta tilausta käsittelette päivässä?");

    // The wizard is free again: the same answers go from the same form.
    busy = false;
    await send.click();
    await expect(messages(page).last()).toContainText("Kiitos, kirjasin vastauksesi.");
    expect(sent[sent.length - 1]).toBe(ANSWERS);
    await expect(page.getByTestId("chat-questions")).toHaveCount(0);
  });
});

test.describe("the chat and the steps on a phone", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test.beforeEach(async ({ request }) => {
    await resetMockSessions(request);
  });

  test("a chat closed in the middle of a reply shows the reply when opened again", async ({ page }) => {
    let finish: () => void = () => {};
    const finished = new Promise<void>((resolve) => (finish = resolve));
    const sent = await fakeWizard(page, async () => {
      await finished;
      return reply("Selvä, jatketaan siitä.");
    });
    await newSession(page);
    const dock = page.getByTestId("chat-dock");

    await chatField(page).fill("Haluan automatisoida ostotilausten käsittelyn.");
    await chatField(page).press("Enter");
    await expect.poll(() => sent.length).toBe(1);
    await page.getByTestId("chat-dock-toggle").click();
    await expect(dock).toHaveAttribute("data-chat-open", "false");
    await expect(dock).toBeHidden();

    await page.locator("[data-open-chat]").first().click();
    await expect(dock).toHaveAttribute("data-chat-open", "true");
    await expect(ownMessages(page).filter({ hasText: "Haluan automatisoida ostotilausten käsittelyn." })).toBeVisible();
    finish();
    await expect(messages(page).last()).toContainText("Selvä, jatketaan siitä.");
    await expect(messages(page).last()).toBeInViewport();
  });

  test("the steps opened under the title leave the step's view in the window", async ({ page }) => {
    await newSession(page);
    await page.getByTestId("chat-dock-toggle").click();
    await page.getByTestId("steps-disclosure").click();
    const steps = page.getByRole("navigation", { name: "Vaiheet" });
    const closed = steps.locator('button[aria-expanded="false"]');
    while ((await closed.count()) > 0) await closed.first().click();

    // Every stage is open: the list scrolls inside its card, and the step's
    // title and view below it are still in the window.
    expect(await steps.evaluate((el) => el.scrollHeight - el.clientHeight)).toBeGreaterThan(0);
    const title = page.getByTestId("workspace-phase");
    await expect(title).toBeInViewport({ ratio: 1 });
    const below = await title.evaluate((el) => window.innerHeight - el.getBoundingClientRect().bottom);
    expect(below).toBeGreaterThan(150);
  });
});

test.describe("skipping a question with its button", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test.beforeEach(async ({ request }) => {
    await resetMockSessions(request);
  });

  test("a round can be sent with every question skipped, and a skip can be taken back", async ({
    page,
  }) => {
    await newSession(page);
    const sent = await fakeWizard(page, (_message, earlier) =>
      reply(earlier === 0 ? ROUND : "Selvä, käytän oletuksia."),
    );
    await chatField(page).fill("Haluamme käsitellä ostotilaukset.");
    await chatField(page).press("Enter");

    const form = page.getByTestId("chat-questions");
    await expect(form).toBeVisible();
    await expect(form.locator("ol > li")).toHaveCount(3);
    // Each button is described by its question.
    await expect(form.getByTestId("chat-question-skip-0")).toHaveAccessibleDescription(
      "2. Missä muodossa ostotilaukset saapuvat?",
    );

    // Nothing answered or skipped yet: nothing to send.
    const send = form.getByRole("button", { name: "Lähetä vastaukset" });
    await expect(send).toBeDisabled();

    // Skipping takes what was typed out of the answer, and can be taken back.
    const first = form.locator("textarea").nth(0);
    await first.fill("PDF sähköpostilla");
    const skipFirst = form.getByTestId("chat-question-skip-0");
    await skipFirst.click();
    await expect(skipFirst).toHaveAttribute("aria-pressed", "true");
    await expect(first).toBeDisabled();
    await expect(first).toHaveValue("");
    await skipFirst.click();
    await expect(first).toHaveValue("PDF sähköpostilla");
    await skipFirst.click();

    await form.getByTestId("chat-question-skip-1").click();
    await form.getByTestId("chat-question-skip-2").click();
    await expect(send).toBeEnabled();
    await send.click();

    await expect.poll(() => sent.length).toBe(2);
    expect(sent[1]).toBe(
      [
        "Vastaukseni kysymyksiisi (kysymykset lainattuina):",
        '2. "Missä muodossa ostotilaukset saapuvat?": ohita',
        '3. "Mitä järjestelmiä käytätte?": ohita',
        '4. "Kuinka monta tilausta käsittelette päivässä?": ohita',
      ].join("\n"),
    );
  });
});

// Two questions list their answers as bullets; the third is free text.
const OPTION_ROUND = [
  "Tarkennan muutaman asian:",
  "",
  "1. Missä muodossa ostotilaukset saapuvat?",
  "   - PDF sähköpostilla",
  "   - Skannattuna paperina",
  "   - EDI-sanomana",
  "2. Kuka tarkistaa poimitut tiedot?",
  "   - Ostaja",
  "   - Talousosasto",
  "3. Kuinka monta tilausta käsittelette päivässä?",
].join("\n");

test.describe("choosing among the answers a question lists", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test.beforeEach(async ({ request }) => {
    await resetMockSessions(request);
  });

  test("the options are choices under their question: one press chooses, and the chosen one says so", async ({
    page,
  }) => {
    const sent = await fakeWizard(page, (_message, earlier) =>
      reply(earlier === 0 ? OPTION_ROUND : "Kiitos, kirjasin vastauksesi."),
    );
    await newSession(page);
    await chatField(page).fill("Haluan automatisoida ostotilausten käsittelyn.");
    await chatField(page).press("Enter");

    // The form says it is the place to answer, and is named by that.
    const form = page.getByRole("form", { name: "Vastaa tässä" });
    await expect(form).toBeVisible();

    // The options are a group named by their question, each a button that is
    // off until pressed, tall enough to hit and with the hand cursor.
    const options = form.getByRole("group", { name: "1. Missä muodossa ostotilaukset saapuvat?" });
    await expect(options.getByRole("button")).toHaveText(["PDF sähköpostilla", "Skannattuna paperina", "EDI-sanomana"]);
    const pdf = options.getByRole("button", { name: "PDF sähköpostilla" });
    const edi = options.getByRole("button", { name: "EDI-sanomana" });
    await expect(pdf).toHaveAttribute("aria-pressed", "false");
    await expect(pdf).toHaveCSS("cursor", "pointer");
    expect((await pdf.boundingBox())!.height).toBeGreaterThanOrEqual(32);
    // An edge that is seen at rest, not only under the pointer.
    await expect(pdf).toHaveCSS("border-top-color", "rgb(135, 145, 167)");

    // Chosen: pressed, filled, and its words are the answer in the field.
    const first = form.getByRole("textbox", { name: "1. Missä muodossa ostotilaukset saapuvat?" });
    await expect(first).toHaveAttribute("placeholder", "Tai kirjoita oma vastaus");
    await pdf.click();
    await expect(pdf).toHaveAttribute("aria-pressed", "true");
    await expect(pdf).toHaveCSS("background-color", "rgb(230, 241, 250)");
    await expect(first).toHaveValue("PDF sähköpostilla");
    // Another option takes its place; the same one again takes the answer back.
    await edi.click();
    await expect(edi).toHaveAttribute("aria-pressed", "true");
    await expect(pdf).toHaveAttribute("aria-pressed", "false");
    await edi.click();
    await expect(edi).toHaveAttribute("aria-pressed", "false");
    await expect(first).toHaveValue("");
    await pdf.click();

    // From the keyboard: Tab reaches the next option, Space presses it, and
    // the focus is drawn on it.
    await pdf.focus();
    await page.keyboard.press("Tab");
    const scanned = options.getByRole("button", { name: "Skannattuna paperina" });
    await expect(scanned).toBeFocused();
    expect(await scanned.evaluate((el) => getComputedStyle(el).boxShadow)).not.toBe("none");
    await page.keyboard.press("Space");
    await expect(scanned).toHaveAttribute("aria-pressed", "true");

    // Skip is a button with an edge of its own, pressed once it is on.
    const skip = form.getByTestId("chat-question-skip-2");
    await expect(skip).toHaveCSS("border-top-width", "1px");
    expect((await skip.boundingBox())!.height).toBeGreaterThanOrEqual(32);
    await skip.click();
    await expect(skip).toHaveAttribute("aria-pressed", "true");

    await form.getByRole("group", { name: "2. Kuka tarkistaa poimitut tiedot?" }).getByRole("button", { name: "Ostaja" }).click();
    await form.getByRole("button", { name: "Lähetä vastaukset" }).click();
    await expect.poll(() => sent.length).toBe(2);
    expect(sent[1]).toBe(
      [
        "Vastaukseni kysymyksiisi (kysymykset lainattuina):",
        '1. "Missä muodossa ostotilaukset saapuvat?": Skannattuna paperina',
        '2. "Kuka tarkistaa poimitut tiedot?": Ostaja',
        '3. "Kuinka monta tilausta käsittelette päivässä?": ohita',
      ].join("\n"),
    );
  });
});

test.describe("the choices under a finger", () => {
  test.use({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true });

  test.beforeEach(async ({ request }) => {
    await resetMockSessions(request);
  });

  test("options, Skip, the checklist's buttons and the examples are 44 px to press", async ({ page }) => {
    await loginAsDev(page);
    expect(await page.evaluate(() => window.matchMedia("(pointer: coarse)").matches)).toBe(true);
    // The start view's examples and the two choices beside the field.
    const tall = async (name: string, control: ReturnType<Page["locator"]>) =>
      expect((await control.boundingBox())!.height, name).toBeGreaterThanOrEqual(44);
    await tall("example", page.getByTestId("chat-examples").getByRole("button").first());
    await tall("background", page.getByTestId("chat-background").getByRole("button"));

    await fakeWizard(page, () => reply(OPTION_ROUND));
    await createSession(page, `touch ${Date.now()}`);
    await chatField(page).fill("Haluan automatisoida ostotilausten käsittelyn.");
    await chatField(page).press("Enter");
    const form = page.getByTestId("chat-questions");
    await expect(form).toBeVisible();
    await tall("option", form.getByRole("button", { name: "PDF sähköpostilla" }));
    await tall("skip", form.getByTestId("chat-question-skip-0"));

    // Behind the chat: the checklist's button, and the steps' button, which
    // stays small beside the title and is pressed from 44 px around it.
    await page.getByTestId("chat-dock-toggle").tap();
    await tall("answer in the chat", page.getByTestId("requirement-ask-1"));
    const steps = page.getByTestId("steps-disclosure");
    await expect(steps).toHaveCSS("border-top-width", "1px");
    const reach = await steps.evaluate((el) => parseFloat(getComputedStyle(el, "::after").height));
    expect(reach).toBeGreaterThanOrEqual(44);
  });
});
