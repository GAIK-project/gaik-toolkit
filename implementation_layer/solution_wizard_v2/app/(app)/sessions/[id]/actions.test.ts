import { beforeEach, describe, expect, it, vi } from "vitest";
import { buildGateStatus, type GateStatus } from "@/lib/wizard-state-machine";

/** `redirect` ends the action in Next by throwing; here it throws its target. */
class Redirected extends Error {
  constructor(readonly to: string) {
    super(`redirect ${to}`);
  }
}

const next = vi.hoisted(() => ({ revalidatePath: vi.fn(), redirect: vi.fn() }));
vi.mock("next/cache", () => ({ revalidatePath: next.revalidatePath }));
vi.mock("next/navigation", () => ({ redirect: next.redirect }));

const access = vi.hoisted(() => ({ requireOwnedSession: vi.fn() }));
vi.mock("@/lib/session-access", () => access);

const sessions = vi.hoisted(() => ({
  advanceSession: vi.fn(),
  regressSession: vi.fn(),
  approveGate: vi.fn(),
  reopenGate: vi.fn(),
  endAgent: vi.fn(),
}));
vi.mock("@/lib/sessions", () => sessions);

import { approve, releaseWizard } from "./actions";
import { WizardApiError } from "@/lib/wizard-api-client";

type Standing = {
  step: number;
  gateStatus: Record<number, GateStatus>;
  lastSuccessfulRun?: string | null;
  messages: { role: string; content: string }[];
  pendingTurn?: unknown;
};

function at(step: number, over: Partial<Standing> = {}): Standing {
  return { step, gateStatus: buildGateStatus(step), messages: [], ...over };
}

function form(step: number): FormData {
  const data = new FormData();
  data.set("id", "s1");
  data.set("step", String(step));
  return data;
}

/** Run an action to its redirect; null when it ends without one. */
async function redirectOf(run: Promise<unknown>): Promise<string | null> {
  try {
    await run;
    return null;
  } catch (err) {
    if (err instanceof Redirected) return err.to;
    throw err;
  }
}

const busy = () => new WizardApiError(409, "/sessions/s1", JSON.stringify({ detail: { error: "agent_busy" } }));

beforeEach(() => {
  vi.clearAllMocks();
  next.redirect.mockImplementation((to: string) => {
    throw new Redirected(to);
  });
});

