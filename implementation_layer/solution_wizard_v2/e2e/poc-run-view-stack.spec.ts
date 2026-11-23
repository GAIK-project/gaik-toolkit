import { test, expect } from "@playwright/test";
import { DEV_USERS, loginAsDev } from "./helpers/auth";
import { getWizardApiUrl, setApiSessionStep, waitForApiHealthy } from "./helpers/api";
import { createSession } from "./helpers/session";

const STACK_E2E = process.env.PLAYWRIGHT_STACK_E2E === "true";

function sessionIdFromPath(url: string): string {
  return new URL(url).pathname.split("/").pop() as string;
}

/**
 * The PoC run view (#94), against the real stack.
 *
 * The step used to stream a simulated log and finish green whether or not
 * anything had happened, which is what the customer's test report traced the
 * "Run PoC — Success" misunderstanding back to. There is now generation and a
 * separate sandbox run, and the run reports what wizard_api says it did.
 *
 * A cluster is not available here, so a started run comes back 503 naming the
 * missing piece. That is the point: it is a real answer from the real backend,
 * not a green badge over nothing.
 *
 * Run via Docker: ./scripts/docker-test.sh --step stack-e2e
 */
test.describe("#94 the PoC run view reports real runs (stack)", () => {
  test.skip(!STACK_E2E, "set PLAYWRIGHT_STACK_E2E=true (docker-test.sh --step stack-e2e)");

  test.beforeAll(async ({ request }) => {
    await waitForApiHealthy(request);
  });

  async function sessionAtPocStep(
    page: import("@playwright/test").Page,
    request: import("@playwright/test").APIRequestContext,
  ) {
    await loginAsDev(page, DEV_USERS.primary);
    await createSession(page, `Run view ${Date.now()}`);
    const id = sessionIdFromPath(page.url());
    await setApiSessionStep(request, id, 10);
    await page.reload({ waitUntil: "load" });
    const tab = page.getByRole("tab", { name: "PoC" });
    await expect(async () => {
      await tab.click();
      await expect(tab).toHaveAttribute("aria-selected", "true", { timeout: 1_000 });
    }).toPass({ timeout: 15_000 });
    return id;
  }

  test("generation and running are two separate controls", async ({ page, request }) => {
    test.setTimeout(120_000);
    await sessionAtPocStep(page, request);

    // One generates the package, the other runs it. The old single button
    // promised a run it never performed.
    await expect(
      page.getByRole("button", { name: /Generoi PoC-paketti|Generoi paketti uudelleen/ }),
    ).toBeVisible();
    await expect(page.getByTestId("poc-run-sandbox")).toBeVisible();
  });

  test("running is refused until a package exists", async ({ page, request }) => {
    test.setTimeout(120_000);
    await sessionAtPocStep(page, request);

    // Nothing has been generated, so there is nothing to run — and the control
    // says so instead of reporting success.
    await expect(page.getByTestId("poc-run-sandbox")).toBeDisabled();
  });

  test("a run that cannot start says why rather than going green", async ({
    page,
    request,
  }) => {
    test.setTimeout(120_000);
    const id = await sessionAtPocStep(page, request);
    const base = getWizardApiUrl();

    // The API is the one that decides; with no cluster configured it answers
    // 503 sandbox_unavailable (the missing piece is in its log, not the answer).
    // No simulated success anywhere in the path.
    const started = await request.post(`${base}/sessions/${id}/runs`);

    expect([409, 503]).toContain(started.status());
    const body = await started.json();
    const detail = JSON.stringify(body);
    expect(detail).toMatch(/gate|package|sandbox_unavailable/i);
    expect(detail).not.toMatch(/WIZARD_|namespace|kubernetes/i);
  });
});
