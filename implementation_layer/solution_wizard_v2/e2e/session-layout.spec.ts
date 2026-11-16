import { test, expect, type Page } from "@playwright/test";
import { loginAsDev } from "./helpers/auth";
import { resetMockSessions } from "./helpers/mock";
import { createSession, hydrated } from "./helpers/session";

/**
 * Layout bugs from the sprint 4 end-to-end review:
 * - a long conversation made the whole page scroll far past its content, with a
 *   second scrollbar, because each reply's screen-reader label escaped the
 *   chat's scroll box;
 * - an empty chat field stayed several lines tall after the chat had been narrow;
 * - the chat field and its box both drew a focus ring.
 *
 * And the phone layout of the session shell: a gate's decision bar on one
 * row, the line under the title at full width, and the steps as a card.
 */

async function newSession(page: Page) {
  await loginAsDev(page);
  await createSession(page, `layout ${Date.now()}`);
}

const chatField = (page: Page) => page.locator('textarea[name="message"]');

test.describe("session layout", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test.beforeEach(async ({ request }) => {
    await resetMockSessions(request);
  });

  test("a long conversation scrolls inside the chat, not the page", async ({ page }) => {
    await newSession(page);
    const field = chatField(page);
    const send = page.locator('form:has(textarea[name="message"]) button[type="submit"]');
    const log = page.getByRole("log");

    // Talk until the conversation is well taller than its box, so the later
    // replies (and their screen-reader labels) sit far below the window.
    for (let i = 1; i <= 12; i++) {
      await field.fill(`Viesti ${i}: kerron lisää nykyisestä prosessista ja sen ongelmista.`);
      await field.press("Enter");
      await expect(send).toBeEnabled({ timeout: 30_000 });
      const extra = await log.evaluate((el) => el.scrollHeight - el.clientHeight);
      if (extra > 600) break;
    }
    expect(await log.evaluate((el) => el.scrollHeight - el.clientHeight)).toBeGreaterThan(600);

    const pageOverflow = await page.evaluate(
      () => document.scrollingElement!.scrollHeight - window.innerHeight,
    );
    expect(pageOverflow).toBeLessThanOrEqual(0);
  });

  test("a long unbroken word wraps in the chat instead of widening it", async ({ page }) => {
    await newSession(page);
    const field = chatField(page);
    const send = page.locator('form:has(textarea[name="message"]) button[type="submit"]');
    await field.fill(`https://example.com/${"a".repeat(240)}`);
    await field.press("Enter");
    await expect(send).toBeEnabled({ timeout: 30_000 });

    const log = page.getByRole("log");
    expect(await log.evaluate((el) => el.scrollWidth - el.clientWidth)).toBeLessThanOrEqual(0);
  });

  test("an empty chat field is one line tall again after the chat was narrow", async ({ page }) => {
    await newSession(page);
    const field = chatField(page);
    const oneLine = await field.evaluate((el: HTMLElement) => el.offsetHeight);
    const dock = page.getByTestId("chat-dock");

    // Narrow the chat as closing or dragging it does, wait out the dock's width
    // transition, then edit the field so it measures itself while narrow.
    await dock.evaluate((el) => {
      el.style.width = "120px";
      el.style.minWidth = "0";
    });
    await expect.poll(() => field.evaluate((el: HTMLElement) => el.offsetWidth)).toBeLessThan(100);
    await field.fill("x");
    await field.fill("");
    await expect.poll(() => field.evaluate((el: HTMLElement) => el.offsetHeight)).toBeGreaterThan(oneLine);

    await dock.evaluate((el) => {
      el.style.width = "";
      el.style.minWidth = "";
    });
    await expect.poll(() => field.evaluate((el: HTMLElement) => el.offsetHeight)).toBe(oneLine);
  });

  test("the chat field and its box draw one focus ring between them", async ({ page }) => {
    await newSession(page);
    const field = chatField(page);
    await field.click();

    expect(await field.evaluate((el) => getComputedStyle(el).boxShadow)).toBe("none");
    // The box's ring fades in, so wait for it to finish.
    await expect
      .poll(() => field.evaluate((el) => getComputedStyle(el.parentElement!).boxShadow))
      .toContain("0px 0px 0px 3px");
  });
});

