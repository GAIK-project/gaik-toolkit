"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { STEP_COUNT, gateNumber, type GateStatus } from "@/lib/wizard-state-machine";
import { gateDecidableFrom } from "@/lib/gate-decision";
import { WizardApiError } from "@/lib/wizard-api-client";
import { requireOwnedSession } from "@/lib/session-access";
import { afterStepAction, GATE_MOVED_NOTICE, PACKAGE_CHANGED_NOTICE } from "@/lib/step-redirect";
import {
  advanceSession,
  approveGate,
  endAgent,
  reopenGate,
  type ReopenResult,
} from "@/lib/sessions";

// The session's own page and the sidebar, which shows each session's gates on
// every page: both are read again with the action's answer.
function refresh() {
  revalidatePath("/", "layout");
}

/** Refusals the page explains instead of failing: the agent is still working,
 * or the gate has nothing behind it yet (customer test feedback, Oct 2026). */
const NOTICE_CODES = new Set(["agent_busy", "gate_not_ready"]);

/**
 * Whether the gate the form was shown for is still the one waiting for a
 * decision. A page left open while the session moved on (another tab approved
 * the gate, or the work ended) must not decide whichever gate the session
 * stands on now, or a gate that is already approved. The gate's decision is
 * offered through the gate's whole stage (lib/gate-decision).
 * Whether the wizard is replying is not asked here: wizard_api refuses a move
 * or an approval meanwhile, and the page then says that, not "moved on".
 */
function gateStillOpen(session: { step: number; gateStatus: Record<number, GateStatus> }, step: number): boolean {
  return gateDecidableFrom(session, step);
}

/**
 * Put the session on the gate a decision is for, when the decision was offered
 * from a step before it, and say whether it stands there, undecided. The walk
 * is one step at a time and can stop part of the way (the wizard started a
 * reply, wizard_api failed): `onMoved` says the session is no longer where the
 * page shows it, whatever comes after. This is
 * the only place the web app moves a session between gates: the steps there
 * carry no decision, so the page has no button for them (wizard_api moves the
 * session as the wizard writes its files), and the session has to stand on
 * the gate's step only when the gate is decided (approveGate).
 * Each move is made only from the step the session was read on, and the
 * approval that follows is made only for this gate: two approvals of Gate 3 sent together both read the
 * session on the PoC step, and the second one, arriving after the first had
 * approved, moved the session on to Gate 4 and approved that.
 */
async function standsOnGate(
  id: string,
  session: { step: number; gateStatus: Record<number, GateStatus> },
  step: number,
  /** Called as soon as one move has gone through, also when a later one fails. */
  onMoved: () => void,
): Promise<boolean> {
  if (session.step === step) return true;
  let after;
  for (let at = session.step; at < step; at++) {
    after = await advanceSession(id, at);
    // Another request moved the session meanwhile: nothing more is decided here.
    if (after?.step !== at + 1) break;
    onMoved();
  }
  return after?.step === step && after.gateStatus[step] !== "approved";
}

function noticeFor(err: unknown): string | null {
  if (!(err instanceof WizardApiError) || err.status !== 409 || !err.code || !NOTICE_CODES.has(err.code)) {
    return null;
  }
  // Gate 3 with a successful run behind it, of a package that has changed
  // since: "continue in the chat" (gate_not_ready) is not the way on, a new
  // test run is, so the refusal has a notice of its own.
  if (err.code === "gate_not_ready" && err.reason === "package_changed") return PACKAGE_CHANGED_NOTICE;
  return err.code;
}

export async function approve(formData: FormData) {
  const id = formData.get("id") as string;
  const owned = await requireOwnedSession(id);
  if (!owned) return;
  if (!gateStillOpen(owned.session, Number(formData.get("step")))) {
    // Nothing is approved and no wake-up turn is sent; the page says so.
    refresh();
    redirect(afterStepAction(id, { notice: GATE_MOVED_NOTICE })!);
  }
  // The gate the form was shown for; gateStillOpen has checked it is the one waiting.
  const step = Number(formData.get("step"));
  const gate = gateNumber(step);
  let notice: string | null = null;
  let approved = false;
  let onGate = true;
  // The session left the step the page shows, though the approval may not follow.
  let moved = false;
  try {
    // Decided from the step before the gate: the session moves onto it first.
    onGate = await standsOnGate(id, owned.session, step, () => {
      moved = true;
    });
    if (onGate) {
      const after = await approveGate(id, step);
      approved = after?.gateStatus[step] === "approved";
    }
  } catch (err) {
    notice = noticeFor(err);
    if (!notice) {
      // A move went through and a later one, or the approval, failed: the
      // failure is shown over a page that has read where the session stands,
      // not over the step it has left.
      if (moved) refresh();
      throw err;
    }
  }
  refresh();
  // Another request decided this gate meanwhile: nothing was approved here.
  if (!onGate) redirect(afterStepAction(id, { notice: GATE_MOVED_NOTICE })!);
  // The panel is the only gate approval (#173), so the agent has to hear about
  // it: the page sends one chat turn for the approved gate (`wake`), which the
  // chat panel posts on load and then strips from the URL. Only when this
  // action approved it: approveGate returns without approving when the step is
  // no longer a gate.
  const to = afterStepAction(id, {
    notice,
    wake: notice || !approved ? undefined : gate,
    hadNotice: formData.get("notice") === "1",
  });
  if (to) redirect(to);
}

// The solution is done (the last gate is approved): the wizard held for the
// session is released without the user asking, once its last reply has ended
// (components/release-wizard). A live wizard is a process on the server and
// they are few; the session, its files and the conversation stay, and the
// next message starts the wizard again. Refused ("busy") while it is replying.
// Nothing is read again: the page shows the same session either way.
export async function releaseWizard(id: string): Promise<"ended" | "busy" | "failed"> {
  const owned = await requireOwnedSession(typeof id === "string" ? id : "");
  if (!owned) return "failed";
  const { step, gateStatus } = owned.session;
  // Only a finished session: before that the wizard is still at work.
  if (step < STEP_COUNT || gateStatus[step] !== "approved") return "failed";
  return endAgent(owned.session.id);
}

// "Change" on an approved gate in the timeline: its approval and the later
// ones are taken back, and the page shows the session on that gate again. The
// timeline then opens the chat with the gate as the reference, where the user
// says what to change.
export async function reopen(id: string, gate: number): Promise<ReopenResult> {
  if (!Number.isInteger(gate) || gate < 1 || gate > 4) return "failed";
  if (!(await requireOwnedSession(id))) return "failed";
  const outcome = await reopenGate(id, gate);
  // Also when nothing was reopened: the page then shows where the session stands.
  refresh();
  return outcome;
}
