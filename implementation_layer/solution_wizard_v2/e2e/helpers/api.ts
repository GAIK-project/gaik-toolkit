import type { APIRequestContext } from "@playwright/test";
import { ownerId } from "../../lib/owner-id";

export function getWizardApiUrl(): string {
  const url = process.env.WIZARD_API_URL?.trim();
  if (!url) {
    throw new Error("WIZARD_API_URL is required for stack E2E");
  }
  return url.replace(/\/$/, "");
}

export async function waitForApiHealthy(
  request: APIRequestContext,
  timeoutMs = 60_000,
): Promise<void> {
  const base = getWizardApiUrl();
  const deadline = Date.now() + timeoutMs;
  let lastError = "unknown";

  while (Date.now() < deadline) {
    try {
      const res = await request.get(`${base}/health`);
      if (res.ok()) return;
      lastError = `${res.status()} ${await res.text()}`;
    } catch (err) {
      lastError = err instanceof Error ? err.message : String(err);
    }
    await new Promise((r) => setTimeout(r, 1000));
  }

  throw new Error(`wizard_api did not become healthy: ${lastError}`);
}

/** Simulates API process restart (Docker restart policy + test hook). */
export async function restartWizardApi(request: APIRequestContext): Promise<void> {
  const base = getWizardApiUrl();
  try {
    await request.post(`${base}/test/shutdown`, { timeout: 5_000 });
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    const expected =
      message.includes("socket hang up") ||
      message.includes("ECONNRESET") ||
      message.includes("ECONNREFUSED") ||
      message.includes("Timeout");
    if (!expected) throw err;
  }
  await waitForApiHealthy(request);
}

/**
 * Move a session to a given step through the API.
 *
 * During gathering (steps 1–3) the UI has no control that advances the step:
 * the wizard advances on its own once the agent has collected the
 * requirements. A stack test that needs a session at a later step therefore
 * has to say so through the API instead of clicking.
 */
export async function setApiSessionStep(
  request: APIRequestContext,
  sessionId: string,
  step: number,
): Promise<void> {
  const base = getWizardApiUrl();
  // The server refuses a step change that passes a gate nobody approved (#187),
  // so a test asking for a later step has to say the user reached it the normal
  // way. Approving here is setup, not the thing under test — the rule itself is
  // covered by test_gate_enforcement.py and gate-enforcement-stack.spec.ts.
  const res = await request.patch(`${base}/sessions/${sessionId}`, {
    data: { step, gate_statuses: gatesPassedBefore(step) },
  });
  if (!res.ok()) {
    throw new Error(`set step failed: ${res.status()} ${await res.text()}`);
  }
  // A session standing at the PoC step has a design behind it. The api refuses
  // to scaffold from the placeholder blueprint (#181), so a test that jumps
  // there gives the session one the way the wizard would have.
  if (step >= 10) {
    await seedApiDesign(request, sessionId);
  }
}

/**
 * A small real design (three steps, one GAIK component) stored as a new
 * blueprint version, in place of the seed the session was created with.
 */
export async function seedApiDesign(
  request: APIRequestContext,
  sessionId: string,
): Promise<void> {
  const base = getWizardApiUrl();
  const res = await request.post(`${base}/sessions/${sessionId}/versions`, {
    data: {
      note: "e2e design",
      content: {
        name: "Incident report extraction",
        description: "Turn maintenance notes into structured incident reports.",
        goal: "Show that a report can be produced from one note.",
        steps: [
          { id: "collect", name: "Collect note", type: "io" },
          {
            id: "extract",
            name: "Extract fields",
            type: "ai",
            component: "StructuredDataExtractor",
          },
          { id: "review", name: "Technician review", type: "human_review" },
        ],
        integration_targets: [],
      },
    },
  });
  if (!res.ok()) {
    throw new Error(`seed design failed: ${res.status()} ${await res.text()}`);
  }
}

/** UI gate step -> wizard_api gate key, mirroring lib/session-gate-map.ts. */
const GATE_STEP_TO_KEY: Record<number, string> = {
  4: "gate_1",
  9: "gate_2",
  11: "gate_3",
  13: "gate_4",
};

/** Every gate a session must have passed to legitimately stand at `step`. */
export function gatesPassedBefore(step: number): Record<string, string> {
  const approved: Record<string, string> = {};
  for (const [gateStep, key] of Object.entries(GATE_STEP_TO_KEY)) {
    if (Number(gateStep) < step) approved[key] = "approved";
  }
  return approved;
}

/** Approve the gate the session is standing on. */
export async function approveApiGate(
  request: APIRequestContext,
  sessionId: string,
  gateKey: string,
): Promise<void> {
  const base = getWizardApiUrl();
  const res = await request.patch(`${base}/sessions/${sessionId}`, {
    data: { gate_statuses: { [gateKey]: "approved" } },
  });
  if (!res.ok()) {
    throw new Error(`approve ${gateKey} failed: ${res.status()} ${await res.text()}`);
  }
}

export type ApiSessionSummary = {
  id: string;
  step: number;
  title: string | null;
};

function summaryTitle(metadata: Record<string, unknown> | undefined): string | null {
  const title = metadata?.title;
  return typeof title === "string" && title.trim() ? title.trim() : null;
}

/**
 * The sessions wizard_api holds for the signed-in user `email`, under the owner
 * id the web app sends (`lib/owner-id.ts`); the runner has the web app's key.
 */
export async function listApiSessions(
  request: APIRequestContext,
  email: string,
): Promise<ApiSessionSummary[]> {
  const base = getWizardApiUrl();
  const res = await request.get(`${base}/sessions`, { params: { user_id: ownerId(email) } });
  if (!res.ok()) {
    throw new Error(`list sessions failed: ${res.status()} ${await res.text()}`);
  }
  const body = (await res.json()) as {
    sessions: { id: string; step: number; metadata?: Record<string, unknown> }[];
  };
  return body.sessions.map((s) => ({
    id: s.id,
    step: s.step,
    title: summaryTitle(s.metadata),
  }));
}
