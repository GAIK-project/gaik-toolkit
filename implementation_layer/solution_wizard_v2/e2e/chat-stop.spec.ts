import { test, expect, type Page, type Route } from "@playwright/test";
import { loginAsDev } from "./helpers/auth";
import { resetMockSessions } from "./helpers/mock";
import { createSession, hydrated } from "./helpers/session";

/**
 * Stopping a reply while it is being written (#150). While the wizard
 * answers, the button that sends a message stops the reply instead: what was
 * written so far stays, marked "Pysäytetty", and the field takes the next
 * message.
 *
 * The first specs run on the mock store, whose scripted reply is slowed down
 * (/api/dev/reply-pace) so there is a reply to stop. The others answer the
 * chat routes themselves, to hold a reply open the way a starting wizard or a
 * page loaded mid-reply does.
 */

const field = (page: Page) => page.locator('textarea[name="message"]');
const stopButton = (page: Page) => page.getByRole("button", { name: "Pysäytä", exact: true });
const sendButton = (page: Page) => page.getByRole("button", { name: "Lähetä", exact: true });
const replies = (page: Page) => page.locator('[data-testid="chat-message"][data-role="assistant"]');
const userMessages = (page: Page) => page.locator('[data-testid="chat-message"][data-role="user"]');
const stoppedMarks = (page: Page) => page.getByTestId("chat-stopped");

const frames = (...events: object[]) => events.map((e) => `data: ${JSON.stringify(e)}\n\n`).join("");

/** Slows the mock store's scripted reply down to `ms` a word. */
async function replyPace(page: Page, ms: number) {
  const res = await page.request.post("/api/dev/reply-pace", { data: { ms } });
  expect(res.ok(), `reply-pace failed: ${res.status()}`).toBe(true);
}

/** The requests the page makes to stop a reply. */
function stopRequests(page: Page): () => number {
  let count = 0;
  page.on("request", (request) => {
    if (request.method() === "POST" && /\/api\/sessions\/[^/]+\/chat\/stop$/.test(request.url())) count += 1;
  });
  return () => count;
}

/** A new session whose reply to `message` is being written, a word at a time. */
async function replyOnItsWay(page: Page, message: string) {
  await page.goto("/");
  await createSession(page, `stop ${Date.now()}`);
  await replyPace(page, 400);
  await field(page).fill(message);
  await field(page).press("Enter");
  await expect(userMessages(page).last()).toContainText(message);
  // The first words of the reply are on the page (after the speaker's name,
  // which a screen reader is given before them).
  await expect(replies(page).last()).toContainText(/:(\s+\S+){3}/);
}

