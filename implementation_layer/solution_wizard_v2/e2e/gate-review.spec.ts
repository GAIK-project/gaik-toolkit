import { test, expect, type Page } from "@playwright/test";
import { loginAsDev } from "./helpers/auth";
import { recordChatReferences } from "./helpers/chat-reference";
import { setMockSessionStep } from "./helpers/dev-step";
import { resetMockSessions } from "./helpers/mock";

// A gate action is a server action: on a busy dev server it takes a few seconds.
const AFTER_ACTION = { timeout: 20_000 };

/**
 * The gate decision bar (GateDecisionBar) at Gate 1 and at Gates 2–4, the
 * Gate 1 review's items, and the gate timeline. Each test uses its own
 * e2e-only mock fixture (lib/mock-sessions.ts), so approving one never affects
 * another test.
 *
 * A change request goes to the wizard through the chat, as a reference the
 * user writes under. What Gate 1 still lacks, and a correction to one item of
 * its review, are written where they are read and sent as a chat turn.
 */

// Records the messages the page hands to the chat to send (CHAT_SEND_EVENT).
async function recordChatSends(page: Page): Promise<() => Promise<string[]>> {
  await page.evaluate(() => {
    const store = window as unknown as { __chatSends: string[] };
    store.__chatSends = [];
    window.addEventListener("gaik-wizard:chat-send", (e) => {
      store.__chatSends.push((e as CustomEvent<string>).detail);
    });
  });
  return () => page.evaluate(() => (window as unknown as { __chatSends: string[] }).__chatSends);
}

