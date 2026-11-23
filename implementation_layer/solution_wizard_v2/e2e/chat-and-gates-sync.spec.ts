import { test, expect, type Page } from "@playwright/test";
import { loginAsDev } from "./helpers/auth";
import { resetMockSessions } from "./helpers/mock";
import { selectWorkspaceTab } from "./helpers/workspace";
import { PACE_SENTENCES } from "../lib/chat-background";

// A gate action is a server action: on a busy dev server it takes a few seconds.
const AFTER_ACTION = { timeout: 20_000 };

const frame = (data: unknown) => `data: ${JSON.stringify(data)}\n\n`;

/**
 * The chat and the panel tell the same story: a reply survives a reload, an
 * approved gate can be reopened for a change, a finished solution says so
 * where the eye lands, and the wizard can offer the other language.
 * Each test uses its own e2e-only mock fixture (lib/mock-sessions.ts).
 */

const PLAIN_REPLY = [{ delta: "Selvä." }, { done: true }];

// Answers POST /chat as wizard_api streams it, and collects what was sent.
// `first` is the reply to the first message; later ones get a plain reply.
async function fakeChat(page: Page, first: unknown[] = PLAIN_REPLY) {
  const sent: string[] = [];
  await page.route("**/api/sessions/*/chat", (route) => {
    if (route.request().method() !== "POST") return route.continue();
    sent.push((route.request().postDataJSON() as { message: string }).message);
    return route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body: (sent.length === 1 ? first : PLAIN_REPLY).map(frame).join(""),
    });
  });
  return sent;
}

/**
 * Press "Muuta" of an approved gate in the timeline. Where the timeline folds
 * an approved stage's controls behind a press on the stage, the stage is
 * opened first; "Muuta" itself must then be there either way.
 */
async function pressGateChange(page: Page, gate: number) {
  const stage = page.getByTestId(`timeline-stage-${gate}`);
  if ((await stage.count()) > 0 && (await stage.getAttribute("aria-expanded")) === "false") await stage.click();
  await page.getByTestId(`gate-change-${gate}`).click();
}

test.describe("a reply the page did not see start", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test.beforeEach(async ({ request }) => {
    await resetMockSessions(request);
  });

  test("a page loaded mid-reply shows the message and joins the reply", async ({ page }) => {
    await loginAsDev(page);
    let joined = 0;
    await page.route("**/api/sessions/*/chat/stream", (route) => {
      joined += 1;
      return route.fulfill({
        status: 200,
        contentType: "text/event-stream",
        body: [
          { delta: "Katson suunnitelmaa" },
          { activity: { kind: "read", file: "use_case.blueprint.json" } },
          { narration_end: true },
          { delta: "Lisäsin tarkastusvaiheen." },
          { done: true },
        ]
          .map(frame)
          .join(""),
      });
    });

    await page.goto("/sessions/ses_reply_pending");

    const log = page.getByRole("log");
    // The message being answered is not in the stored conversation yet.
    await expect(log.getByText("Lisää tarkastusvaihe.")).toBeVisible();
    await expect(log.getByText("Lisäsin tarkastusvaiheen.")).toBeVisible();
    // The narration before the tool call is not the reply.
    await expect(log.getByText("Katson suunnitelmaa")).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Lähetä" })).toBeEnabled();
    // Joined once, also when the page reads the session again after the reply.
    await page.waitForTimeout(500);
    expect(joined).toBe(1);
  });

  test("when the reply was finished meanwhile, nothing is left hanging", async ({ page }) => {
    await loginAsDev(page);
    await page.route("**/api/sessions/*/chat/stream", (route) => route.fulfill({ status: 204 }));

    await page.goto("/sessions/ses_reply_pending");

    await expect(page.getByRole("button", { name: "Lähetä" })).toBeEnabled();
    await expect(page.getByTestId("chat-thinking")).toHaveCount(0);
    await expect(page.getByRole("log").getByText("Lisää tarkastusvaihe.")).toHaveCount(0);
  });

  test("a message refused while another reply is on its way comes back to the field", async ({
    page,
  }) => {
    await loginAsDev(page);
    await page.route("**/api/sessions/*/chat", (route) =>
      route.request().method() === "POST"
        ? route.fulfill({ status: 409, contentType: "application/json", body: '{"error":"busy"}' })
        : route.continue(),
    );
    await page.goto("/sessions/ses_gates_sync");
    await page.getByTestId("chat-dock-toggle").click();

    const field = page.getByPlaceholder("Kirjoita viesti…");
    await field.fill("Vaihda tarkastaja.");
    await field.press("Enter");

    await expect(page.getByTestId("chat-busy-note")).toBeVisible();
    await expect(field).toHaveValue("Vaihda tarkastaja.");
    // No bubble is left for a message that was not taken.
    await expect(page.getByRole("log").getByText("Vaihda tarkastaja.")).toHaveCount(0);
  });
});

