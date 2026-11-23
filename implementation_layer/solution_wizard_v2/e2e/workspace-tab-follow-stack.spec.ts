import { test, expect, type APIRequestContext, type Page } from "@playwright/test";
import { DEV_USERS, loginAsDev } from "./helpers/auth";
import { getWizardApiUrl, setApiSessionStep, waitForApiHealthy } from "./helpers/api";
import { createSession, readSessionAgain } from "./helpers/session";

const STACK_E2E = process.env.PLAYWRIGHT_STACK_E2E === "true";

function sessionIdFromPath(url: string): string {
  return new URL(url).pathname.split("/").pop() as string;
}

async function apiStep(request: APIRequestContext, sessionId: string): Promise<number> {
  const res = await request.get(`${getWizardApiUrl()}/sessions/${sessionId}`);
  expect(res.ok(), `read session failed: ${res.status()}`).toBe(true);
  return (await res.json()).step as number;
}

/**
 * #138 (U1) — the workspace panel follows chat-driven progress.
 *
 * What the customer hit on 28 Aug: the chat carried the session all the way
 * through a PoC while the workspace sat on whatever tab was last clicked, so
 * the finished PoC was never seen at all ("the chat and this user interface
 * are not in sync"). The panel has to follow forward across a milestone.
 * That it never follows backwards is covered by the unit tests of
 * nextTabForStepChange: since the Nov 2026 UX pass the page has no control
 * that steps back once the tabs are shown.
 *
 * Runs against the real stack (UI + wizard_api + Postgres), not the mock store.
 * The step is asserted through the API rather than the header, because the
 * header's step indicator is rendered differently once the BPMN layout takes
 * over ("VAIHE 8" there, "VAIHE 7 / 13" before it).
 */
test.describe("#138 workspace panel follows the session forward (stack)", () => {
  test.skip(!STACK_E2E, "set PLAYWRIGHT_STACK_E2E=true (docker-test.sh --step stack-e2e)");

  test.beforeAll(async ({ request }) => {
    await waitForApiHealthy(request);
  });

  async function newSessionAtStep(
    page: Page,
    request: APIRequestContext,
    step: number,
  ): Promise<string> {
    await loginAsDev(page, DEV_USERS.primary);
    await createSession(page, `Tab follow ${Date.now()}`);
    const id = sessionIdFromPath(page.url());
    // Gathering (steps 1–3) is advanced by the agent, not by the UI button.
    await setApiSessionStep(request, id, step);
    await page.reload({ waitUntil: "load" });
    await expect(page.getByRole("tablist")).toBeVisible();
    return id;
  }

  /**
   * Pick a tab, retrying until it sticks. The tablist renders server-side, so a
   * click can land before React has hydrated the panel — the button is there and
   * the click succeeds, but no handler runs yet and the selection silently does
   * not move. Retrying the click-then-assert pair is deterministic where a fixed
   * sleep would only be lucky.
   */
  async function selectTab(page: Page, name: string): Promise<void> {
    const tab = page.getByRole("tab", { name });
    await expect(async () => {
      await tab.click();
      await expect(tab).toHaveAttribute("aria-selected", "true", { timeout: 1_000 });
    }).toPass({ timeout: 15_000 });
  }

  test("crossing into the BPMN step pulls the panel to the workflow tab", async ({
    page,
    request,
  }) => {
    test.setTimeout(120_000);
    const id = await newSessionAtStep(page, request, 7);

    // Before the diagram exists there is no Työnkulku tab, and the session
    // opens on Blueprint. It is the only tab to be on: the PoC tab is locked
    // until Gate 2, and a press on it opens nothing.
    await expect(page.getByRole("tab", { name: "Työnkulku" })).toHaveCount(0);
    await expect(page.getByRole("tab", { name: "PoC" })).toHaveAttribute("aria-disabled", "true");
    await selectTab(page, "Blueprint");

    // The step moves while the page is open, as it does when the wizard
    // writes the diagram during a chat turn.
    await setApiSessionStep(request, id, 8);
    await readSessionAgain(page);

    await expect(page.getByRole("tab", { name: "Työnkulku" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    expect(await apiStep(request, id)).toBe(8);
  });

  test("crossing into the PoC step pulls the panel to the PoC tab", async ({ page, request }) => {
    test.setTimeout(120_000);
    // Step 9 is Gate 2, so the advance control there is the gate's own button.
    const id = await newSessionAtStep(page, request, 9);

    await selectTab(page, "Blueprint");

    await page.getByTestId("gate2-actions").getByRole("button", { name: "Hyväksy ratkaisun rakenne" }).click();

    await expect(page.getByRole("tab", { name: "PoC" })).toHaveAttribute("aria-selected", "true");
    expect(await apiStep(request, id)).toBe(10);
  });
});
