import type { GateStatus } from "@/lib/sessions";

export type StageState = "approved" | "current" | "pending";

/**
 * The timeline state of one stage: the phases up to and including its gate.
 *
 * A stage is approved once the session has moved past its gate. The last gate
 * sits on the last phase, so the step never moves past it: when it is approved
 * the session stays on that phase. Without the stored gate status the timeline
 * kept showing the final gate as in progress and ahead after its approval
 * (R21 on s4, 3 Nov 2026). The status counts only while the session is on the
 * gate's phase, so a step back before an approved gate still shows it as open.
 */
export function stageState(
  step: number,
  bounds: { first: number; last: number },
  gateStep: number | null,
  gateStatus: Record<number, GateStatus>,
): StageState {
  const { first, last } = bounds;
  if (step > last) return "approved";
  if (
    gateStep !== null &&
    step === gateStep &&
    gateStatus[gateStep] === "approved"
  ) {
    return "approved";
  }
  if (step >= first && step <= last) return "current";
  return "pending";
}
