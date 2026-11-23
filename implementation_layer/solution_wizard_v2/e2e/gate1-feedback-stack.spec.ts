import { test, expect, type Page } from "@playwright/test";
import { DEV_USERS, loginAsDev } from "./helpers/auth";
import { getWizardApiUrl, setApiSessionStep, waitForApiHealthy } from "./helpers/api";
import { recordChatReferences } from "./helpers/chat-reference";
import { createSession } from "./helpers/session";

const STACK_E2E = process.env.PLAYWRIGHT_STACK_E2E === "true";

function sessionIdFromPath(url: string): string {
  return new URL(url).pathname.split("/").pop() as string;
}

// A new session put on Gate 1 (step 4). Gathering (1–3) is advanced by the
// agent, not from the UI, so the step is set through the API.
async function newSessionAtGate1(page: Page, request: Parameters<typeof setApiSessionStep>[0], title: string) {
  await loginAsDev(page, DEV_USERS.primary);
  await createSession(page, `${title} ${Date.now()}`);
  const id = sessionIdFromPath(page.url());
  await setApiSessionStep(request, id, 4);
  await page.reload({ waitUntil: "domcontentloaded" });
  await expect(page.getByTestId("workspace-phase")).toHaveText("Gate 1: vaatimukset");
  return id;
}

async function gate1Status(request: Parameters<typeof setApiSessionStep>[0], id: string): Promise<string> {
  const detail = await (await request.get(`${getWizardApiUrl()}/sessions/${id}`)).json();
  return detail.gate_statuses.gate_1;
}

/**
 * #126 and its follow-up — Gate 1 "Request changes" against the
 * real stack (UI + wizard_api + Postgres), so the assertions cover the API
 * path rather than the in-memory mock store.
 *
 * Run via Docker: ./scripts/docker-test.sh --step stack-e2e
 *
 * An objection used to append to the stored transcript through POST
 * /messages, which the live agent never reads, with a canned reply. Now a
 * change request is written in the chat itself (the bar hands the gate over as
 * a reference). The bar has no reject button any more. What must not happen
 * again:
 *   - "Request changes" moving the session back to step 3.
 *   - A canned acknowledgement nobody wrote.
 */
test.describe("#126 Gate 1 objections reach the agent through the chat (stack)", () => {
  test.skip(!STACK_E2E, "set PLAYWRIGHT_STACK_E2E=true (docker-test.sh --step stack-e2e)");

  test.beforeAll(async ({ request }) => {
    await waitForApiHealthy(request);
  });

  test("request changes stays on the gate and hands it to the chat", async ({ page, request }) => {
    test.setTimeout(120_000);
    const id = await newSessionAtGate1(page, request, "Gate1 feedback");
    const references = await recordChatReferences(page);

    await page.getByTestId("gate1-actions").getByRole("button", { name: "Pyydä muutoksia" }).click();

    expect(await references()).toEqual([
      {
        key: "gate:4",
        label: "Gate 1 · Vaatimukset",
        prefix: "Muutospyyntö ennen Gate 1:n (vaatimukset) hyväksyntää:",
      },
    ]);
    // The session stays on Gate 1, the gate stays open, and nothing was
    // written into the transcript on the user's behalf.
    await expect(page.getByText("VAIHE 4 / 13")).toBeVisible();
    expect(await gate1Status(request, id)).toBe("pending");
    await expect(page.getByText(/Muutospyyntö kirjattu/)).toHaveCount(0);
  });
});
