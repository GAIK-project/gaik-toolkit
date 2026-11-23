import type { APIRequestContext } from "@playwright/test";
import { getWizardApiUrl } from "./api";

/** Opt-in local-only live-agent E2E (never CI) — same gate as helpers/agent.ts. */
export function agentE2eEnabled(): boolean {
  if (process.env.CI) return false;
  return process.env.PLAYWRIGHT_AGENT_E2E === "true";
}

export type CreatedSession = { id: string; outputDir: string };

/** Create a session directly against wizard_api (no browser). */
export async function createSessionViaApi(
  request: APIRequestContext,
  userId: string,
  title: string,
): Promise<CreatedSession> {
  const base = getWizardApiUrl();
  const res = await request.post(`${base}/sessions`, {
    data: { user_id: userId, title },
    headers: { "Content-Type": "application/json" },
  });
  if (!res.ok()) {
    throw new Error(`create session failed: ${res.status()} ${await res.text()}`);
  }
  const body = (await res.json()) as { id: string; output_dir: string };
  return { id: body.id, outputDir: body.output_dir };
}

/**
 * Send one message to the live agent via wizard_api's SSE chat endpoint and
 * return the assembled assistant reply text. Request-only (no browser) —
 * this is testing agent/prompt behaviour (SKILL.md), not UI wiring, so it
 * talks to wizard_api directly rather than through the Next.js proxy.
 */
export async function sendChatViaApi(
  request: APIRequestContext,
  sessionId: string,
  message: string,
  opts: { locale?: string; timeoutMs?: number } = {},
): Promise<string> {
  const base = getWizardApiUrl();
  const res = await request.post(`${base}/sessions/${sessionId}/chat`, {
    data: { message, locale: opts.locale ?? "fi" },
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    timeout: opts.timeoutMs ?? 180_000,
  });
  if (!res.ok()) {
    throw new Error(`chat failed: ${res.status()} ${await res.text()}`);
  }
  const raw = await res.text();
  let text = "";
  for (const frame of raw.split("\n\n")) {
    const line = frame.startsWith("data: ") ? frame.slice(6) : frame;
    if (!line.trim()) continue;
    try {
      const evt = JSON.parse(line) as { delta?: string; error?: boolean };
      if (evt.delta) text += evt.delta;
    } catch {
      // heartbeat or malformed frame — skip
    }
  }
  return text.trim();
}