test.describe("reopening an approved gate", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test.beforeEach(async ({ request }) => {
    await resetMockSessions(request);
  });

  test("Change asks first, then puts the session back on the gate with the chat ready", async ({
    page,
  }) => {
    await loginAsDev(page);
    await page.goto("/sessions/ses_gates_sync");
    await expect(page.getByText("VAIHE 10 / 13")).toBeVisible();
    await expect(page.getByTestId("gate-ring")).toHaveAccessibleName("2/4 gatea hyväksytty");

    // "Change" is behind a press on the approved stage.
    await expect(page.getByTestId("gate-change-1")).toHaveCount(0);
    await page.getByTestId("timeline-stage-1").click();
    await page.getByTestId("gate-change-1").click();
    const ask = page.getByTestId("gate-reopen-1");
    await expect(ask).toContainText("Avataanko Gate 1 uudelleen?");

    // Cancel leaves everything as it was.
    await ask.getByRole("button", { name: "Peruuta" }).click();
    await expect(ask).toHaveCount(0);
    await expect(page.getByText("VAIHE 10 / 13")).toBeVisible();

    await page.getByTestId("gate-change-1").click();
    await page.getByTestId("gate-reopen-confirm-1").click();

    await expect(page.getByTestId("workspace-phase")).toHaveText("Gate 1: vaatimukset", AFTER_ACTION);
    await expect(page.getByTestId("gate-reopened")).toContainText(
      "Gate 1 (Vaatimukset) on avattu uudelleen muutosta varten.",
    );
    await expect(page.getByTestId("gate-ring")).toHaveAccessibleName("0/4 gatea hyväksytty");
    await expect(page.getByTestId("gate1-actions")).toBeVisible();
    // The chat is open with the gate as the reference: the user says what to change.
    await expect(page.getByTestId("chat-reference")).toContainText("Gate 1");
    // The field says what to write while the gate's chip is attached, and
    // goes back to its own words when the chip is removed.
    await expect(page.getByPlaceholder("Mitä Gate 1:ssä pitää muuttaa?")).toBeFocused();
    await page.getByTestId("chat-reference-remove").click();
    await expect(page.getByPlaceholder("Kirjoita viesti…")).toBeFocused();
  });

  test("approving the reopened gate again takes the notice away", async ({ page }) => {
    await loginAsDev(page);
    await fakeChat(page);
    await page.goto("/sessions/ses_gates_sync");
    await page.getByTestId("timeline-stage-2").click();
    await page.getByTestId("gate-change-2").click();
    await page.getByTestId("gate-reopen-confirm-2").click();
    await expect(page.getByTestId("gate-reopened")).toBeVisible(AFTER_ACTION);
    await expect(page.getByText("VAIHE 9 / 13")).toBeVisible();

    await page
      .getByTestId("gate2-actions")
      .getByRole("button", { name: "Hyväksy ratkaisun rakenne" })
      .click();

    await expect(page.getByText("VAIHE 10 / 13")).toBeVisible(AFTER_ACTION);
    await expect(page.getByTestId("gate-reopened")).toHaveCount(0);
  });

  test("the last gate approved again after a change releases the wizard a second time", async ({ page }) => {
    // The page releases the wizard of a finished session and remembers it in
    // this browser, so that it asks once. The mark was kept for good: after
    // Gate 4 was reopened and approved again nothing released the wizard.
    const released = () => page.evaluate(() => window.localStorage.getItem("wizard-released:ses_last_gate"));
    const approve = () =>
      page.getByTestId("gate4-actions").getByRole("button", { name: "Hyväksy luovutus" }).click();
    await loginAsDev(page);
    const sent = await fakeChat(page);
    const WAKE = "Gate 4 hyväksytty paneelista, jatka.";
    await page.goto("/sessions/ses_last_gate");

    await approve();
    await expect(page.getByTestId("solution-done")).toBeVisible(AFTER_ACTION);
    // Released once the wizard's reply to the approval has ended.
    await expect.poll(released, AFTER_ACTION).toBe("1");
    expect(sent).toEqual([WAKE]);

    await pressGateChange(page, 4);
    await page.getByTestId("gate-reopen-confirm-4").click();
    await expect(page.getByTestId("gate-reopened")).toBeVisible(AFTER_ACTION);
    await expect(page.getByTestId("solution-done")).toHaveCount(0);
    // The session waits at its last gate again: the mark of the first release is gone.
    await expect.poll(released, AFTER_ACTION).toBeNull();

    await approve();
    await expect(page.getByTestId("solution-done")).toBeVisible(AFTER_ACTION);
    // The wizard hears of the second approval too, and is released after its reply.
    await expect.poll(() => sent, AFTER_ACTION).toEqual([WAKE, WAKE]);
    await expect.poll(released, AFTER_ACTION).toBe("1");
  });

  test("a reopened Gate 2 is said above the workspace, and the tab leaves the locked PoC for the diagram", async ({
    page,
  }) => {
    await loginAsDev(page);
    await page.goto("/sessions/ses_laskut");
    // Gate 3 waits on the test run, so the tab is the PoC.
    const poc = page.getByRole("tab", { name: /PoC/ });
    await expect(poc).toHaveAttribute("aria-selected", "true");

    await pressGateChange(page, 2);
    await page.getByTestId("gate-reopen-confirm-2").click();

    const notice = page.getByTestId("gate-reopened");
    await expect(notice).toContainText(
      "Gate 2 (Ratkaisun rakenne) on avattu uudelleen muutosta varten.",
      AFTER_ACTION,
    );
    await expect(page.getByTestId("workspace-phase")).toHaveText("Gate 2: ratkaisun rakenne");
    // Read before the workspace it changes: above the tabs, not between the workspace and the decision bar.
    const box = (await notice.boundingBox())!;
    const tabs = (await page.getByRole("tablist").first().boundingBox())!;
    expect(box.y + box.height).toBeLessThanOrEqual(tabs.y);

    // The PoC is locked until Gate 2 is approved again: the tab shows what the gate is about instead.
    await expect(page.getByRole("tab", { name: /Työnkulku/ })).toHaveAttribute("aria-selected", "true");
    await expect(poc).toHaveAttribute("aria-selected", "false");
    await expect(poc).toHaveAttribute("aria-disabled", "true");
    await expect(page.getByTestId("simple-flow")).toBeVisible({ timeout: 30_000 });
    // Before Gate 2 again, so the diagram can be edited.
    await expect(page.getByTestId("simple-flow-locked")).toHaveCount(0);

    // The locked tab says why, and a press on it leaves the open tab where it is.
    await expect(poc).toHaveAccessibleDescription("Avautuu, kun Gate 2 on hyväksytty");
    await poc.click({ force: true });
    await expect(poc).toHaveAttribute("aria-selected", "false");
    await expect(page.getByRole("tab", { name: /Työnkulku/ })).toHaveAttribute("aria-selected", "true");
  });

  test("a gate reopened from the Blueprint tab leaves the tab where it was", async ({ page }) => {
    await loginAsDev(page);
    await page.goto("/sessions/ses_gates_sync");
    await selectWorkspaceTab(page, /Blueprint/);

    await pressGateChange(page, 2);
    await page.getByTestId("gate-reopen-confirm-2").click();

    await expect(page.getByTestId("gate-reopened")).toBeVisible(AFTER_ACTION);
    await expect(page.getByRole("tab", { name: /Blueprint/ })).toHaveAttribute("aria-selected", "true");
  });

  test("the page follows a gate the wizard reopened in the middle of its reply", async ({ page }) => {
    await loginAsDev(page);
    // The reply says the session changed; the mock session is moved the way
    // the wizard's own tool moves a real one.
    await page.route("**/api/sessions/*/chat", async (route) => {
      if (route.request().method() !== "POST") return route.continue();
      await page.request.post("/api/dev/set-step", { data: { id: "ses_gates_sync", step: 9 } });
      return route.fulfill({
        status: 200,
        contentType: "text/event-stream",
        body: [{ session_changed: true }, { delta: "Avasin Gate 2:n." }, { done: true }]
          .map(frame)
          .join(""),
      });
    });
    await page.goto("/sessions/ses_gates_sync");
    await page.getByTestId("chat-dock-toggle").click();

    const field = page.getByPlaceholder("Kirjoita viesti…");
    await field.fill("Vaihda tarkastaja.");
    await field.press("Enter");

    await expect(page.getByTestId("workspace-phase")).toHaveText(
      "Gate 2: ratkaisun rakenne",
      AFTER_ACTION,
    );
    await expect(page.getByRole("log").getByText("Avasin Gate 2:n.")).toBeVisible();
  });

  test("a reply whose connection was cut is read again from the running turn", async ({ page }) => {
    await loginAsDev(page);
    // The response to the message stops without its last frame, the way a
    // proxy closes a long response; the wizard is still answering.
    await page.route("**/api/sessions/*/chat", (route) => {
      if (route.request().method() !== "POST") return route.continue();
      return route.fulfill({
        status: 200,
        contentType: "text/event-stream",
        body: [{ delta: "Lisään tarkast" }].map(frame).join(""),
      });
    });
    let joined = 0;
    await page.route("**/api/sessions/*/chat/stream", (route) => {
      joined += 1;
      return route.fulfill({
        status: 200,
        contentType: "text/event-stream",
        body: [{ delta: "Lisään tarkastusvaiheen ja päivitän kaavion." }, { done: true }]
          .map(frame)
          .join(""),
      });
    });
    await page.goto("/sessions/ses_gates_sync");
    await page.getByTestId("chat-dock-toggle").click();

    const field = page.getByPlaceholder("Kirjoita viesti…");
    await field.fill("Lisää tarkastusvaihe.");
    await field.press("Enter");

    const log = page.getByRole("log");
    await expect(log.getByText("Lisään tarkastusvaiheen ja päivitän kaavion.")).toBeVisible(AFTER_ACTION);
    // The half that arrived before the cut is not left beside the whole reply.
    await expect(log.getByText("Lisään tarkast", { exact: true })).toHaveCount(0);
    await expect(log.getByText("Lisää tarkastusvaihe.")).toHaveCount(1);
    await expect(log.getByText("⚠︎")).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Lähetä" })).toBeEnabled();
    expect(joined).toBe(1);
  });
});

