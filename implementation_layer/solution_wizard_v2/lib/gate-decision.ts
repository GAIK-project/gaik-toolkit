import { approvedGateIn } from "@/lib/chat-reference";
import { GATE_STEPS, isGateStep, type GateStatus } from "@/lib/wizard-state-machine";

export type DecisionSession = {
  step: number;
  gateStatus: Record<number, GateStatus>;
  lastSuccessfulRun?: string | null;
  messages: { role: string; content: string }[];
  pendingTurn?: unknown;
  /** What Gate 1 reviews, as the wizard has recorded it so far. */
  businessContext?: unknown;
  assumptions?: readonly unknown[];
  /**
   * How far the files the wizard has written reach, as wizard_api reads them
   * (the workflow diagram is the Gate 2 step, the PoC package the step after).
   * Absent in the mock store, which has no wizard writing files.
   */
  reachedStep?: number | null;
};

/**
 * Whether the wizard has recorded what Gate 1 reviews (the business context
 * or an assumption): the draft specification is there. Whether it is complete
 * enough to approve is the decision bar's to say (gate1Missing).
 */
export function specificationGathered(
  session: Pick<DecisionSession, "businessContext" | "assumptions">,
): boolean {
  return Boolean(session.businessContext) || (session.assumptions?.length ?? 0) > 0;
}

/**
 * The gate of the stage the session is in: the first gate at or after its step
 * that is not approved. A session standing on an approved gate (the move after
 * the approval was refused, or the step was set back onto it) is in the next
 * gate's stage. Undefined once the last gate is approved.
 */
export function stageGateStep(session: Pick<DecisionSession, "step" | "gateStatus">): number | undefined {
  return GATE_STEPS.find((gate) => gate >= session.step && session.gateStatus[gate] !== "approved");
}

/**
 * The step of the gate whose decision the page offers now, or undefined.
 *
 * On a gate step that is the gate itself, until it is approved. The steps
 * between gates carry no decision of the user's: the wizard works through
 * them in the chat and wizard_api moves the session as the wizard writes its
 * files. They had a "Next step" button all the same, and users asked what it
 * was for. So a gate's decision is offered through its whole stage, from the
 * moment what it reviews is there:
 *
 * - Gate 1 once the wizard has recorded the specification it reviews;
 * - Gate 2 once the wizard's files reach the workflow diagram (`reachedStep`)
 *   and the wizard has replied since Gate 1 was approved. wizard_api moves the
 *   session onto the gate itself when the diagram is new; a session whose
 *   diagram was written before Gate 1 was approved stayed behind;
 * - Gate 3 once a test run has succeeded: a run is not a file the step follows;
 * - Gate 4 once the wizard has replied since Gate 3 was approved (that reply
 *   is where it finishes the documentation).
 *
 * Gate 2 and Gate 4 are not offered while the wizard is replying: the approve
 * button would stand where the gate before was approved a moment ago.
 *
 * Deciding from a step before the gate moves the session onto the gate first
 * (actions.ts); wizard_api's own gate rules decide as before whether the
 * approval holds.
 */
export function decisionGateStep(session: DecisionSession): number | undefined {
  const gateStep = stageGateStep(session);
  if (gateStep === undefined || gateStep === session.step) return gateStep;
  return aheadReady(session, gateStep) ? gateStep : undefined;
}

/** Whether what the gate ahead reviews is there, so its decision can be offered already. */
function aheadReady(session: DecisionSession, gateStep: number): boolean {
  switch (gateStep) {
    case GATE_STEPS[0]:
      return specificationGathered(session);
    case GATE_STEPS[1]:
      return (
        (session.reachedStep ?? 0) >= gateStep && !session.pendingTurn && repliedSinceApproval(session.messages, 1)
      );
    case GATE_STEPS[2]:
      return Boolean(session.lastSuccessfulRun);
    case GATE_STEPS[3]:
      return !session.pendingTurn && repliedSinceApproval(session.messages, 3);
    default:
      return false;
  }
}

/**
 * The step the workspace is drawn for: the session's own, or as far on as the
 * wizard's files reach within the stage. The Workflow tab is there once the
 * diagram is, also for a session whose step has not followed it.
 */
export function workspaceStep(session: Pick<DecisionSession, "step" | "gateStatus" | "reachedStep">): number {
  const reached = session.reachedStep ?? 0;
  return Math.max(session.step, Math.min(reached, stageGateStep(session) ?? reached));
}

/** The wizard's reply is the newest message, and it came after `gate` was last approved. */
function repliedSinceApproval(messages: DecisionSession["messages"], gate: number): boolean {
  const last = messages[messages.length - 1];
  if (!last || last.role !== "assistant" || !last.content.trim()) return false;
  for (let i = messages.length - 2; i >= 0; i--) {
    const m = messages[i];
    if (m.role === "user" && approvedGateIn(m.content) === gate) return true;
  }
  return false;
}

/**
 * Whether a decision of the gate at `gateStep` can be taken from where the
 * session stands: on the gate or anywhere in its stage, while the gate is not
 * approved. This is what the server asks before it decides.
 * It is wider than `decisionGateStep`, which says when the page offers the
 * decision: a page that offered it and a wizard that started replying since
 * are not "the session has moved on". wizard_api answers that case itself
 * (the wizard is busy, or the gate has nothing behind it yet), and the page
 * then says the real reason.
 */
export function gateDecidableFrom(
  session: Pick<DecisionSession, "step" | "gateStatus">,
  gateStep: number,
): boolean {
  return isGateStep(gateStep) && stageGateStep(session) === gateStep;
}
