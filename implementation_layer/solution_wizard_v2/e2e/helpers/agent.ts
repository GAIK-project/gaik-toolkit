import type { APIRequestContext, Page } from "@playwright/test";
import { expect } from "@playwright/test";
import { getWizardApiUrl } from "./api";
import { DEV_USERS } from "./auth";

/** Opt-in local-only live-agent E2E (never CI). */
export function agentE2eEnabled(): boolean {
  if (process.env.CI) return false;
  return process.env.PLAYWRIGHT_AGENT_E2E === "true";
}

export function requireAgentE2e(): void {
  if (!agentE2eEnabled()) {
    throw new Error(
      "Set PLAYWRIGHT_AGENT_E2E=true (local only). Requires running stack with WIZARD_AGENT_CHAT=true + Claude login.",
    );
  }
  if (!process.env.WIZARD_API_URL?.trim()) {
    throw new Error("WIZARD_API_URL is required for agent E2E (e.g. http://127.0.0.1:8100)");
  }
}

/** Open chat dock if collapsed (BPMN steps start collapsed). */
export async function ensureChatOpen(page: Page): Promise<void> {
  const dock = page.getByTestId("chat-dock");
  await expect(dock).toBeVisible();
  if ((await dock.getAttribute("data-chat-open")) !== "true") {
    await page.getByTestId("chat-dock-toggle").click();
  }
  await expect(dock).toHaveAttribute("data-chat-open", "true");
}

/**
 * Send one chat message and wait until the assistant finishes streaming.
 * Asserts the reply is a live agent answer (not the mock fallback).
 */
export async function sendAgentChatAndWait(
  page: Page,
  message: string,
  opts: { timeoutMs?: number } = {},
): Promise<string> {
  const timeoutMs = opts.timeoutMs ?? 120_000;
  await ensureChatOpen(page);

  // By test id, not by role: the chat is the page's main content while the
  // live agent gathers requirements, and a complementary panel after that.
  const chat = page.getByTestId("chat-dock");
  const log = chat.getByRole("log");
  const messages = log.locator('[data-testid="chat-message"]');
  const before = await messages.count();

  // The empty start view's field has its own placeholder.
  await chat.locator('textarea[name="message"]').fill(message);
  await chat.getByRole("button", { name: /Lähetä|Send/i }).click();

  // Typing indicator or new assistant bubble appears, then streaming ends.
  await expect(chat.getByRole("button", { name: /Lähetä|Send/i })).toBeEnabled({
    timeout: timeoutMs,
  });

  await expect
    .poll(async () => messages.count(), { timeout: timeoutMs })
    .toBeGreaterThan(before);

  const bubbles = log.locator('[data-testid="chat-message"][data-role="assistant"]');
  const last = bubbles.last();
  await expect(last).not.toHaveText(/^\s*$/, { timeout: 10_000 });

  const text = ((await last.textContent()) ?? "").trim();
  expect(text.length, "agent reply should be non-empty").toBeGreaterThan(20);
  expect(text).not.toMatch(/Mock-vastaus|Mock reply/i);
  expect(text).not.toMatch(/⚠︎/);
  return text;
}

/** Jump session to BPMN phase (step 8) with Gate 1 approved — after agent Q&A. */
export async function jumpSessionToBpmnPhase(
  request: APIRequestContext,
  sessionId: string,
): Promise<void> {
  const base = getWizardApiUrl();
  const res = await request.patch(`${base}/sessions/${sessionId}`, {
    data: {
      step: 8,
      gate_statuses: {
        gate_1: "approved",
        gate_2: "pending",
        gate_3: "pending",
        gate_4: "pending",
      },
    },
    headers: { "Content-Type": "application/json" },
  });
  if (!res.ok()) {
    throw new Error(`jump to BPMN failed: ${res.status()} ${await res.text()}`);
  }
  const body = (await res.json()) as { step: number };
  if (body.step !== 8) {
    throw new Error(`expected step 8 after patch, got ${body.step}`);
  }
}

export function sessionIdFromUrl(url: string): string {
  const m = url.match(/\/sessions\/([^/?#]+)/);
  if (!m?.[1]) throw new Error(`no session id in URL: ${url}`);
  return m[1];
}

export { DEV_USERS };