test.describe("a finished solution", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test.beforeEach(async ({ request }) => {
    await resetMockSessions(request);
  });

  test("says so above the workspace, in one heading, with no button to end the session", async ({ page }) => {
    await loginAsDev(page);
    await fakeChat(page);
    await page.goto("/sessions/ses_last_gate");
    await expect(page.getByTestId("gate-ring")).toHaveAccessibleName("3/4 gatea hyväksytty");
    await page.getByTestId("gate4-actions").getByRole("button", { name: "Hyväksy luovutus" }).click();

    const done = page.getByTestId("solution-done");
    await expect(done).toBeVisible(AFTER_ACTION);
    await expect(done.getByRole("heading", { name: "Ratkaisu on valmis" })).toBeVisible();
    await expect(page.getByTestId("gate-ring")).toHaveAccessibleName("4/4 gatea hyväksytty");
    await expect(page.getByTestId("timeline-progress")).toHaveText("Valmis");
    // Above the tabs, not under the workspace.
    const card = await done.boundingBox();
    const tabs = await page.getByRole("tablist").first().boundingBox();
    expect(card && tabs && card.y < tabs.y).toBe(true);

    // The wizard is released by the page; ending a session is in its row's menu.
    await expect(done.getByRole("button")).toHaveCount(0);
    await expect(done).not.toContainText("Kaikki neljä gatea");
    await expect(page.getByTestId("now-line")).toHaveCount(0);
  });
});

