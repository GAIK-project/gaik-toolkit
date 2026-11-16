import { test, expect, type Page } from "@playwright/test";
import { loginAsDev } from "./helpers/auth";
import { resetMockSessions } from "./helpers/mock";
import { createSession } from "./helpers/session";
import { PACE_SENTENCES } from "../lib/chat-background";

/**
 * The chat's one composer: a reference chip for "ask about this" from the page
 * (CHAT_REFERENCE_EVENT in lib/chat-events.ts), a checklist point answered in
 * the chat, the background and pace choices of an empty chat, the header hint and the AI
 * notice, a gate approval shown as an event line, and links in a reply.
 */

/** The line the user's first message carries when nothing is chosen: the
 *  default pace (lib/chat-background). It goes ahead of what they sent. */
const QUICK = PACE_SENTENCES.fi.quick;

const REFERENCE_EVENT = "gaik-wizard:chat-reference";
const SEND_EVENT = "gaik-wizard:chat-send";

type Reference = { key: string; label: string; prefix: string; draft?: string };

async function newSession(page: Page) {
  await page.goto("/");
  await createSession(page, `chat ${Date.now()}`);
}

// Answers POST /chat as wizard_api streams it, and collects what was sent.
async function fakeChat(page: Page, events: object[] = [{ delta: "Selvä." }, { done: true }]) {
  const sent: string[] = [];
  const body = events.map((e) => `data: ${JSON.stringify(e)}\n\n`).join("");
  await page.route("**/api/sessions/*/chat", (route) => {
    if (route.request().method() !== "POST") return route.continue();
    sent.push((route.request().postDataJSON() as { message: string }).message);
    return route.fulfill({ status: 200, contentType: "text/event-stream", body });
  });
  return sent;
}

// What askInChat does, from anywhere on the page.
async function ask(page: Page, reference: Reference) {
  await page.evaluate(
    ([name, detail]) => window.dispatchEvent(new CustomEvent(name as string, { detail })),
    [REFERENCE_EVENT, reference] as const,
  );
}

const field = (page: Page) => page.locator('textarea[name="message"]');
const chip = (page: Page) => page.getByTestId("chat-reference");
const userMessages = (page: Page) => page.locator('[data-testid="chat-message"][data-role="user"]');

const STEP: Reference = {
  key: "step:classify",
  label: "Vaihe 3 · Luokittelu",
  prefix: 'Koskee prosessin vaihetta 3 (id classify), lainattuna: "Luokittelu"',
};