test.describe("session layout on a phone", () => {
  const PHONE = { width: 390, height: 844 };
  test.use({ viewport: PHONE });

  test.beforeEach(async ({ request }) => {
    await resetMockSessions(request);
  });

  // How far the page itself scrolls: it should not, in either direction.
  const pageOverflow = (page: Page) =>
    page.evaluate(() => ({
      x: document.scrollingElement!.scrollWidth - window.innerWidth,
      y: document.scrollingElement!.scrollHeight - window.innerHeight,
    }));

  // The vertical middle of each button in a bar: one value when they share a row.
  const buttonRows = (page: Page, testId: string) =>
    page
      .getByTestId(testId)
      .getByRole("button")
      .evaluateAll((els) => [
        ...new Set(
          els.map((el) => {
            const box = el.getBoundingClientRect();
            return Math.round((box.top + box.height / 2) / 4);
          }),
        ),
      ]);

  test("a gate's decision bar is one row and leaves the workspace most of the screen", async ({ page }) => {
    await loginAsDev(page);
    await page.goto("/sessions/ses_gate2_pending");

    // Ask for changes and approve keep their names on a phone, where approve
    // reads "Hyväksy". The bar has no reject control.
    const bar = page.getByTestId("gate2-actions");
    await expect(bar.getByRole("button", { name: /Hylkää/ })).toHaveCount(0);
    await expect(bar.getByRole("button", { name: "Pyydä muutoksia" })).toBeVisible();
    const approve = bar.getByRole("button", { name: "Hyväksy ratkaisun rakenne" });
    await expect(approve).toBeVisible();
    await expect(approve).toContainText("Hyväksy");

    expect(await buttonRows(page, "gate2-actions")).toHaveLength(1);
    const box = (await bar.boundingBox())!;
    expect(box.height).toBeLessThanOrEqual(72);
    expect(box.y + box.height).toBeLessThanOrEqual(PHONE.height);

    // The line under the title has the full width beside nothing.
    const now = (await page.getByTestId("now-line").boundingBox())!;
    expect(now.width).toBeGreaterThan(PHONE.width - 40);

    // The workspace between the header and the bar is more than half the screen.
    const workspace = (await page.locator("#main-content > .scroll-thin").boundingBox())!;
    expect(workspace.height).toBeGreaterThan(PHONE.height * 0.6);

    expect(await pageOverflow(page)).toEqual({ x: 0, y: 0 });
  });

  test("Gate 1's decision bar is one row too, with no previous button", async ({ page }) => {
    await loginAsDev(page);
    await page.goto("/sessions/ses_gate1_ready");

    // The bar has two decisions, as at the other gates: there is no way back from it.
    const bar = page.getByTestId("gate1-actions");
    await expect(bar.getByRole("button", { name: "Edellinen" })).toHaveCount(0);
    await expect(bar.getByRole("button", { name: "Pyydä muutoksia" })).toBeVisible();
    await expect(bar.getByRole("button", { name: "Hyväksy vaatimukset" })).toBeVisible();
    expect(await buttonRows(page, "gate1-actions")).toHaveLength(1);
    expect((await bar.boundingBox())!.height).toBeLessThanOrEqual(72);
    expect(await pageOverflow(page)).toEqual({ x: 0, y: 0 });
  });

  test("the steps open as a card that does not repeat the step count", async ({ page }) => {
    await loginAsDev(page);
    await page.goto("/sessions/ses_gate2_pending");

    const summary = page.getByTestId("steps-disclosure");
    await expect(summary).toHaveText("Vaihe 9/13");
    await summary.click();

    const card = page.getByRole("navigation", { name: "Vaiheet" });
    await expect(card).toBeVisible();
    await expect(card.getByText("Hyväksy ratkaisun rakenne")).toBeVisible();
    await expect(card).not.toContainText("Vaihe 9");
    // It takes the header's width, under the chat button, not a column beside it.
    expect((await card.boundingBox())!.width).toBeGreaterThan(PHONE.width - 40);
    expect(await pageOverflow(page)).toEqual({ x: 0, y: 0 });
  });

  test("the chat opens as a sheet from the header and gathering does not scroll the page", async ({ page }) => {
    await loginAsDev(page);
    await page.goto("/sessions/ses_gate2_pending");

    const dock = page.getByTestId("chat-dock");
    await expect(dock).toHaveAttribute("data-chat-open", "false");
    await page.getByRole("button", { name: "Keskustelu" }).click();
    await expect(dock).toHaveAttribute("data-chat-open", "true");
    await expect(chatField(page)).toBeVisible();
    expect(await pageOverflow(page)).toEqual({ x: 0, y: 0 });

    await page.goto("/sessions/ses_cv");
    await expect(page.getByTestId("workspace-phase")).toHaveText("Vaatimusten keruu");
    expect(await pageOverflow(page)).toEqual({ x: 0, y: 0 });
  });
});