test.describe("asked for the other language", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test.beforeEach(async ({ request }) => {
    await resetMockSessions(request);
  });

  test("the wizard offers the switch as a button, and the reply goes on in that language", async ({
    page,
  }) => {
    await loginAsDev(page);
    const sent = await fakeChat(page, [
      { offer_locale: "en" },
      { delta: "You can switch the interface with the button below." },
      { done: true },
    ]);
    await page.goto("/sessions/ses_gates_sync");
    await page.getByTestId("chat-dock-toggle").click();

    const field = page.getByPlaceholder("Kirjoita viesti…");
    await field.fill("Can you answer in English");
    await field.press("Enter");

    const offer = page.getByTestId("chat-language-offer");
    await expect(offer).toHaveText("Switch to English");
    await offer.click();

    // The interface is in English, and the wizard is told to go on in it.
    await expect(page.getByPlaceholder("Type a message…")).toBeVisible(AFTER_ACTION);
    // The first message typed in this session carries the default pace's line
    // (lib/chat-background), in the language the interface had then.
    await expect
      .poll(() => sent)
      .toEqual([`${PACE_SENTENCES.fi.quick}\nCan you answer in English`, "Continue in English."]);
    await expect(page.getByTestId("chat-language-offer")).toHaveCount(0);
  });
});
