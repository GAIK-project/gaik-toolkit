import type { GateStatus } from "@/lib/mock-sessions";
import { GATE_STEPS } from "@/lib/mock-sessions";

/** UI gate step → wizard_api gate_statuses key. */
export const GATE_STEP_TO_API: Record<number, string> = {
  4: "gate_1",
  9: "gate_2",
  11: "gate_3",
  13: "gate_4",
};

export function apiGateKeyForStep(gateStep: number): string | undefined {
  return GATE_STEP_TO_API[gateStep];
}

/** Map API gate_statuses to UI step-keyed gate map (includes locked). */
export function apiGatesToUi(
  step: number,
  gateStatuses: Record<string, string>,
): Record<number, GateStatus> {
  const result: Record<number, GateStatus> = {};
  for (const gateStep of GATE_STEPS) {
    const key = GATE_STEP_TO_API[gateStep];
    const raw = gateStatuses[key];
    const decided =
      raw === "approved" || raw === "rejected" ? (raw as GateStatus) : undefined;
    if (step > gateStep) {
      result[gateStep] = "approved";
    } else if (step < gateStep) {
      // A gate above the current step is normally out of reach — but not after
      // the user has gone back to revise something. Flattening it to "locked"
      // then showed an approval the user had already given as if it had been
      // taken away. The stored decision is what counts; "locked" is only for a
      // gate nobody has ruled on yet.
      result[gateStep] = decided ?? "locked";
    } else {
      result[gateStep] = decided ?? "pending";
    }
  }
  return result;
}

/** Patch body for approving the gate at the current step. */
export function uiGateApprovalPatch(
  gateStep: number,
): Record<string, string> | undefined {
  const key = GATE_STEP_TO_API[gateStep];
  return key ? { [key]: "approved" } : undefined;
}
