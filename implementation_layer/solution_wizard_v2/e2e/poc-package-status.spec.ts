import { test, expect, type Page } from "@playwright/test";
import { loginAsDev } from "./helpers/auth";
import { resetMockSessions } from "./helpers/mock";

/**
 * Step 1 of the PoC tab has one status line for the files and the preflight
 * together. It says "ready to run" only once the check passed: a failed check
 * reads as errors (#88) with its findings under it, a check that could not
 * finish (the time limit, a sandbox error) as not finished with a retry, a
 * running check as checking, and a package nobody could check (no sandbox, or
 * a busy one) as generated. The mock store has no PoC package, so the package API is answered
 * here.
 */

// A session past Gate 2 (step 11): before it the PoC tab is locked and asks
// for no package.
const SESSION = "ses_laskut";

type Check = "succeeded" | "failed" | "timeout-once" | "no-sandbox" | "busy-once";

async function fakePackage(page: Page, check: Check, opts: { hold?: Promise<void> } = {}) {
  await page.route(`**/api/sessions/${SESSION}/poc/files`, (route) =>
    route.fulfill({
      json: {
        generated: true,
        ready: true,
        problems: [],
        files: ["run_poc.py", "requirements.txt", "README.md"],
        version: "v1",
      },
    }),
  );
  let checks = 0;
  await page.route(`**/api/sessions/${SESSION}/poc/check`, (route) => {
    checks += 1;
    if (check === "no-sandbox") return route.fulfill({ status: 503, json: { detail: "no sandbox" } });
    if (check === "busy-once" && checks === 1) {
      return route.fulfill({
        status: 429,
        headers: { "Retry-After": "1" },
        json: { detail: { error: "sandbox_busy" } },
      });
    }
    return route.fulfill({ json: { run_id: "check-1" } });
  });
  const passed = [{ log: "all stages load" }, { done: true, phase: "succeeded" }];
  const found = [
    { log: "PROBLEM: run_poc.py cannot import gaik.software_modules.missing" },
    { done: true, phase: "failed" },
  ];
  // The Job hit its limit before the check script reported anything.
  const timedOut = [{ log: "Loading" }, { done: true, phase: "timeout", message: "the run passed its limit" }];
  let streams = 0;
  await page.route(`**/api/sessions/${SESSION}/runs/check-1/stream`, async (route) => {
    streams += 1;
    const events = check === "failed" ? found : check === "timeout-once" && streams === 1 ? timedOut : passed;
    await opts.hold;
    await route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body: events.map((e) => `data: ${JSON.stringify(e)}\n\n`).join(""),
    });
  });
}

async function openPocTab(page: Page) {
  await loginAsDev(page);
  await page.goto(`/sessions/${SESSION}`);
  await page.getByRole("tab", { name: "PoC" }).click();
}

test.describe("PoC package status", () => {
  test.beforeEach(async ({ request }) => {
    await resetMockSessions(request);
  });

  test("a package that passed the check is ready to run", async ({ page }) => {
    await fakePackage(page, "succeeded");
    await openPocTab(page);

    const status = page.getByTestId("poc-package-status");
    await expect(status).toHaveAttribute("data-state", "ready");
    await expect(status).toHaveText("Valmis ajettavaksi");
    await expect(page.getByTestId("poc-input-upload-label")).toHaveClass(/btn-brand/);
    await expect(page.getByTestId("poc-run-sandbox")).toHaveClass(/btn-secondary/);
  });

  test("a failed check says the package has errors and lists them under it", async ({ page }) => {
    await fakePackage(page, "failed");
    await openPocTab(page);

    const status = page.getByTestId("poc-package-status");
    await expect(status).toHaveAttribute("data-state", "failed");
    await expect(status).toHaveText("Paketissa on virheitä");

    const findings = page.getByTestId("poc-check-problems");
    await expect(findings).toContainText("Tarkistus löysi virheitä, jotka kaatavat ajon:");
    await expect(findings.getByRole("listitem")).toHaveText([
      "run_poc.py cannot import gaik.software_modules.missing",
    ]);

    const run = page.getByTestId("poc-run-sandbox");
    await expect(run).toHaveClass(/btn-secondary/);
    await expect(run).toBeEnabled();
  });

  test("a check that hit its time limit did not finish: no errors named, and a retry", async ({ page }) => {
    await fakePackage(page, "timeout-once");
    await openPocTab(page);

    const status = page.getByTestId("poc-package-status");
    await expect(status).toHaveAttribute("data-state", "unfinished");
    await expect(status).toContainText("Tarkistus ei valmistunut");
    await expect(status).not.toContainText("Paketissa on virheitä");
    await expect(page.getByTestId("poc-check-problems")).toHaveCount(0);
    const run = page.getByTestId("poc-run-sandbox");
    await expect(run).toBeEnabled();
    await expect(run).toHaveClass(/btn-secondary/);

    await page.getByTestId("poc-check-retry").click();
    await expect(status).toHaveAttribute("data-state", "ready");
    await expect(status).toHaveText("Valmis ajettavaksi");
    await expect(page.getByTestId("poc-input-upload-label")).toHaveClass(/btn-brand/);
  });

  test("while the check runs the package is not called ready yet", async ({ page }) => {
    let release!: () => void;
    const hold = new Promise<void>((resolve) => {
      release = resolve;
    });
    await fakePackage(page, "succeeded", { hold });
    await openPocTab(page);

    const status = page.getByTestId("poc-package-status");
    await expect(status).toHaveAttribute("data-state", "checking");
    await expect(status).toHaveText("Tarkistetaan pakettia…");

    release();
    await expect(status).toHaveAttribute("data-state", "ready");
    await expect(status).toHaveText("Valmis ajettavaksi");
  });

  test("a package nobody could check reads as generated, not ready", async ({ page }) => {
    await fakePackage(page, "no-sandbox");
    await openPocTab(page);

    const status = page.getByTestId("poc-package-status");
    await expect(status).toHaveAttribute("data-state", "unchecked");
    await expect(status).toHaveText("Generoitu PoC-paketti");
  });

  test("a busy sandbox leaves the package unchecked until the check runs after Retry-After", async ({ page }) => {
    await fakePackage(page, "busy-once");
    await openPocTab(page);

    const status = page.getByTestId("poc-package-status");
    await expect(status).toHaveAttribute("data-state", "unchecked");
    await expect(status).not.toContainText("Valmis ajettavaksi");
    await expect(status).toHaveAttribute("data-state", "ready", { timeout: 10_000 });
  });
});
