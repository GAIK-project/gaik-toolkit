import { test, expect, type Page } from "@playwright/test";
import { loginAsDev } from "./helpers/auth";
import { resetMockSessions } from "./helpers/mock";
import { setMockSessionStep } from "./helpers/dev-step";
import { selectWorkspaceTab } from "./helpers/workspace";

// A gate action is a server action: on a busy dev server it takes a few seconds.
const AFTER_ACTION = { timeout: 20_000 };

const MOVED = "Sessio oli jo edennyt toisessa ikkunassa, joten päätöstäsi ei tallennettu.";

/**
 * A gate approval made on a page the session has already left (another tab
 * decided first), and what an approval sends to the chat.
 * Each test uses its own e2e-only mock fixture (lib/mock-sessions.ts).
 */

// Answers POST /chat as wizard_api streams it, and collects what was sent.
// While `failing` is set the chat answers 500 instead.
async function fakeChat(page: Page) {
  const state = { sent: [] as string[], failing: false };
  await page.route("**/api/sessions/*/chat", (route) => {
    if (route.request().method() !== "POST") return route.continue();
    if (state.failing) return route.fulfill({ status: 500, contentType: "application/json", body: "{}" });
    state.sent.push((route.request().postDataJSON() as { message: string }).message);
    return route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body: `data: ${JSON.stringify({ delta: "Selvä." })}\n\ndata: ${JSON.stringify({ done: true })}\n\n`,
    });
  });
  return state;
}

test.describe("a gate decision on a page the session has left", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test.beforeEach(async ({ request }) => {
    await resetMockSessions(request);
  });

  test("an approval from a page left open approves nothing and says so", async ({ page, context }) => {
    await loginAsDev(page);
    const chat = await fakeChat(page);
    await page.goto("/sessions/ses_gate2_pending");
    await expect(page.getByText("VAIHE 9 / 13")).toBeVisible();

    // Another tab approves Gate 2 and goes on to the next gate's step.
    const other = await context.newPage();
    await fakeChat(other);
    await other.goto("/sessions/ses_gate2_pending");
    await other.getByTestId("gate2-actions").getByRole("button", { name: "Hyväksy ratkaisun rakenne" }).click();
    await expect(other.getByText("VAIHE 10 / 13")).toBeVisible(AFTER_ACTION);
    await other.close();

    await page.getByTestId("gate2-actions").getByRole("button", { name: "Hyväksy ratkaisun rakenne" }).click();
    await expect(page.getByText(MOVED)).toBeVisible(AFTER_ACTION);
    await expect(page.getByText("VAIHE 10 / 13")).toBeVisible();
    await expect(page).toHaveURL(/notice=gate_moved/);
    // The agent is told about no approval from this page.
    expect(chat.sent).toEqual([]);
  });
});

test.describe("a gate approval and the chat", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test.beforeEach(async ({ request }) => {
    await resetMockSessions(request);
  });

  test("an approval removes the chip of its own gate only", async ({ page }) => {
    await loginAsDev(page);
    const chat = await fakeChat(page);
    await page.goto("/sessions/ses_gate2_pending");
    // Sent again until the page listens (it may still be loading its scripts).
    await expect(async () => {
      await page.evaluate(() =>
        window.dispatchEvent(
          new CustomEvent("gaik-wizard:chat-reference", {
            detail: { key: "gate:4", label: "Gate 1 · Vaatimukset", prefix: "Muutospyyntö Gate 1:een:" },
          }),
        ),
      );
      await expect(page.getByTestId("chat-reference")).toContainText("Gate 1", { timeout: 1000 });
    }).toPass(AFTER_ACTION);

    await page.getByTestId("gate2-actions").getByRole("button", { name: "Hyväksy ratkaisun rakenne" }).click();
    await expect(page.getByText("VAIHE 10 / 13")).toBeVisible(AFTER_ACTION);
    await expect.poll(() => chat.sent, AFTER_ACTION).toEqual(["Gate 2 hyväksytty paneelista, jatka."]);
    await expect(page.getByTestId("chat-reference")).toContainText("Gate 1");
  });

  test("the wake-up leaves the address, the open tab stays in it", async ({ page }) => {
    await loginAsDev(page);
    const chat = await fakeChat(page);
    await page.goto("/sessions/ses_ui_basics?wake=1&tab=blueprint");
    await expect.poll(() => chat.sent, AFTER_ACTION).toEqual(["Gate 1 hyväksytty paneelista, jatka."]);
    await expect(page).toHaveURL(/\/sessions\/ses_ui_basics\?tab=blueprint$/);
  });
});