describe("approve", () => {
  it("from the PoC step moves the session onto Gate 3 and approves that gate only", async () => {
    access.requireOwnedSession.mockResolvedValue({ session: at(10, { lastSuccessfulRun: "run-1" }) });
    sessions.advanceSession.mockResolvedValue(at(11));
    sessions.approveGate.mockResolvedValue(at(12));

    expect(await redirectOf(approve(form(11)))).toBe("/sessions/s1?wake=3");
    // The move is made from the step the page saw, the approval for the form's gate.
    expect(sessions.advanceSession).toHaveBeenCalledWith("s1", 10);
    expect(sessions.approveGate).toHaveBeenCalledWith("s1", 11);
  });

  it("from a step of Gate 2's stage walks the session onto the gate and approves that gate only", async () => {
    access.requireOwnedSession.mockResolvedValue({ session: at(6) });
    sessions.advanceSession.mockImplementation(async (_id: string, from: number) => at(from + 1));
    sessions.approveGate.mockResolvedValue(at(10));

    expect(await redirectOf(approve(form(9)))).toBe("/sessions/s1?wake=2");
    // One step at a time, each from the step the one before left the session on.
    expect(sessions.advanceSession.mock.calls).toEqual([
      ["s1", 6],
      ["s1", 7],
      ["s1", 8],
    ]);
    expect(sessions.approveGate).toHaveBeenCalledWith("s1", 9);
  });

  it("a second approval of Gate 3 that arrives after the first approves nothing more", async () => {
    // Both requests read the session on the PoC step. The first has approved
    // Gate 3 by the time this one moves: the session stands on step 12, and
    // must not be moved on to Gate 4 and approved there.
    access.requireOwnedSession.mockResolvedValue({ session: at(10, { lastSuccessfulRun: "run-1" }) });
    sessions.advanceSession.mockResolvedValue(at(12));

    expect(await redirectOf(approve(form(11)))).toBe("/sessions/s1?notice=gate_moved");
    expect(sessions.advanceSession).toHaveBeenCalledWith("s1", 10);
    expect(sessions.approveGate).not.toHaveBeenCalled();
  });

  it("while the wizard is replying says that it is busy, not that the gate has moved", async () => {
    // The page offered Gate 4 from the documentation step, then a message was
    // sent: the session has not moved, the wizard is answering.
    access.requireOwnedSession.mockResolvedValue({
      session: at(12, { pendingTurn: { userMessage: "Lisää ohje." }, messages: [{ role: "user", content: "Lisää ohje." }] }),
    });
    sessions.advanceSession.mockRejectedValue(busy());

    expect(await redirectOf(approve(form(13)))).toBe("/sessions/s1?notice=agent_busy");
    expect(sessions.approveGate).not.toHaveBeenCalled();
  });

  it("a walk refused part of the way says the wizard is busy over the step the session reached", async () => {
    // Gate 2 offered from step 6: the first move went through, then the wizard
    // started a reply. The session stands on step 7 now.
    access.requireOwnedSession.mockResolvedValue({ session: at(6) });
    sessions.advanceSession.mockResolvedValueOnce(at(7)).mockRejectedValueOnce(busy());

    expect(await redirectOf(approve(form(9)))).toBe("/sessions/s1?notice=agent_busy");
    expect(next.revalidatePath).toHaveBeenCalledWith("/", "layout");
    expect(sessions.approveGate).not.toHaveBeenCalled();
  });

  it("a walk that fails part of the way reads the page again before it fails", async () => {
    // The failure is not one the page explains. Without a new reading it was
    // shown over step 6 while the session stood on step 7.
    access.requireOwnedSession.mockResolvedValue({ session: at(6) });
    sessions.advanceSession.mockResolvedValueOnce(at(7)).mockRejectedValueOnce(new Error("wizard_api 500"));

    await expect(approve(form(9))).rejects.toThrow("wizard_api 500");
    expect(next.revalidatePath).toHaveBeenCalledWith("/", "layout");
    expect(sessions.approveGate).not.toHaveBeenCalled();
  });

  it("an approval that fails after the move onto the gate reads the page again too", async () => {
    access.requireOwnedSession.mockResolvedValue({ session: at(10, { lastSuccessfulRun: "run-1" }) });
    sessions.advanceSession.mockResolvedValue(at(11));
    sessions.approveGate.mockRejectedValue(new Error("wizard_api 500"));

    await expect(approve(form(11))).rejects.toThrow("wizard_api 500");
    expect(next.revalidatePath).toHaveBeenCalledWith("/", "layout");
  });

  it("a failure before anything moved changes nothing, and nothing is read again", async () => {
    access.requireOwnedSession.mockResolvedValue({ session: at(6) });
    sessions.advanceSession.mockRejectedValue(new Error("wizard_api 500"));

    await expect(approve(form(9))).rejects.toThrow("wizard_api 500");
    expect(next.revalidatePath).not.toHaveBeenCalled();
  });

  it("refused because the package changed after the run, says to run the test again", async () => {
    // wizard_api: 409 gate_not_ready with reason package_changed. The generic
    // notice sent the user to the chat; the way on is another test run.
    access.requireOwnedSession.mockResolvedValue({ session: at(11, { lastSuccessfulRun: "run-1" }) });
    sessions.approveGate.mockRejectedValue(
      new WizardApiError(
        409,
        "/sessions/s1",
        JSON.stringify({ detail: { error: "gate_not_ready", gate: "gate_3", reason: "package_changed" } }),
      ),
    );

    expect(await redirectOf(approve(form(11)))).toBe("/sessions/s1?notice=package_changed");
    expect(next.revalidatePath).toHaveBeenCalledWith("/", "layout");
  });

  it("refused because the gate has nothing behind it yet keeps the notice it had", async () => {
    access.requireOwnedSession.mockResolvedValue({ session: at(11) });
    sessions.approveGate.mockRejectedValue(
      new WizardApiError(409, "/sessions/s1", JSON.stringify({ detail: { error: "gate_not_ready", gate: "gate_3" } })),
    );

    expect(await redirectOf(approve(form(11)))).toBe("/sessions/s1?notice=gate_not_ready");
  });

  it("a form for a gate the session has left is told so, and nothing is moved", async () => {
    access.requireOwnedSession.mockResolvedValue({ session: at(12) });

    expect(await redirectOf(approve(form(11)))).toBe("/sessions/s1?notice=gate_moved");
    expect(sessions.advanceSession).not.toHaveBeenCalled();
    expect(sessions.approveGate).not.toHaveBeenCalled();
  });

  it("on the gate itself approves without a move", async () => {
    access.requireOwnedSession.mockResolvedValue({ session: at(9) });
    sessions.approveGate.mockResolvedValue(at(10));

    expect(await redirectOf(approve(form(9)))).toBe("/sessions/s1?wake=2");
    expect(sessions.advanceSession).not.toHaveBeenCalled();
    expect(sessions.approveGate).toHaveBeenCalledWith("s1", 9);
  });
});

describe("releaseWizard", () => {
  const done = () => ({ id: "s1", ...at(13, { gateStatus: { ...buildGateStatus(13), 13: "approved" } }) });

  it("releases the wizard of a finished session, and reads nothing again", async () => {
    access.requireOwnedSession.mockResolvedValue({ session: done() });
    sessions.endAgent.mockResolvedValue("ended");

    expect(await releaseWizard("s1")).toBe("ended");
    expect(sessions.endAgent).toHaveBeenCalledWith("s1");
    // The page shows the same session either way: no refresh, no redirect.
    expect(next.revalidatePath).not.toHaveBeenCalled();
    expect(next.redirect).not.toHaveBeenCalled();
  });

  it("says so when the wizard is still replying or the release fails, and nothing else happens", async () => {
    access.requireOwnedSession.mockResolvedValue({ session: done() });
    sessions.endAgent.mockResolvedValue("busy");
    expect(await releaseWizard("s1")).toBe("busy");
    sessions.endAgent.mockResolvedValue("failed");
    expect(await releaseWizard("s1")).toBe("failed");
    expect(next.revalidatePath).not.toHaveBeenCalled();
    expect(next.redirect).not.toHaveBeenCalled();
  });

  it("leaves the wizard of a session that is not finished, or is not the user's", async () => {
    // The last gate still waits.
    access.requireOwnedSession.mockResolvedValue({ session: { id: "s1", ...at(13) } });
    expect(await releaseWizard("s1")).toBe("failed");
    access.requireOwnedSession.mockResolvedValue({ session: { id: "s1", ...at(12) } });
    expect(await releaseWizard("s1")).toBe("failed");
    access.requireOwnedSession.mockResolvedValue(null);
    expect(await releaseWizard("s1")).toBe("failed");
    expect(sessions.endAgent).not.toHaveBeenCalled();
  });
});