// The wizard takes a while over its reply, so what the page shows meanwhile can be read.
async function slowChat(page: Page) {
  await page.route("**/api/sessions/*/chat", async (route) => {
    if (route.request().method() !== "POST") return route.continue();
    await new Promise((resolve) => setTimeout(resolve, 3000));
    return route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body: `data: ${JSON.stringify({ delta: "Selvä." })}\n\ndata: ${JSON.stringify({ done: true })}\n\n`,
    });
  });
}
test.describe("Gate 1 review", () => {
  test.beforeEach(async ({ request }) => {
    await resetMockSessions(request);
  });

  test("approve is disabled until business context is captured", async ({ page }) => {
    await loginAsDev(page);
    await page.goto("/sessions/ses_gate1_blocked");

    await expect(page.getByTestId("workspace-phase")).toHaveText("Gate 1: vaatimukset");
    const bar = page.getByTestId("gate1-actions");
    await expect(bar.getByRole("button", { name: "Hyväksy vaatimukset" })).toBeDisabled();

    // What is missing has a field of its own, right where approval is refused.
    const missing = bar.getByTestId("gate1-missing-form");
    await expect(missing.getByLabel("Nykyprosessi", { exact: true })).toBeVisible();
    await expect(missing.getByLabel("Odotettu arvo", { exact: true })).toBeVisible();
    // The bar has two decisions: ask for changes, approve.
    await expect(bar.getByRole("button", { name: "Hylkää…" })).toHaveCount(0);
    await expect(bar.getByRole("button", { name: "Edellinen" })).toHaveCount(0);
  });

  test("the missing items are answered in the bar and go to the wizard as one chat turn", async ({ page }) => {
    await loginAsDev(page);
    await slowChat(page);
    await page.goto("/sessions/ses_gate1_blocked");
    const sends = await recordChatSends(page);

    const form = page.getByTestId("gate1-missing-form");
    const send = form.getByRole("button", { name: "Lähetä wizardille" });
    // Nothing to send until an item has an answer or is marked not known.
    await expect(send).toBeDisabled();
    await form.getByLabel("Nykyprosessi", { exact: true }).fill("Laskut kirjataan käsin.");
    await form.getByRole("checkbox", { name: "Ei tiedossa: Odotettu arvo" }).check();
    await expect(form.getByLabel("Odotettu arvo", { exact: true })).toBeDisabled();
    await send.click();

    expect(await sends()).toEqual([
      [
        "Täydennän Gate 1:n puuttuvat tiedot:",
        "- Nykyprosessi: Laskut kirjataan käsin.",
        "- Odotettu arvo: en tiedä. Kirjaa kohtaan paras arviosi keskustelun perusteella ja lisää se avoimeksi oletukseksi, jotta Gate 1 voidaan hyväksyä.",
      ].join("\n"),
    ]);
    // The fields give way to a line saying the wizard is on it.
    await expect(page.getByTestId("gate1-missing")).toContainText("Wizard kirjaa vastauksia…");
    await expect(form).toHaveCount(0);
  });

  test("request changes takes the gate to the chat as a reference, with no form", async ({ page }) => {
    await loginAsDev(page);
    await page.goto("/sessions/ses_gate1_blocked");
    const references = await recordChatReferences(page);

    await page.getByTestId("gate1-actions").getByRole("button", { name: "Pyydä muutoksia" }).click();

    expect(await references()).toEqual([
      {
        key: "gate:4",
        label: "Gate 1 · Vaatimukset",
        prefix: "Muutospyyntö ennen Gate 1:n (vaatimukset) hyväksyntää:",
      },
    ]);
    // The session stays on the gate, and nothing is written for the user.
    await expect(page.getByText("VAIHE 4 / 13")).toBeVisible();
    await expect(page.getByText(/Muutospyyntö kirjattu/)).toHaveCount(0);
  });

  test("business context and open assumptions render", async ({ page }) => {
    await loginAsDev(page);
    await page.goto("/sessions/ses_gate1_ready");

    // The timeline's card names the same topics, so look in the workspace.
    const review = page.getByRole("main");
    await expect(review.getByText("Liiketoimintakonteksti", { exact: true })).toBeVisible();
    await expect(
      review.getByText("Three people manually review invoices every morning."),
    ).toBeVisible();
    await expect(review.getByText("Faster processing")).toBeVisible();

    await expect(review.getByText("Avoimet oletukset", { exact: true })).toBeVisible();
    await expect(review.getByText("Invoices arrive as PDF email attachments.")).toBeVisible();
    await expect(review.getByText("Currency is always EUR.")).toBeVisible();
    // Each assumption says once whether it is confirmed; there is no counter.
    await expect(review.getByTestId("assumption-status")).toHaveText([
      "Vahvistettu",
      "Vahvistamaton",
      "Vahvistamaton",
      "Vahvistettu",
    ]);
    await expect(review.getByText(/kuitattu/)).toHaveCount(0);
  });

  test("the review is one sheet in plain words, with no identifiers", async ({ page }) => {
    await loginAsDev(page);
    await page.goto("/sessions/ses_gate1_ready");

    const sheet = page.getByTestId("gate1-review");
    await expect(sheet.getByRole("heading", { level: 2 })).toHaveText([
      "Kerätyt vaatimukset",
      "Liiketoimintakonteksti",
      "Avoimet oletukset",
    ]);
    // What the agent wrote as identifiers is shown in words: the known ones
    // with their Finnish label, an unknown one as readable text.
    // A known knowledge process also says in one line what it means.
    await expect(sheet.getByText("Tiedon tallentaminen", { exact: true })).toBeVisible();
    await expect(
      sheet.getByText("Tarvittava tieto poimitaan dokumenteista, tallenteista ja viesteistä."),
    ).toBeVisible();
    await expect(sheet.getByText("Invoice review", { exact: true })).toBeVisible();
    await expect(sheet.getByText("Vaikutus: komponenttien valinta")).toBeVisible();
    await expect(sheet.getByText("Vaikutus: data retention policy")).toBeVisible();
    await expect(sheet).not.toContainText(/[a-z]_[a-z]/);

    // One sheet: nothing inside it is a card of its own.
    const nested = await sheet.evaluate(
      (el) => [...el.querySelectorAll("*")].filter((child) => child.classList.contains("rounded-xl")).length,
    );
    expect(nested).toBe(0);

    // A long assumption wraps inside the sheet at a phone's width.
    await page.setViewportSize({ width: 390, height: 844 });
    const overflow = await sheet.evaluate((el) => el.scrollWidth - el.clientWidth);
    expect(overflow).toBeLessThanOrEqual(0);
  });

  test("an assumption is corrected under its row, and the correction goes to the wizard as a chat turn", async ({ page }) => {
    await loginAsDev(page);
    await slowChat(page);
    await page.goto("/sessions/ses_gate1_ready");
    const sends = await recordChatSends(page);
    const review = page.getByTestId("gate1-review");

    // The control is in view without a pointer over the row.
    const change = review.getByRole("button", { name: "Muuta: Oletus 2" });
    await expect(change).toBeVisible();
    await expect(change).toHaveCSS("opacity", "1");
    await change.click();
    // An assumption holds or it does not: that choice comes first, and the
    // field under it takes what is right instead.
    await expect(review.getByRole("radio", { name: "Pitää paikkansa", exact: true })).toBeFocused();
    const field = review.getByLabel("Mikä on oikein?");
    await expect(field).toBeVisible();
    // Cancel closes the field and sends nothing.
    await review.getByRole("button", { name: "Peruuta" }).click();
    await expect(field).toHaveCount(0);
    await expect(change).toBeFocused();

    await change.click();
    await field.fill("Myös SEK ja NOK.");
    await review.getByRole("button", { name: "Lähetä wizardille" }).click();
    await expect(field).toHaveCount(0);
    await expect(review).toContainText("Wizard käsittelee muutosta…");
    expect(await sends()).toEqual([
      'Koskee oletusta 2, lainattuna: "Currency is always EUR."\n\nMyös SEK ja NOK.',
    ]);

    // A business-context item has the same control.
    await review.getByRole("button", { name: "Muuta: Nykyprosessi" }).click();
    await expect(review.getByLabel("Mikä on oikein?")).toBeFocused();
  });

  test("the knowledge processes are corrected by choosing among the wizard's three", async ({ page }) => {
    await loginAsDev(page);
    await slowChat(page);
    await page.goto("/sessions/ses_gate1_ready");
    const sends = await recordChatSends(page);
    const review = page.getByTestId("gate1-review");

    await review.getByRole("button", { name: "Muuta: Tietoprosessit" }).click();
    // The process that holds now is ticked; nothing is sent until the choice changes.
    const capture = review.getByRole("checkbox", { name: /^Tiedon tallentaminen/ });
    await expect(capture).toBeFocused();
    await expect(capture).toBeChecked();
    await expect(review.getByRole("checkbox")).toHaveCount(3);
    const send = review.getByRole("button", { name: "Lähetä wizardille" });
    await expect(send).toBeDisabled();

    await review.getByRole("checkbox", { name: /^Tiedon haku/ }).check();
    await send.click();
    expect(await sends()).toEqual([
      'Koskee liiketoimintakontekstin kohtaa Tietoprosessit, lainattuna: "Tiedon tallentaminen; Invoice review"\n\n' +
        "Oikeat tietoprosessit: tiedon tallentaminen (knowledge capture), tiedon haku (knowledge access)",
    ]);
  });

  test("an assumption that holds is confirmed with one choice", async ({ page }) => {
    await loginAsDev(page);
    await slowChat(page);
    await page.goto("/sessions/ses_gate1_ready");
    const sends = await recordChatSends(page);
    const review = page.getByTestId("gate1-review");

    await review.getByRole("button", { name: "Muuta: Oletus 2" }).click();
    await review.getByRole("radio", { name: "Pitää paikkansa", exact: true }).check();
    await review.getByRole("button", { name: "Lähetä wizardille" }).click();
    expect(await sends()).toEqual([
      'Koskee oletusta 2, lainattuna: "Currency is always EUR."\n\nOletus pitää paikkansa. Merkitse se vahvistetuksi.',
    ]);
  });

  test("approve advances past the gate once context is complete", async ({ page }) => {
    await loginAsDev(page);
    await page.goto("/sessions/ses_gate1_ready");

    const approveButton = page.getByTestId("gate1-actions").getByRole("button", { name: "Hyväksy vaatimukset" });
    await expect(approveButton).toBeEnabled();
    await approveButton.click();

    await expect(page.getByText("VAIHE 5 / 13")).toBeVisible(AFTER_ACTION);
  });
});