/**
 * Gate 3 approves a test run of the package that is there. wizard_api keeps
 * the digest of the package the run that passed was started on, and refuses
 * the gate (409 gate_not_ready, reason package_changed) once the package has
 * another. The mock store keeps the same two digests and refuses the same way.
 * ses_laskut stands at Gate 3.
 */
test.describe("Gate 3 and a package changed after the test run", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  const SESSION = "ses_laskut";
  const approve = (page: Page) =>
    page.getByTestId("gate3-actions").getByRole("button", { name: "Hyväksy testiajo" });
  const STALE = "Tulos on aiemmasta paketista. Hyväksy, kun nykyisen paketin ajo on onnistunut.";

  test.beforeEach(async ({ request }) => {
    await resetMockSessions(request);
  });

  test("a refused approval says to run the test again and takes the user to the run", async ({
    page,
    request,
    baseURL,
  }) => {
    // The run that passed tested the package that is there.
    await setMockSessionStep(request, baseURL as string, SESSION, 11, "run-1", {
      testedPackage: "d1",
      packageDigest: "d1",
    });
    await loginAsDev(page);
    const chat = await fakeChat(page);
    await page.goto(`/sessions/${SESSION}?tab=blueprint`);
    await expect(approve(page)).toBeEnabled();
    await expect(page.getByTestId("gate-stale-result")).toHaveCount(0);

    // The package is changed behind the open page; the page has not read it.
    await setMockSessionStep(request, baseURL as string, SESSION, 11, "run-1", { packageDigest: "d2" });
    await approve(page).click();

    const notice = page.getByTestId("action-notice");
    await expect(notice).toContainText(
      "PoC-paketti muuttui viimeisen onnistuneen testiajon jälkeen, joten hyväksyntää ei tallennettu. Aja testi uudelleen ja hyväksy sitten.",
      AFTER_ACTION,
    );
    await expect(page).toHaveURL(/notice=package_changed/);
    // Not the notice that sends the user to the chat.
    await expect(page.getByText("Jatka chatissa, kunnes wizard esittää tuloksen.")).toHaveCount(0);
    // Nothing was approved, and the wizard is told of no approval.
    await expect(page.getByText("VAIHE 11 / 13")).toBeVisible();
    expect(chat.sent).toEqual([]);
    // The page has read the session again: the approval now waits, with its reason.
    await expect(page.getByTestId("gate-stale-result")).toHaveText(STALE);
    await expect(approve(page)).toBeDisabled();

    // The notice takes the user to the test run on the PoC tab, from whichever tab is open.
    await selectWorkspaceTab(page, "Blueprint");
    await notice.getByRole("button", { name: "Siirry testiajoon" }).click();
    await expect(page.getByRole("tab", { name: "PoC" })).toHaveAttribute("aria-selected", "true");
  });

  test("the approval waits with its reason before it is pressed, on another tab and after a reload", async ({
    page,
    request,
    baseURL,
  }) => {
    await setMockSessionStep(request, baseURL as string, SESSION, 11, "run-1", {
      testedPackage: "d1",
      packageDigest: "d2",
    });
    await loginAsDev(page);
    await fakeChat(page);
    await page.goto(`/sessions/${SESSION}?tab=blueprint`);
    await expect(page.getByRole("tab", { name: "Blueprint" })).toHaveAttribute("aria-selected", "true");
    await expect(page.getByTestId("gate-stale-result")).toHaveText(STALE);
    await expect(approve(page)).toBeDisabled();
    await expect(approve(page)).toHaveAccessibleDescription(STALE);
    // The line under the title asks for the run too, and points at no approval.
    const nowLine = page.getByTestId("now-line");
    await expect(nowLine).toHaveText(
      "PoC-paketti muuttui onnistuneen testiajon jälkeen. Aja testi uudelleen PoC-välilehdellä, niin testiajon voi hyväksyä.",
    );
    await expect(nowLine.getByRole("button")).toHaveCount(0);

    await page.reload();
    await expect(page.getByTestId("gate-stale-result")).toHaveText(STALE);
    await expect(approve(page)).toBeDisabled();

    // A run of the package that is there has passed: the gate opens.
    await setMockSessionStep(request, baseURL as string, SESSION, 11, "run-2", { testedPackage: "d2" });
    await page.reload();
    await expect(page.getByTestId("gate-stale-result")).toHaveCount(0);
    await expect(approve(page)).toBeEnabled();
    await expect(nowLine).toContainText("valitse sitten Hyväksy testiajo tai Pyydä muutoksia.");
    await expect(nowLine.getByRole("button", { name: "Näytä hyväksyntä sivulla" })).toBeVisible();
  });

  test("a session whose run has no digest is approved as before", async ({ page, request, baseURL }) => {
    // wizard_api without the digests, or a run recorded before they were kept.
    await setMockSessionStep(request, baseURL as string, SESSION, 11, "run-1", { packageDigest: "d2" });
    await loginAsDev(page);
    const chat = await fakeChat(page);
    await page.goto(`/sessions/${SESSION}?tab=blueprint`);
    await expect(page.getByTestId("gate-stale-result")).toHaveCount(0);
    await approve(page).click();
    await expect(page.getByText("VAIHE 12 / 13")).toBeVisible(AFTER_ACTION);
    await expect.poll(() => chat.sent, AFTER_ACTION).toEqual(["Gate 3 hyväksytty paneelista, jatka."]);
  });

  test("the PoC tab's own reading of the digests opens the gate when a run has passed since the page was read", async ({
    page,
    request,
    baseURL,
  }) => {
    // As the page reads the session, the run that passed tested another package.
    await setMockSessionStep(request, baseURL as string, SESSION, 11, "run-1", {
      testedPackage: "d1",
      packageDigest: "d2",
    });
    // The PoC tab reads the package itself. First the same as the page, then a
    // run of the current package has been recorded (nothing reads the page again).
    const files = { tested: "d1" };
    await page.route(`**/api/sessions/${SESSION}/poc/files`, (route) =>
      route.fulfill({
        json: {
          generated: true,
          ready: true,
          problems: [],
          files: ["run_poc.py"],
          version: "v2",
          package_digest: "d2",
          recordedRun: "run-1",
          testedPackage: files.tested,
        },
      }),
    );
    await page.route(`**/api/sessions/${SESSION}/poc/input`, (route) => route.fulfill({ json: { files: [] } }));
    await page.route(`**/api/sessions/${SESSION}/poc/check`, (route) =>
      route.fulfill({ status: 503, json: { detail: "no sandbox" } }),
    );
    await loginAsDev(page);
    await fakeChat(page);
    await page.goto(`/sessions/${SESSION}`);
    await expect(page.getByRole("tab", { name: "PoC" })).toHaveAttribute("aria-selected", "true");
    await expect(page.getByTestId("gate-stale-result")).toHaveText(STALE);
    await expect(approve(page)).toBeDisabled();

    files.tested = "d2";
    // The tab reads the package again when it is opened.
    await selectWorkspaceTab(page, "Blueprint");
    await selectWorkspaceTab(page, "PoC");
    await expect(page.getByTestId("gate-stale-result")).toHaveCount(0);
    await expect(approve(page)).toBeEnabled();
  });
});