test.describe("the chat composer", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test.beforeEach(async ({ page, request }) => {
    await resetMockSessions(request);
    await loginAsDev(page);
  });

  test("a reference from the page is a chip, and the message starts with its line", async ({ page }) => {
    await newSession(page);
    const sent = await fakeChat(page);

    await ask(page, STEP);
    await expect(chip(page)).toContainText("Vaihe 3 · Luokittelu");
    await expect(field(page)).toBeFocused();

    // A chip alone sends nothing.
    await field(page).press("Enter");
    await expect(chip(page)).toBeVisible();
    expect(sent).toEqual([]);

    // Another item takes the chip's place, and its draft goes into the field.
    await ask(page, {
      key: "gate:9",
      label: "Gate 2 · Ratkaisun rakenne",
      prefix: "Muutospyyntö ennen Gate 2:n (Ratkaisun rakenne) hyväksyntää:",
      draft: "Lisää ",
    });
    await expect(chip(page)).toHaveCount(1);
    await expect(chip(page)).toContainText("Gate 2 · Ratkaisun rakenne");
    await expect(field(page)).toHaveValue("Lisää ");
    await expect(field(page)).toBeFocused();

    await field(page).pressSequentially("tarkistusvaihe.");
    await field(page).press("Enter");
    await expect
      .poll(() => sent)
      // The session's first message: the pace line, then the chip's line and the words.
      .toEqual([`${QUICK}\nMuutospyyntö ennen Gate 2:n (Ratkaisun rakenne) hyväksyntää:\n\nLisää tarkistusvaihe.`]);
    await expect(chip(page)).toHaveCount(0);
    await expect(userMessages(page).last()).toContainText("Lisää tarkistusvaihe.");
    await expect(page.locator('[data-testid="chat-message"][data-role="assistant"]').last()).toContainText("Selvä.");

    // A chip the user removes leaves an ordinary message.
    await ask(page, STEP);
    await page.getByTestId("chat-reference-remove").click();
    await expect(chip(page)).toHaveCount(0);
    await expect(field(page)).toBeFocused();
    await field(page).fill("Kiitos");
    await field(page).press("Enter");
    await expect.poll(() => sent[1]).toBe("Kiitos");
  });

  test("a draft does not replace what the user has typed", async ({ page }) => {
    await newSession(page);
    await field(page).fill("Kesken oleva ajatus");
    await ask(page, { ...STEP, draft: "Muuta " });
    await expect(chip(page)).toBeVisible();
    await expect(field(page)).toHaveValue("Kesken oleva ajatus");
  });

  test("a reference opens a closed chat", async ({ page }) => {
    await newSession(page);
    const dock = page.getByTestId("chat-dock");
    await page.getByTestId("chat-dock-toggle").click();
    await expect(dock).toHaveAttribute("data-chat-open", "false");

    await ask(page, STEP);
    await expect(dock).toHaveAttribute("data-chat-open", "true");
    await expect(chip(page)).toBeVisible();
    await expect(field(page)).toBeFocused();
  });

  test("a checklist point is answered in the chat, quoted as data", async ({ page }) => {
    await newSession(page);
    const sent = await fakeChat(page);

    // One composer: the checklist has no field of its own.
    await expect(page.locator("textarea")).toHaveCount(1);
    await page.getByTestId("requirement-ask-2").click();
    await expect(chip(page)).toContainText("Kohta 2 · Who will use the system?");
    await expect(field(page)).toBeFocused();

    await field(page).pressSequentially("Asiakaspalvelu");
    await field(page).press("Enter");
    await expect
      .poll(() => sent)
      .toEqual([
        `${QUICK}\nVastaus tarkistuslistan kohtaan 2, lainattuna: "Who will use the system?"\n\nAsiakaspalvelu`,
      ]);
    await expect(chip(page)).toHaveCount(0);
  });

  test("an answer the wizard was too busy to take comes back with its chip", async ({ page }) => {
    await newSession(page);
    await page.route("**/api/sessions/*/chat", (route) =>
      route.request().method() === "POST"
        ? route.fulfill({ status: 409, contentType: "application/json", body: "{}" })
        : route.continue(),
    );
    await page.getByTestId("requirement-ask-2").click();
    await field(page).pressSequentially("Asiakaspalvelu");
    await field(page).press("Enter");

    // Said above the field; no bubble is left for an answer that was not taken.
    await expect(page.getByTestId("chat-busy-note")).toContainText("Wizard vastaa vielä edelliseen viestiin");
    await expect(page.getByRole("log")).not.toContainText("Asiakaspalvelu");
    await expect(chip(page)).toContainText("Kohta 2");
    await expect(field(page)).toHaveValue("Asiakaspalvelu");
  });

  test("what the user writes while an answer fails to send is not replaced by the old answer", async ({ page }) => {
    await newSession(page);
    let refuse: () => void = () => {};
    const refused = new Promise<void>((resolve) => (refuse = resolve));
    await page.route("**/api/sessions/*/chat", async (route) => {
      if (route.request().method() !== "POST") return route.continue();
      await refused;
      return route.fulfill({ status: 409, contentType: "application/json", body: "{}" });
    });
    await page.getByTestId("requirement-ask-2").click();
    await field(page).pressSequentially("Asiakaspalvelu");
    await field(page).press("Enter");
    await expect(field(page)).toHaveValue("");
    await field(page).pressSequentially("Ja vielä laskutus");
    refuse();

    await expect(page.getByTestId("chat-busy-note")).toContainText("Wizard vastaa vielä edelliseen viestiin");
    await expect(field(page)).toHaveValue("Ja vielä laskutus");
  });

  test("the waiting line says that the wizard is starting when the answer is late", async ({ page }) => {
    await newSession(page);
    // wizard_api answers a message only once the wizard is up: held back
    // here, as it is while a wizard released after a break starts again.
    let answer: () => void = () => {};
    const up = new Promise<void>((resolve) => (answer = resolve));
    await page.route("**/api/sessions/*/chat", async (route) => {
      if (route.request().method() !== "POST") return route.continue();
      await up;
      return route.fulfill({
        status: 200,
        contentType: "text/event-stream",
        body: `data: ${JSON.stringify({ delta: "Selvä." })}\n\ndata: ${JSON.stringify({ done: true })}\n\n`,
      });
    });
    await field(page).fill("Jatketaan");
    await field(page).press("Enter");

    const line = page.getByTestId("chat-activity");
    await expect(line).toHaveText("Wizard miettii…");
    // The same line, with other words: nothing is added beside it.
    await expect(line).toHaveText("Wizard käynnistyy. Tämä kestää hetken.", { timeout: 10_000 });
    await expect(line).toHaveCount(1);

    answer();
    await expect(page.getByRole("log")).toContainText("Selvä.");
    await expect(line).toHaveCount(0);
  });

  test("a wizard that is busy is not said to be starting while the message waits to be sent again", async ({ page }) => {
    await newSession(page);
    // The first answer is late (the line turns to "starting") and then says
    // the wizard is answering another message; the page waits and sends again.
    let posts = 0;
    let answer: () => void = () => {};
    const up = new Promise<void>((resolve) => (answer = resolve));
    await page.route("**/api/sessions/*/chat", async (route) => {
      if (route.request().method() !== "POST") return route.continue();
      posts += 1;
      if (posts === 1) {
        await new Promise((r) => setTimeout(r, 4000));
        return route.fulfill({ status: 409, contentType: "application/json", body: "{}" });
      }
      await up;
      return route.fulfill({
        status: 200,
        contentType: "text/event-stream",
        body: `data: ${JSON.stringify({ delta: "Selvä." })}

data: ${JSON.stringify({ done: true })}

`,
      });
    });
    // A message from the page waits for a busy wizard (a typed one is refused).
    await page.evaluate(
      ([name, detail]) => window.dispatchEvent(new CustomEvent(name, { detail })),
      [SEND_EVENT, "Jatketaan"] as const,
    );

    const line = page.getByTestId("chat-activity");
    await expect(line).toHaveText("Wizard käynnistyy. Tämä kestää hetken.", { timeout: 10_000 });
    // The 409 is in: the wizard is up and busy, and the wait says no start.
    await expect(line).toHaveText("Wizard miettii…", { timeout: 5_000 });
    await expect.poll(() => posts, { timeout: 10_000 }).toBe(2);
    // The second try has just gone out: nothing says a start yet.
    await expect(line).toHaveText("Wizard miettii…");

    answer();
    await expect(page.getByRole("log")).toContainText("Selvä.");
    await expect(line).toHaveCount(0);
  });

  test("the waiting line says at once that the wizard is starting when the session has none", async ({ page }) => {
    // The mock store's session that wizard_api reported without a wizard.
    await page.goto("/sessions/ses_wizard_released");
    let answer: () => void = () => {};
    const up = new Promise<void>((resolve) => (answer = resolve));
    await page.route("**/api/sessions/*/chat", async (route) => {
      if (route.request().method() !== "POST") return route.continue();
      await up;
      return route.fulfill({
        status: 200,
        contentType: "text/event-stream",
        body: `data: ${JSON.stringify({ delta: "Selvä." })}

data: ${JSON.stringify({ done: true })}

`,
      });
    });
    await field(page).fill("Jatketaan");
    await field(page).press("Enter");

    // Well inside the three seconds a late answer takes to say so.
    const line = page.getByTestId("chat-activity");
    await expect(line).toHaveText("Wizard käynnistyy. Tämä kestää hetken.", { timeout: 1500 });

    answer();
    await expect(page.getByRole("log")).toContainText("Selvä.");
    await expect(line).toHaveCount(0);
  });

  test("a message the page sends as it is still goes out as a chat turn", async ({ page }) => {
    await newSession(page);
    const sent = await fakeChat(page);
    const message = 'Hylkään Gate 1:n (Vaatimukset): "liian suppea"';
    await field(page).fill("Kesken");
    await page.evaluate(
      ([name, detail]) => window.dispatchEvent(new CustomEvent(name, { detail })),
      [SEND_EVENT, message] as const,
    );
    await expect.poll(() => sent).toEqual([message]);
    // What the user was typing stays in the field.
    await expect(field(page)).toHaveValue("Kesken");
  });

  test("an empty chat asks who the user is, and the answer leads the first message", async ({ page }) => {
    await newSession(page);
    const sent = await fakeChat(page);

    const empty = page.getByTestId("chat-empty");
    await expect(empty).toContainText("Hei! Olen tekoälyavustaja.");
    // One of two, in the tools row of the message field.
    const choice = page.getByRole("radiogroup", { name: "Taustasi" });
    const nonTechnical = choice.getByRole("radio", { name: "En ole tekninen" });
    const technical = choice.getByRole("radio", { name: "Tekninen", exact: true });

    // The choice is shown on the control; the field holds only what is typed.
    await nonTechnical.click();
    await expect(nonTechnical).toHaveAttribute("aria-checked", "true");
    await expect(field(page)).toHaveValue("");
    await expect(field(page)).toBeFocused();

    // The other one takes its place; pressing it again takes the choice back.
    await technical.click();
    await expect(technical).toHaveAttribute("aria-checked", "true");
    await expect(nonTechnical).toHaveAttribute("aria-checked", "false");
    await expect(field(page)).toHaveValue("");
    await technical.click();
    await expect(technical).toHaveAttribute("aria-checked", "false");
    await expect(field(page)).toHaveValue("");

    // Choosing leaves what is already written as it is.
    await field(page).pressSequentially("Haluan luokitella laskut.");
    await technical.click();
    await expect(technical).toHaveAttribute("aria-checked", "true");
    await expect(field(page)).toHaveValue("Haluan luokitella laskut.");

    // How much the wizard asks is chosen the same way: quick to begin with,
    // and nothing is written into the field.
    const pace = page.getByRole("radiogroup", { name: "Kysymysten määrä" });
    await expect(pace.getByRole("radio", { name: "Nopea" })).toHaveAttribute("aria-checked", "true");
    await pace.getByRole("radio", { name: "Perusteellinen" }).click();
    await expect(pace.getByRole("radio", { name: "Perusteellinen" })).toHaveAttribute("aria-checked", "true");
    await expect(field(page)).toHaveValue("Haluan luokitella laskut.");

    // The wizard gets the choices as the first lines of the first message,
    // the background and then the pace; the user's own bubble shows only
    // their words.
    await field(page).press("Enter");
    await expect.poll(() => sent.length).toBe(1);
    expect(sent[0].split("\n")).toEqual([
      expect.stringMatching(/^Taustani: olen tekninen\./),
      PACE_SENTENCES.fi.thorough,
      "Haluan luokitella laskut.",
    ]);
    await expect(userMessages(page)).toHaveText(["Haluan luokitella laskut."]);

    // The greeting and the choices belong to the empty chat only, and their
    // lines go with the first message alone.
    await expect(empty).toHaveCount(0);
    await expect(page.getByTestId("chat-background")).toHaveCount(0);
    await expect(page.getByTestId("chat-pace")).toHaveCount(0);
    await field(page).fill("Niitä tulee sata päivässä.");
    await field(page).press("Enter");
    await expect.poll(() => sent.length).toBe(2);
    expect(sent[1]).toBe("Niitä tulee sata päivässä.");

    // The choices are remembered for the next session; its field starts empty.
    await newSession(page);
    await expect(page.getByRole("radio", { name: "Tekninen", exact: true })).toHaveAttribute(
      "aria-checked",
      "true",
    );
    await expect(page.getByRole("radio", { name: "Perusteellinen" })).toHaveAttribute("aria-checked", "true");
    await expect(field(page)).toHaveValue("");
  });

  test("the AI notice is the second line of the docked chat's header, and stays with the folded chat", async ({
    page,
  }) => {
    // While gathering too: the header carries it from the first message on.
    await newSession(page);
    await expect(page.getByTestId("chat-ai-notice")).toBeInViewport();

    await page.goto("/sessions/ses_ui_basics");
    const notice = page.getByTestId("chat-ai-notice");
    await expect(notice).toHaveCount(1);
    await expect(notice).toHaveText("Vastaukset tuottaa tekoäly. Tarkista ne ennen käyttöä.");
    await expect(notice).toBeInViewport();
    // The line that used to say where changes are asked for is gone.
    await expect(page.getByTestId("chat-hint")).toHaveCount(0);
    // Under the chat's title and above the conversation; the field has no row under it.
    const title = (await page.getByTestId("chat-dock").getByRole("heading", { name: "Keskustelu" }).boundingBox())!;
    const noticeBox = (await notice.boundingBox())!;
    const logBox = (await page.getByRole("log").boundingBox())!;
    expect(noticeBox.y).toBeGreaterThanOrEqual(title.y + title.height - 1);
    expect(noticeBox.y + noticeBox.height).toBeLessThanOrEqual(logBox.y + 1);
    // The field is described by the notice, so a screen reader hears it there.
    const describedBy = (await field(page).getAttribute("aria-describedby")) ?? "";
    expect(describedBy.split(" ")).toContain(await notice.getAttribute("id"));

    // Folded to its tab, the chat still carries the notice: the button that
    // opens it is described by it.
    await page.getByTestId("chat-dock-toggle").click();
    await expect(page.getByTestId("chat-dock-toggle")).toHaveAccessibleDescription(
      "Vastaukset tuottaa tekoäly. Tarkista ne ennen käyttöä.",
    );
  });

  test("the notice is fine print that starts where the title starts", async ({ page }) => {
    await page.goto("/sessions/ses_ui_basics");
    const notice = page.getByTestId("chat-ai-notice");
    await expect(notice).toBeInViewport();
    expect(await notice.evaluate((el) => getComputedStyle(el).fontSize)).toBe("11px");
    // Small, but as readable as the rest of the muted text: no fading.
    expect(await notice.evaluate((el) => getComputedStyle(el).opacity)).toBe("1");

    // The first letter of the notice sits under the first letter of the title.
    const edges = await page.evaluate(() => {
      const note = document.querySelector<HTMLElement>("[data-testid=chat-ai-notice]")!;
      const title = note.parentElement!.querySelector<HTMLElement>("h2")!;
      const left = (el: HTMLElement) => el.getBoundingClientRect().left + parseFloat(getComputedStyle(el).paddingLeft);
      return { title: left(title), note: left(note) };
    });
    expect(Math.abs(edges.title - edges.note)).toBeLessThanOrEqual(1);
  });

  test("the field grows with its text up to a limit, then scrolls, and Enter still sends", async ({ page }) => {
    await newSession(page);
    const sent = await fakeChat(page);
    const input = field(page);
    const height = () => input.evaluate((el) => el.getBoundingClientRect().height);
    const overflow = () => input.evaluate((el) => el.scrollHeight - el.clientHeight);
    const oneLine = await height();
    const four = "rivi yksi\nrivi kaksi\nrivi kolme\nrivi neljä";

    await input.fill(four);
    await expect.poll(height).toBeGreaterThan(oneLine + 40);
    const fourLines = await height();
    // No scrollbar beside text that is all in view.
    expect(await overflow()).toBeLessThanOrEqual(0);

    // Past the limit the field stops growing and its text scrolls.
    await input.fill(Array.from({ length: 14 }, (_, i) => `rivi ${i + 1}`).join("\n"));
    await expect.poll(overflow).toBeGreaterThan(0);
    expect(await height()).toBeLessThanOrEqual(160);
    await input.fill(four);
    await expect.poll(height).toBe(fourLines);

    // Shift+Enter adds a line and sends nothing; Enter sends and the field is one line again.
    await input.press("Shift+Enter");
    await input.pressSequentially("rivi viisi");
    expect(sent).toEqual([]);
    await expect.poll(height).toBeGreaterThan(fourLines);
    await input.press("Enter");
    await expect.poll(() => sent.length).toBe(1);
    expect(sent[0]).toContain("rivi neljä\nrivi viisi");
    await expect(input).toHaveValue("");
    await expect.poll(height).toBe(oneLine);
  });

  test("the send button is quiet while the field is empty and filled once there is text", async ({ page }) => {
    await newSession(page);
    const send = page.locator('form:has(textarea[name="message"]) button[type="submit"]');
    // Quiet, not disabled: it is the same working button either way.
    await expect(send).toBeEnabled();
    await expect(send).toHaveAttribute("data-empty", "true");
    await field(page).fill("Kiitos");
    await expect(send).not.toHaveAttribute("data-empty", /.*/);
    await field(page).fill("   ");
    await expect(send).toHaveAttribute("data-empty", "true");
  });

  test("a gate approved in the panel shows as an event line, not as the user's message", async ({ page }) => {
    const sent = await fakeChat(page);
    // Gate 2 is approved in this session; the address alone does not wake the agent.
    await page.goto("/sessions/ses_laskut?wake=2");

    await expect(page.getByTestId("chat-event")).toHaveText("Gate 2 hyväksytty");
    // What is sent to the agent stays the same.
    await expect.poll(() => sent).toEqual(["Gate 2 hyväksytty paneelista, jatka."]);
    await expect(userMessages(page).filter({ hasText: "paneelista" })).toHaveCount(0);
    await expect(page).toHaveURL(/\/sessions\/ses_laskut$/);
  });

  test("the same words typed by the user stay the user's message", async ({ page }) => {
    await newSession(page);
    const sent = await fakeChat(page);
    await field(page).fill("Gate 2 hyväksytty paneelista, jatka.");
    await field(page).press("Enter");

    // As the session's first message it goes out behind the pace line, as any typed one does.
    await expect.poll(() => sent).toEqual([`${QUICK}\nGate 2 hyväksytty paneelista, jatka.`]);
    await expect(userMessages(page).filter({ hasText: "paneelista" })).toHaveCount(1);
    await expect(page.getByTestId("chat-event")).toHaveCount(0);
  });

  test("links in a reply: in-app ones stay in the tab, external ones say where they go", async ({ page }) => {
    await newSession(page);
    const path = new URL(page.url()).pathname;
    await fakeChat(page, [
      {
        delta:
          `Testi on [PoC-välilehdellä](${path}?tab=poc). Ohje: [GAIK-dokumentaatio](https://www.gaik.ai/docs/wizard) ` +
          "ja https://en.wikipedia.org/wiki/Foo_(bar).",
      },
      { done: true },
    ]);
    await field(page).fill("Mistä löydän ohjeet?");
    await field(page).press("Enter");

    const log = page.getByRole("log");
    const external = log.getByRole("link", { name: /GAIK-dokumentaatio/ });
    await expect(external).toHaveAttribute("href", "https://www.gaik.ai/docs/wizard");
    await expect(external).toHaveAttribute("target", "_blank");
    await expect(external).toHaveAttribute("rel", "noreferrer noopener");
    await expect(external).toHaveAttribute("title", "https://www.gaik.ai/docs/wizard");
    await expect(external.locator(".chat-link-host")).toHaveText("gaik.ai");
    await expect(external.locator("svg.chat-link-icon")).toBeVisible();

    const bare = log.getByRole("link", { name: "https://en.wikipedia.org/wiki/Foo_(bar)" });
    await expect(bare).toHaveAttribute("href", "https://en.wikipedia.org/wiki/Foo_(bar)");
    await expect(bare.locator(".chat-link-host")).toHaveCount(0);

    // The in-app link goes through the router: same tab, no page load.
    const internal = log.getByRole("link", { name: "PoC-välilehdellä" });
    await expect(internal).not.toHaveAttribute("target", /.*/);
    await page.evaluate(() => ((window as unknown as { stayed?: boolean }).stayed = true));
    await internal.click();
    await expect(page).toHaveURL(/\?tab=poc$/);
    expect(await page.evaluate(() => (window as unknown as { stayed?: boolean }).stayed)).toBe(true);
    expect(page.context().pages()).toHaveLength(1);
  });
});

test.describe("the chat composer on a phone", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test.beforeEach(async ({ page, request }) => {
    await resetMockSessions(request);
    await loginAsDev(page);
  });

  test("a reference opens the chat sheet with its chip in view", async ({ page }) => {
    await page.goto("/sessions/ses_ui_basics");
    const dock = page.getByTestId("chat-dock");
    await expect(dock).toHaveAttribute("data-chat-open", "false");

    await ask(page, STEP);
    await expect(dock).toHaveAttribute("data-chat-open", "true");
    await expect(chip(page)).toBeInViewport();
    await expect(page.getByTestId("chat-reference-remove")).toBeInViewport();
    await expect(field(page)).toBeInViewport();
    // The chip stays inside the sheet's width.
    const box = (await chip(page).boundingBox())!;
    expect(box.x + box.width).toBeLessThanOrEqual(390);
  });
});