test.describe("the gate row of the session bar", () => {
  test.beforeEach(async ({ request }) => {
    await resetMockSessions(request);
  });

  test("shows the four gates beside the session's name, with the step count at the bar's end", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await loginAsDev(page);
    await page.goto("/sessions/ses_gate2_pending");

    const bar = page.getByTestId("session-bar");
    await expect(bar.getByRole("heading", { level: 1 })).toHaveText("Gate 2 — pending review (e2e fixture)");
    expect((await bar.boundingBox())!.height).toBe(48);
    const row = bar.getByRole("navigation", { name: "Vaiheet" });
    // How far the session is, in approved gates, is the list's own name.
    await expect(row.getByRole("list")).toHaveAccessibleName("1/4 gatea hyväksytty");
    await expect(row.getByRole("listitem")).toHaveCount(4);
    for (const [gate, state] of [
      [1, "approved"],
      [2, "current"],
      [3, "pending"],
      [4, "pending"],
    ] as const) {
      await expect(row.getByTestId(`timeline-stage-${gate}`)).toHaveAttribute("data-state", state);
      await expect(row.getByTestId(`timeline-stage-${gate}`)).toHaveAttribute("aria-expanded", "false");
    }
    // The step count is not drawn (the stages show it); it stays for a screen
    // reader, outside the row, and nothing is open until a press.
    await expect(bar.getByTestId("timeline-progress")).toHaveText("Vaihe 9 / 13");
    await expect(bar.getByTestId("timeline-progress")).toHaveClass(/sr-only/);
    await expect(row).not.toContainText("Vaihe 9");
    await expect(row).not.toContainText("Skeeman suunnittelu");
    // The steps column is gone: the workspace starts at the sidebar's edge.
    const side = (await page.getByTestId("sidebar").boundingBox())!;
    const main = (await page.locator("#main-content").boundingBox())!;
    expect(main.x).toBe(side.x + side.width);
  });

  test("a stage opens under the row on a press, one at a time, and closes on Esc or a press elsewhere", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await loginAsDev(page);
    await page.goto("/sessions/ses_gate2_pending");
    const row = page.getByRole("navigation", { name: "Vaiheet" });
    const stage = (n: number) => row.getByTestId(`timeline-stage-${n}`);
    await expect(stage(2)).toBeVisible();

    await stage(2).click();
    await expect(stage(2)).toHaveAttribute("aria-expanded", "true");
    const steps = row.getByRole("listitem").filter({ hasText: "Visuaalinen työnkulku (BPMN)" }).last();
    await expect(steps).toBeVisible();
    // The step the session is on is marked in the panel.
    await expect(row.locator('[aria-current="step"]')).toHaveText(/Hyväksy ratkaisun rakenne/);
    // The panel lies over the workspace: nothing under the bar moved.
    const panel = page.locator(`#${await stage(2).getAttribute("aria-controls")}`);
    const box = (await panel.boundingBox())!;
    const bar = (await page.getByTestId("session-bar").boundingBox())!;
    expect(box.y).toBeGreaterThanOrEqual(bar.y + bar.height);
    expect(box.x + box.width).toBeLessThanOrEqual(1440);
    expect((await page.locator("#main-content").boundingBox())!.y).toBe(bar.y + bar.height);

    // Another stage takes its place.
    await stage(3).click();
    await expect(stage(3)).toHaveAttribute("aria-expanded", "true");
    await expect(stage(2)).toHaveAttribute("aria-expanded", "false");
    await expect(row.getByText("Hyväksy testiajo")).toBeVisible();
    await expect(row.getByText("Hyväksy ratkaisun rakenne")).toHaveCount(0);

    // Esc closes it and leaves the focus on its stage.
    await page.keyboard.press("Escape");
    await expect(stage(3)).toHaveAttribute("aria-expanded", "false");
    await expect(stage(3)).toBeFocused();

    // A press on the same stage closes it; so does a press elsewhere on the page.
    await stage(1).click();
    await expect(stage(1)).toHaveAttribute("aria-expanded", "true");
    await stage(1).click();
    await expect(stage(1)).toHaveAttribute("aria-expanded", "false");
    await stage(4).click();
    await expect(row.getByText("Hyväksy luovutus")).toBeVisible();
    await page.getByTestId("workspace-phase").click();
    await expect(stage(4)).toHaveAttribute("aria-expanded", "false");
    await expect(row.getByText("Hyväksy luovutus")).toHaveCount(0);
  });

  test("a mouse resting on a stage opens its panel, which follows the pointer and leaves with it; a press keeps it", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await loginAsDev(page);
    await page.goto("/sessions/ses_gate2_pending");
    await hydrated(page);
    const row = page.getByRole("navigation", { name: "Vaiheet" });
    const stage = (n: number) => row.getByTestId(`timeline-stage-${n}`);
    const panel = async (n: number) => page.locator(`#${await stage(n).getAttribute("aria-controls")}`);

    // Resting on a stage opens it without a press.
    await stage(2).hover();
    await expect(stage(2)).toHaveAttribute("aria-expanded", "true");
    await expect(row.getByText("Hyväksy ratkaisun rakenne")).toBeVisible();
    // The next stage's panel takes its place as the pointer moves along the row.
    await stage(3).hover();
    await expect(stage(3)).toHaveAttribute("aria-expanded", "true");
    await expect(stage(2)).toHaveAttribute("aria-expanded", "false");
    // The pointer can move into the panel and read it.
    await (await panel(3)).hover();
    await page.waitForTimeout(400);
    await expect(stage(3)).toHaveAttribute("aria-expanded", "true");
    // Off the row and the panel, it leaves.
    await page.getByTestId("workspace-phase").hover();
    await expect(stage(3)).toHaveAttribute("aria-expanded", "false");

    // A press keeps the panel the pointer opened: it stays when the pointer leaves, also over another stage.
    await stage(1).hover();
    await expect(stage(1)).toHaveAttribute("aria-expanded", "true");
    await stage(1).click();
    await expect(stage(1)).toHaveAttribute("aria-expanded", "true");
    await stage(3).hover();
    await page.getByTestId("workspace-phase").hover();
    await page.waitForTimeout(400);
    await expect(stage(1)).toHaveAttribute("aria-expanded", "true");
    // So does a press inside it: the question it asks is not lost to a stray pointer.
    await page.keyboard.press("Escape");
    await stage(1).hover();
    await row.getByTestId("gate-change-1").click();
    await page.getByTestId("workspace-phase").hover();
    await page.waitForTimeout(400);
    await expect(row.getByTestId("gate-reopen-1")).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(stage(1)).toHaveAttribute("aria-expanded", "false");

    // A pointer that only crosses the bar opens nothing.
    await page.mouse.move(700, 24);
    await page.mouse.move(40, 400, { steps: 4 });
    await page.waitForTimeout(300);
    for (const n of [1, 2, 3, 4]) await expect(stage(n)).toHaveAttribute("aria-expanded", "false");
  });

  test("Change in an approved stage asks with the focus on its answer, and Esc still closes the panel", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await loginAsDev(page);
    await page.goto("/sessions/ses_gate2_pending");
    await hydrated(page);
    const row = page.getByRole("navigation", { name: "Vaiheet" });
    const stage = row.getByTestId("timeline-stage-1");
    const change = row.getByTestId("gate-change-1");
    const question = row.getByTestId("gate-reopen-1");
    const confirm = row.getByTestId("gate-reopen-confirm-1");

    // The button that was pressed is replaced by the question: its answer takes the focus.
    await stage.click();
    await change.click();
    await expect(confirm).toBeFocused();
    // Not a box inside the panel's box.
    await expect(question).toHaveCSS("border-left-width", "0px");
    await expect(question).toHaveCSS("background-color", "rgba(0, 0, 0, 0)");
    // Cancelled, the focus is back where the question was asked from.
    await question.getByRole("button", { name: "Peruuta" }).click();
    await expect(question).toHaveCount(0);
    await expect(change).toBeFocused();

    // Esc from the question closes the panel, and the question leaves with it.
    await change.press("Enter");
    await expect(confirm).toBeFocused();
    await page.keyboard.press("Escape");
    await expect(stage).toHaveAttribute("aria-expanded", "false");
    await expect(stage).toBeFocused();
    await stage.press("Enter");
    await expect(change).toBeVisible();
    await expect(question).toHaveCount(0);
    await expect(stage).toBeFocused();

    // Also when the focus is on nothing: the panel is still the thing Esc closes.
    await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur());
    await page.keyboard.press("Escape");
    await expect(stage).toHaveAttribute("aria-expanded", "false");
    await expect(stage).toBeFocused();
  });

  test("where the chat opens over the workspace, a stage's panel lies over the chat and can be read", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1024, height: 768 });
    await loginAsDev(page);
    await page.goto("/sessions/ses_gate2_pending");
    await hydrated(page);
    await page.locator("[data-open-chat]").first().click();
    const chat = page.getByTestId("chat-dock");
    await expect(chat).toHaveAttribute("data-chat-open", "true");

    const stage = page.getByRole("navigation", { name: "Vaiheet" }).getByTestId("timeline-stage-2");
    await stage.click();
    const panel = page.locator(`#${await stage.getAttribute("aria-controls")}`);
    await expect(panel).toBeVisible();
    // The panel reaches over the chat's sheet, which stays open under it.
    const box = (await panel.boundingBox())!;
    const sheet = (await chat.boundingBox())!;
    expect(box.x + box.width).toBeGreaterThan(sheet.x);
    await expect(chat).toHaveAttribute("data-chat-open", "true");
    // At every point of a grid over the panel, the panel is what is on top.
    const covered = await panel.evaluate((el) => {
      const at = el.getBoundingClientRect();
      let under = 0;
      for (let x = at.left + 4; x < at.right - 4; x += 12) {
        for (let y = at.top + 4; y < at.bottom - 4; y += 12) {
          if (!el.contains(document.elementFromPoint(x, y))) under += 1;
        }
      }
      return under;
    });
    expect(covered).toBe(0);

    // The button that opens the sidebar stays on top of the bar's left end.
    await page.setViewportSize({ width: 820, height: 1100 });
    const opener = page.getByTestId("sidebar-open");
    await expect(opener).toBeVisible();
    // Once the sidebar, a drawer at this width, has slid out of the way.
    await expect
      .poll(() =>
        opener.evaluate((el) => {
          const at = el.getBoundingClientRect();
          return el.contains(document.elementFromPoint(at.left + at.width / 2, at.top + at.height / 2));
        }),
      )
      .toBe(true);
    await opener.click();
    await expect(page.getByTestId("sidebar")).toBeVisible();
  });

  test("a rejected gate says so beside its stage, without a press", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await loginAsDev(page);
    await page.goto("/sessions/ses_gate2_pending");
    const row = page.getByRole("navigation", { name: "Vaiheet" });
    await expect(row).not.toContainText("Hylätty");

    // The page has no reject control: a gate stands rejected in older sessions.
    const res = await page.request.post("/api/dev/set-step", {
      data: { id: "ses_gate2_pending", step: 9, rejected: true },
    });
    expect(res.ok()).toBe(true);
    await page.reload();

    await expect(row).toContainText("Hylätty", { timeout: 20_000 });
    // Outside the stage's button, whose name stays its topic; the panel does not say it twice.
    await expect(row.getByTestId("timeline-stage-2")).toHaveText("2Ratkaisun rakenne");
    await row.getByTestId("timeline-stage-2").click();
    await expect(row.getByText("Hylätty")).toHaveCount(1);
  });

  test("between a phone and the widest layout the row keeps to the stage in progress, and its panels stay in the window", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 800, height: 700 });
    await loginAsDev(page);
    await page.goto("/sessions/ses_gate2_pending");
    const row = page.getByRole("navigation", { name: "Vaiheet" });
    await expect(row).toBeVisible();
    // The other stages are their marks; their names stay for a screen reader.
    await expect(row.getByTestId("timeline-stage-2")).toHaveText("2Ratkaisun rakenne");
    await expect(row.getByTestId("timeline-stage-3")).toHaveAccessibleName("Testiajo");
    expect((await row.getByTestId("timeline-stage-3").boundingBox())!.width).toBeLessThan(40);
    // The step line of the phone layout is not shown beside the row.
    await expect(page.getByTestId("steps-disclosure")).toBeHidden();

    for (const gate of [1, 2, 3, 4]) {
      const stage = row.getByTestId(`timeline-stage-${gate}`);
      await stage.click();
      const panel = page.locator(`#${await stage.getAttribute("aria-controls")}`);
      const box = (await panel.boundingBox())!;
      expect(box.x).toBeGreaterThanOrEqual(0);
      expect(box.x + box.width).toBeLessThanOrEqual(800);
    }
    expect(
      await page.evaluate(() => document.scrollingElement!.scrollWidth - window.innerWidth),
    ).toBeLessThanOrEqual(0);
  });
});