test.describe("Gates 2–4 — the same decision bar", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test.beforeEach(async ({ request }) => {
    await resetMockSessions(request);
  });

  test("Gate 2 says what to do now, keeps its decision in view and opens the chat beside it", async ({ page }) => {
    await loginAsDev(page);
    await page.goto("/sessions/ses_gate2_pending");

    await expect(page.getByTestId("workspace-phase")).toHaveText("Gate 2: ratkaisun rakenne");
    // One line under the title instead of the generic gate banner: what to
    // check. The approval is asked once, by its button.
    await expect(page.getByTestId("now-line")).toHaveText("Tarkista työnkulku ja blueprint.");
    await expect(page.getByText("Tämä on gate-vaihe")).toHaveCount(0);

    const bar = page.getByTestId("gate2-actions");
    await expect(bar).toBeInViewport();
    await expect(bar.getByRole("button", { name: "Hyväksy ratkaisun rakenne" })).toBeInViewport();
    await expect(bar).toContainText("Hyväksynnän jälkeen wizard rakentaa tästä rakenteesta PoC-paketin.");
    // The agent's summary of the gate is in the chat: it starts open here,
    // though the chat is collapsed from the workflow step on.
    await expect(page.getByTestId("chat-dock")).toHaveAttribute("data-chat-open", "true");
  });

  test("approve advances past Gate 2 to a step with no way back", async ({ page }) => {
    await loginAsDev(page);
    await page.goto("/sessions/ses_gate2_pending");

    await page.getByTestId("gate2-actions").getByRole("button", { name: "Hyväksy ratkaisun rakenne" }).click();

    await expect(page.getByText("VAIHE 10 / 13")).toBeVisible(AFTER_ACTION);
    await expect(page.getByTestId("gate2-actions")).toHaveCount(0);
    // Between gates there are no step buttons: the wizard works there.
    await expect(page.getByRole("button", { name: "Edellinen" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Seuraava vaihe" })).toHaveCount(0);
  });

  test("request changes at Gate 2 references the gate in the chat", async ({ page }) => {
    await loginAsDev(page);
    await page.goto("/sessions/ses_gate2_pending");
    const references = await recordChatReferences(page);

    await page.getByTestId("gate2-actions").getByRole("button", { name: "Pyydä muutoksia" }).click();

    expect(await references()).toEqual([
      {
        key: "gate:9",
        label: "Gate 2 · Ratkaisun rakenne",
        prefix: "Muutospyyntö ennen Gate 2:n (ratkaisun rakenne) hyväksyntää:",
      },
    ]);
  });

  test("the timeline shows the stages at a glance, and what an approval checks and a change to an approved stage behind a press", async ({ page }) => {
    await loginAsDev(page);
    await page.goto("/sessions/ses_gate2_pending");

    const timeline = page.getByRole("navigation", { name: "Vaiheet" });
    // The row is the four gates; a stage's steps are behind a press on it,
    // the stage in progress included.
    await expect(timeline.getByTestId("timeline-stage-2")).toHaveAttribute("aria-expanded", "false");
    await expect(timeline.getByText("Hyväksy ratkaisun rakenne")).toHaveCount(0);
    await timeline.getByTestId("timeline-stage-2").click();
    await expect(timeline.getByTestId("timeline-stage-2")).toHaveAttribute("aria-expanded", "true");
    // The gate's row is named by its decision.
    await expect(timeline.getByText("Hyväksy ratkaisun rakenne")).toBeVisible();

    // At a glance a stage is its mark and its topic: no gate tag, no status
    // word, no step count, and no card that repeats the line above the workspace.
    await expect(page.getByTestId("timeline-now")).toHaveCount(0);
    await expect(page.getByTestId("timeline-stage-1")).toHaveText("Vaatimukset");
    await expect(page.getByTestId("timeline-stage-2")).toHaveText("2Ratkaisun rakenne");
    await expect(timeline).not.toContainText("Hyväksynnässä tarkistat:");
    await expect(page.getByTestId("now-line")).not.toContainText("Nyt");

    // What the approval checks is behind its own control on the gate's row.
    const checksToggle = timeline.getByRole("button", { name: "Hyväksynnässä tarkistat: Ratkaisun rakenne" });
    await expect(checksToggle).toHaveAttribute("aria-expanded", "false");
    await checksToggle.click();
    await expect(page.getByTestId("gate-checks-2").getByRole("listitem")).toHaveText([
      "Komponentit vaiheittain",
      "Blueprint: vaiheet, syötteet ja tulokset",
      "Työnkulkukaavio ja roolit",
    ]);

    // Gate 1 is approved: its stage opens on a press, and a change there
    // reopens it (asked first), and then goes to the wizard through the chat.
    const references = await recordChatReferences(page);
    await expect(page.getByRole("button", { name: "Muuta hyväksyttyä vaihetta: Vaatimukset" })).toHaveCount(0);
    await page.getByTestId("timeline-stage-1").click();
    // One stage is open at a time: Gate 2's panel made way for Gate 1's.
    await expect(timeline.getByTestId("timeline-stage-2")).toHaveAttribute("aria-expanded", "false");
    await expect(page.getByTestId("gate-checks-2")).toHaveCount(0);
    await page.getByRole("button", { name: "Muuta hyväksyttyä vaihetta: Vaatimukset" }).click();
    expect(await references()).toEqual([]);
    await page.getByTestId("gate-reopen-1").getByRole("button", { name: "Avaa uudelleen" }).click();
    await expect(page.getByTestId("workspace-phase")).toHaveText("Gate 1: vaatimukset", AFTER_ACTION);
    // Reopened, the panel has done its job; the change is said in the chat.
    await expect(timeline.getByTestId("timeline-stage-1")).toHaveAttribute("aria-expanded", "false");
    expect(await references()).toEqual([
      {
        key: "gate:4",
        label: "Gate 1 · Vaatimukset",
        prefix: "Haluan muuttaa hyväksyttyä vaihetta Gate 1 (vaatimukset):",
      },
    ]);
  });

  test("a gate that is already approved is not asked again: the next gate's decision is the way on", async ({
    page,
    request,
    baseURL,
  }) => {
    // This session has passed Gate 2. Put it back on that step, as a step
    // moved back by the agent or through the API leaves it.
    await setMockSessionStep(request, baseURL as string, "ses_laskut", 9);
    await loginAsDev(page);
    await page.goto("/sessions/ses_laskut");

    await expect(page.getByTestId("workspace-phase")).toHaveText("Gate 2: ratkaisun rakenne");
    // The session is in the next stage: the line is the PoC step's, and no
    // gate is offered until what the next one reviews is there.
    await expect(page.getByTestId("now-line")).toContainText("Testiajo käynnistyy PoC-välilehdellä");
    await expect(page.getByTestId("gate2-actions")).toHaveCount(0);
    await expect(page.getByTestId("gate3-actions")).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Seuraava vaihe" })).toHaveCount(0);

    // A test run has succeeded: Gate 3 is decided from here, and the session
    // is moved onto it and past it by the approval.
    await setMockSessionStep(request, baseURL as string, "ses_laskut", 9, "run-1");
    await page.reload();
    await expect(page.getByTestId("gate2-actions")).toHaveCount(0);
    await page.getByTestId("gate3-actions").getByRole("button", { name: "Hyväksy testiajo" }).click();
    await expect(page.getByText("VAIHE 12 / 13")).toBeVisible(AFTER_ACTION);
  });

  test("approving Gate 4 ends the work: no bar, no next step, and the package named", async ({
    page,
    request,
    baseURL,
  }) => {
    await setMockSessionStep(request, baseURL as string, "ses_laskut", 13);
    await loginAsDev(page);
    await page.goto("/sessions/ses_laskut");

    await expect(page.getByTestId("workspace-phase")).toHaveText("Gate 4: luovutus");
    const bar = page.getByTestId("gate4-actions");
    await expect(bar).toContainText("Hyväksyntä päättää työn, ja käyttöönottopaketin voi ladata.");
    await bar.getByRole("button", { name: "Hyväksy luovutus" }).click();

    await expect(page.getByTestId("solution-done")).toBeVisible(AFTER_ACTION);
    await expect(page.getByTestId("gate4-actions")).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Seuraava vaihe" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Edellinen" })).toHaveCount(0);
    // This session has no successful test run, so the card says how to get the
    // package; it is said once, so the line under the title is gone.
    await expect(page.getByTestId("solution-done")).toContainText(
      "Paketti avautuu PoC-välilehdellä, kun sandbox-ajo on onnistunut.",
    );
    await expect(page.getByTestId("now-line")).toHaveCount(0);
    // Nothing is left to check, so the last stage has no checklist to open.
    await expect(page.getByTestId("gate-checks-toggle-4")).toHaveCount(0);
  });

  test("a test run that succeeded is approved from the PoC step, without Next step", async ({
    page,
    request,
    baseURL,
  }) => {
    // The step follows the files the wizard writes, and a test run is not one:
    // the session stays on the PoC step when the run has succeeded.
    await setMockSessionStep(request, baseURL as string, "ses_laskut", 10);
    await loginAsDev(page);
    await page.goto("/sessions/ses_laskut");
    await expect(page.getByTestId("workspace-phase")).toHaveText("PoC");
    // No run yet: nothing to approve, and no step button either.
    await expect(page.getByTestId("gate3-actions")).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Seuraava vaihe" })).toHaveCount(0);

    await setMockSessionStep(request, baseURL as string, "ses_laskut", 10, "run-1");
    await page.reload();
    await expect(page.getByTestId("now-line")).toContainText(
      "Testi onnistui. Tarkista tulos PoC-välilehdellä ja valitse sitten Hyväksy testiajo tai Pyydä muutoksia.",
    );
    // The line points at the bar it names: the approve button takes the focus.
    await page.getByTestId("now-line").getByRole("button", { name: "Näytä hyväksyntä sivulla" }).click();
    await expect(page.getByTestId("gate3-actions").getByRole("button", { name: "Hyväksy testiajo" })).toBeFocused();
    await expect(page.getByRole("button", { name: "Seuraava vaihe" })).toHaveCount(0);
    const bar = page.getByTestId("gate3-actions");
    await bar.getByRole("button", { name: "Hyväksy testiajo" }).click();

    // Approved in one press: the session is past Gate 3.
    await expect(page.getByText("VAIHE 12 / 13")).toBeVisible(AFTER_ACTION);
    await expect(page.getByTestId("gate-ring")).toHaveAccessibleName("3/4 gatea hyväksytty");
  });

  test("after Gate 3 the handover is approved from the documentation step, once the wizard has replied", async ({
    page,
  }) => {
    await loginAsDev(page);
    await page.goto("/sessions/ses_laskut");
    await page.getByTestId("gate3-actions").getByRole("button", { name: "Hyväksy testiajo" }).click();

    await expect(page.getByText("VAIHE 12 / 13")).toBeVisible(AFTER_ACTION);
    await expect(page.getByTestId("workspace-phase")).toHaveText("Dokumentaatio");
    // The wizard answers the approval; then Gate 4's decision is here, with no
    // "Next step" to find first.
    const bar = page.getByTestId("gate4-actions");
    await expect(bar.getByRole("button", { name: "Hyväksy luovutus" })).toBeVisible(AFTER_ACTION);
    await expect(page.getByRole("button", { name: "Seuraava vaihe" })).toHaveCount(0);
    await bar.getByRole("button", { name: "Hyväksy luovutus" }).click();

    await expect(page.getByTestId("solution-done")).toBeVisible(AFTER_ACTION);
    await expect(page.getByTestId("gate-ring")).toHaveAccessibleName("4/4 gatea hyväksytty");
  });

  test("the wizard's reply at a gate carries the approval", async ({ page, request, baseURL }) => {
    // ses_chatbot has a conversation that ends in the wizard's reply.
    await setMockSessionStep(request, baseURL as string, "ses_chatbot", 9);
    await loginAsDev(page);
    await page.goto("/sessions/ses_chatbot");
    await expect(page.getByTestId("workspace-phase")).toHaveText("Gate 2: ratkaisun rakenne");

    // The same decision in the same words as the bar under the workspace.
    const inChat = page.getByTestId("chat-gate-action").getByRole("button", { name: "Hyväksy ratkaisun rakenne" });
    await expect(inChat).toBeVisible();
    await expect(page.getByTestId("gate2-actions").getByRole("button", { name: "Hyväksy ratkaisun rakenne" })).toBeVisible();
    await expect(page.getByTestId("chat-gate-action")).toHaveCount(1);
    await inChat.click();

    await expect(page.getByText("VAIHE 10 / 13")).toBeVisible(AFTER_ACTION);
    await expect(page.getByTestId("chat-event")).toContainText("Gate 2 hyväksytty", AFTER_ACTION);
    await expect(page.getByTestId("chat-gate-action")).toHaveCount(0);
  });

  test("Gate 3 asks for the test run before the approval", async ({ page }) => {
    await loginAsDev(page);
    await page.goto("/sessions/ses_laskut");

    await expect(page.getByTestId("workspace-phase")).toHaveText("Gate 3: testiajo");
    // No successful run yet: the line names the run, not the approval.
    await expect(page.getByTestId("now-line")).toContainText(
      "Tarkista testiajon tulos PoC-välilehdellä. Kerro chatissa, jos jotain pitää muuttaa.",
    );
    await expect(
      page.getByTestId("gate3-actions").getByRole("button", { name: "Hyväksy testiajo" }),
    ).toBeVisible();
  });
});