test.describe("stopping a reply", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test.beforeEach(async ({ page, request }) => {
    await resetMockSessions(request);
    await loginAsDev(page);
  });

  test("the send button stops the reply, what was written stays, and the next message is taken", async ({
    page,
  }) => {
    const stops = stopRequests(page);
    await replyOnItsWay(page, "Laskujen käsittely");

    // Stop stands where Send stood; there is no Send to press meanwhile.
    await expect(stopButton(page)).toBeVisible();
    await expect(stopButton(page)).toBeEnabled();
    await expect(sendButton(page)).toHaveCount(0);

    // Esc is not a stop: not in the field, not on the button.
    await field(page).press("Escape");
    await stopButton(page).focus();
    await page.keyboard.press("Escape");
    await page.waitForTimeout(300);
    expect(stops()).toBe(0);
    await expect(stopButton(page)).toBeVisible();

    await stopButton(page).click();

    await expect(stoppedMarks(page)).toHaveCount(1);
    await expect(stoppedMarks(page)).toHaveText("Pysäytetty");
    expect(stops()).toBe(1);
    // The reply stopped where it was: its first words, not all of it.
    const stopped = replies(page).last();
    const written = (await stopped.innerText()).replace(/\s*Pysäytetty\s*$/, "").trim();
    expect(written.length).toBeGreaterThan(0);
    expect(written).not.toMatch(/\?$/);
    // The field is free.
    await expect(sendButton(page)).toBeVisible();
    await expect(stopButton(page)).toHaveCount(0);
    await expect(page.getByTestId("chat-thinking")).toHaveCount(0);

    // Stored as stopped: a reload shows the same words and the same mark, and
    // the note the reply was stored with is not shown beside it.
    await page.reload();
    await hydrated(page);
    await expect(stoppedMarks(page)).toHaveCount(1);
    await expect(replies(page).last()).toContainText(written);
    await expect(page.getByRole("log")).not.toContainText("(Pysäytetty)");

    // The next message is taken and answered to its end.
    await replyPace(page, 0);
    await field(page).fill("Talousosaston käsittelijät");
    await field(page).press("Enter");
    await expect(userMessages(page).last()).toContainText("Talousosaston käsittelijät");
    await expect(sendButton(page)).toBeEnabled();
    await expect(replies(page).last()).toContainText(/\S/);
    await expect(replies(page).last().getByTestId("chat-stopped")).toHaveCount(0);
    await expect(stoppedMarks(page)).toHaveCount(1);
  });

  test("the stop button is reached and pressed from the keyboard", async ({ page }) => {
    await replyOnItsWay(page, "Laskujen käsittely");

    // From the field, the button is the next stop of Tab.
    await field(page).focus();
    await page.keyboard.press("Tab");
    await expect(stopButton(page)).toBeFocused();
    await page.keyboard.press("Enter");

    await expect(stoppedMarks(page)).toHaveCount(1);
    await expect(sendButton(page)).toBeVisible();
  });

  test("a double click on Send does not stop the reply it started", async ({ page }) => {
    const stops = stopRequests(page);
    await page.goto("/");
    await createSession(page, `stop ${Date.now()}`);
    await replyPace(page, 400);

    await field(page).fill("Laskujen käsittely");
    await sendButton(page).dblclick();

    await expect(stopButton(page)).toBeVisible();
    await expect(replies(page).last()).toContainText(/:(\s+\S+){3}/);
    expect(stops()).toBe(0);
    await expect(stoppedMarks(page)).toHaveCount(0);
  });

  test("a stop pressed before the message has reached the wizard is asked again until it is taken", async ({
    page,
  }) => {
    await page.goto("/");
    await createSession(page, `stop ${Date.now()}`);

    // The wizard is being started: the chat's answer is held until released.
    let release!: () => void;
    const released = new Promise<void>((resolve) => (release = resolve));
    await page.route("**/api/sessions/*/chat", async (route: Route) => {
      if (route.request().method() !== "POST") return route.continue();
      await released;
      await route.fulfill({
        status: 200,
        contentType: "text/event-stream",
        body: frames({ stopped: true, tool: null }),
      });
    });
    // Nothing to stop at first; taken the second time, as the turn has begun.
    let asked = 0;
    await page.route("**/api/sessions/*/chat/stop", async (route: Route) => {
      asked += 1;
      if (asked === 1) {
        return route.fulfill({ status: 409, contentType: "application/json", body: '{"error":"no_reply_running"}' });
      }
      await route.fulfill({ status: 202, contentType: "application/json", body: '{"stopping":true}' });
      release();
    });

    await field(page).fill("Laskujen käsittely");
    await field(page).press("Enter");
    await expect(stopButton(page)).toBeVisible();
    // Not the press that sent the message, held: a press of its own.
    await page.waitForTimeout(500);
    await stopButton(page).click();

    // Pressed: the button turns and cannot be pressed twice.
    const stopping = page.getByRole("button", { name: "Pysäytetään…" });
    await expect(stopping).toBeDisabled();

    await expect(stoppedMarks(page)).toHaveCount(1);
    expect(asked).toBe(2);
    await expect(sendButton(page)).toBeVisible();
    // Stopped before the first word: the message stays, with the mark alone under it.
    await expect(userMessages(page).last()).toContainText("Laskujen käsittely");
    await expect(replies(page).last()).toHaveText(/^(Tekoälyavustaja:\s*)?Pysäytetty$/);
  });

  test("a reply joined after a reload can be stopped too", async ({ page }) => {
    // The page is loaded while the wizard is answering: it joins the reply.
    let release!: () => void;
    const released = new Promise<void>((resolve) => (release = resolve));
    await page.route("**/api/sessions/*/chat/stream", async (route: Route) => {
      await released;
      await route.fulfill({
        status: 200,
        contentType: "text/event-stream",
        body: frames({ delta: "Lisään tarkastusvaiheen " }, { stopped: true, tool: "write" }),
      });
    });
    let asked = 0;
    await page.route("**/api/sessions/*/chat/stop", async (route: Route) => {
      asked += 1;
      await route.fulfill({ status: 202, contentType: "application/json", body: '{"stopping":true}' });
      release();
    });

    await page.goto("/sessions/ses_reply_pending");
    await hydrated(page);
    await expect(page.getByRole("log").getByText("Lisää tarkastusvaihe.")).toBeVisible();
    await expect(stopButton(page)).toBeVisible();
    await page.waitForTimeout(500);
    await stopButton(page).click();

    await expect(stoppedMarks(page)).toHaveCount(1);
    expect(asked).toBe(1);
    await expect(page.getByRole("log").getByText("Lisään tarkastusvaiheen")).toBeVisible();
    await expect(sendButton(page)).toBeEnabled();
  });
});

test.describe("stopping a reply on a phone", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test.beforeEach(async ({ page, request }) => {
    await resetMockSessions(request);
    await loginAsDev(page);
  });

  test("Stop is in view beside the field and stops the reply", async ({ page }) => {
    await replyOnItsWay(page, "Laskujen käsittely");

    const box = (await stopButton(page).boundingBox())!;
    expect(box.x).toBeGreaterThanOrEqual(0);
    expect(box.x + box.width).toBeLessThanOrEqual(390);
    expect(box.y + box.height).toBeLessThanOrEqual(844);
    await stopButton(page).click();

    await expect(stoppedMarks(page)).toHaveCount(1);
    await expect(sendButton(page)).toBeVisible();
  });
});
