import { expect, type Page, type Route } from "@playwright/test";
import { CHAT_SEND_EVENT } from "../../lib/chat-events";

/**
 * Resolves once React has taken over a page that was loaded whole, and its
 * effects have run. `page.goto` returns at the load event, which can come
 * before that: a window event sent to the page then (a chat reference, say)
 * would have no listener yet. React marks each element it takes over; the
 * last one of the page's content is the last to get its mark.
 */
export async function hydrated(page: Page): Promise<void> {
  await page.waitForFunction(() => {
    let last = document.querySelector("[data-shell-main]");
    while (last?.lastElementChild) last = last.lastElementChild;
    return last !== null && Object.keys(last).some((key) => key.startsWith("__reactFiber"));
  });
  // The effects of that first render are flushed within the next frames.
  await page.evaluate(
    () => new Promise<void>((done) => requestAnimationFrame(() => requestAnimationFrame(() => done()))),
  );
}

/**
 * Has the page read the session again, in the same document, the way the end
 * of a chat turn does: the step is the wizard's to move (it follows the files
 * the wizard writes), so the page has no button that moves it, and the chat
 * calls router.refresh() as each reply ends. A message goes out through the
 * chat (CHAT_SEND_EVENT, as the page's own forms send one), its reply ends at
 * once without reaching the wizard, and this resolves when the page has read
 * the session from the server. The page is not loaded anew: what the client
 * holds (the tab the user chose) stays, and that is checked here.
 */
export async function readSessionAgain(page: Page): Promise<void> {
  await hydrated(page);
  const chat = "**/api/sessions/*/chat";
  const reply = (route: Route) =>
    route.request().method() === "POST"
      ? route.fulfill({ status: 200, contentType: "text/event-stream", body: `data: ${JSON.stringify({ done: true })}\n\n` })
      : route.fallback();
  await page.route(chat, reply);
  await page.evaluate(() => {
    (window as unknown as { __sameDocument?: boolean }).__sameDocument = true;
  });
  const path = new URL(page.url()).pathname;
  // router.refresh() asks for the page's server components again (an RSC
  // request for this path); a prefetch of another link is not it.
  const reread = page.waitForResponse((res) => {
    const headers = res.request().headers();
    return headers.rsc === "1" && !headers["next-router-prefetch"] && new URL(res.url()).pathname === path;
  });
  await page.evaluate((event) => window.dispatchEvent(new CustomEvent(event, { detail: "Jatketaan." })), CHAT_SEND_EVENT);
  await reread;
  await page.unroute(chat, reply);
  expect(
    await page.evaluate(() => (window as unknown as { __sameDocument?: boolean }).__sameDocument),
    "the page was loaded anew instead of reading the session again",
  ).toBe(true);
}

/**
 * A new session of the signed-in user with the given name, opened in `page`.
 *
 * In the interface a session starts from the user's first message, which a
 * real wizard would answer. A spec that needs a session and not that
 * conversation asks the app for one instead (POST /api/sessions), with the
 * page's own sign-in.
 */
export async function createSession(page: Page, title: string): Promise<string> {
  const res = await page.request.post("/api/sessions", { data: { title } });
  expect(res.status(), `creating a session failed: ${res.status()} ${await res.text()}`).toBe(201);
  const { id } = (await res.json()) as { id: string };
  await page.goto(`/sessions/${id}`);
  await hydrated(page);
  return id;
}

/**
 * Starts a session the way a user does: the first message, typed on the start
 * view and sent with Enter. The session's chat then sends it as its first
 * turn; route or await that reply in the spec.
 */
export async function startFromMessage(page: Page, text: string): Promise<string> {
  if (new URL(page.url()).pathname !== "/") await page.goto("/");
  await hydrated(page);
  const field = page.getByTestId("start-view").locator('textarea[name="message"]');
  await field.fill(text);
  await field.press("Enter");
  await page.waitForURL(/\/sessions\/[^/]+$/);
  return new URL(page.url()).pathname.split("/")[2];
}
