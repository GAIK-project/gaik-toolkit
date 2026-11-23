// Wizard workflow state machine (#31 / S2-3).
//
// The single source of truth for how a session moves through the 12-phase +
// gate model. It is a PURE reducer: `transition(state, event)` takes the current
// (step, gateStatus) and an event and returns the resulting state plus flags —
// no I/O, no mutation. Both the in-memory mock store and the wizard_api path
// call it to decide, then persist however they persist. The live V1 agent (#29)
// drives the same events instead of a UI button.
//
// Rules (from the S2-3 Gherkin):
//   1. ADVANCE moves one step; a pending gate step blocks it (blockedReason set).
//   2. Gate statuses are DERIVED from the step: passed = approved, current =
//      pending, future = locked. Approving a gate advances past it.
//   3. Step + gate fields are plain data, so they persist across a session GET.

export type GateStatus = "locked" | "pending" | "approved" | "rejected";

/** Total workflow steps (onboarding phases 1–12 + final Gate 4 = 13). */
export const STEP_COUNT = 13;

/** First step where requirement gathering hands off to Gate 1. */
export const GATE_1_STEP = 4;

/** 1-based gate steps: Gate 1 = 4, Gate 2 = 9, Gate 3 = 11, Gate 4 = 13. */
export const GATE_STEPS: readonly number[] = [4, 9, 11, 13];

export function isGateStep(step: number): boolean {
  return GATE_STEPS.includes(step);
}

/** 1-based gate index for a gate step (Gate 1..4), or undefined if not a gate. */
export function gateNumber(step: number): number | undefined {
  const i = GATE_STEPS.indexOf(step);
  return i === -1 ? undefined : i + 1;
}

/**
 * Gate map derived from the current step: every gate before `step` is approved,
 * the gate at `step` is pending, later gates are locked. This is what makes the
 * gate statuses a pure function of the step and therefore trivially persistable.
 */
export function buildGateStatus(step: number): Record<number, GateStatus> {
  const m: Record<number, GateStatus> = {};
  for (const g of GATE_STEPS) {
    m[g] = step > g ? "approved" : step === g ? "pending" : "locked";
  }
  return m;
}

export type WizardEvent =
  | "ADVANCE"
  | "REGRESS"
  | "APPROVE_GATE"
  | "REJECT_GATE"
  | "REQUIREMENTS_COMPLETE";

export type WizardState = {
  step: number;
  gateStatus: Record<number, GateStatus>;
};

export type Transition = {
  /** True when the event produced no change (no-op or gate-blocked). */
  noop: boolean;
  /** The resulting state (identical reference-wise is not guaranteed). */
  state: WizardState;
  /** A step advance happened → the caller should record a new blueprint version. */
  advanced: boolean;
  /** The session reached the final step and is complete. */
  done: boolean;
  /** Set when an ADVANCE was blocked by a pending gate; the agent relays it. */
  blockedReason?: string;
};

function stay(state: WizardState, blockedReason?: string): Transition {
  return { noop: true, state, advanced: false, done: false, blockedReason };
}

function moveTo(step: number, advanced: boolean): Transition {
  return {
    noop: false,
    state: { step, gateStatus: buildGateStatus(step) },
    advanced,
    done: step >= STEP_COUNT && advanced,
  };
}

/**
 * True on the steps a user can step back from: requirements gathering up to
 * and including Gate 1, where the step before shows a different view (the
 * gathering list, the field list, the Gate 1 review). From step 5 on every step
 * shows the same workspace, and a step back would only move the heading and
 * tell the agent an earlier step, so the UI has no "Previous" there and the
 * REGRESS transition refuses it. Changes after Gate 1 go through the chat.
 */
export function canStepBack(step: number): boolean {
  return step > 1 && step <= GATE_1_STEP;
}

/** Human-readable reason an ADVANCE is blocked at a pending gate. */
export function gateBlockReason(step: number): string {
  const n = gateNumber(step);
  return n
    ? `Gate ${n} must be approved before continuing.`
    : "This step must be approved before continuing.";
}

/**
 * Pure transition function. Given the current state and an event, return the
 * next state and side-effect flags. Never mutates its input.
 */
export function transition(state: WizardState, event: WizardEvent): Transition {
  const { step, gateStatus } = state;

  switch (event) {
    case "ADVANCE": {
      if (step >= STEP_COUNT) return stay(state);
      if (isGateStep(step) && gateStatus[step] !== "approved") {
        return stay(state, gateBlockReason(step));
      }
      return moveTo(step + 1, true);
    }

    case "REGRESS": {
      // Only back into requirements gathering (see canStepBack): past Gate 1
      // a step back changed nothing the user sees, and onto a passed gate it
      // reopened a decision already made.
      if (!canStepBack(step)) return stay(state);
      return moveTo(step - 1, false);
    }

    case "APPROVE_GATE": {
      if (!isGateStep(step)) return stay(state);
      // Final gate: mark approved and complete, no further advance.
      if (step >= STEP_COUNT) {
        return {
          noop: false,
          state: { step, gateStatus: { ...gateStatus, [step]: "approved" } },
          advanced: false,
          done: true,
        };
      }
      // Approving a gate advances past it (buildGateStatus marks it approved).
      return moveTo(step + 1, true);
    }

    case "REJECT_GATE": {
      if (!isGateStep(step)) return stay(state);
      // An approved gate stays approved (the last one keeps its step).
      if (gateStatus[step] === "approved") return stay(state);
      return {
        noop: false,
        state: { step, gateStatus: { ...gateStatus, [step]: "rejected" } },
        advanced: false,
        done: false,
      };
    }

    case "REQUIREMENTS_COMPLETE": {
      // Gathering (steps 1–3) is done → jump to Gate 1 for approval.
      if (step >= GATE_1_STEP) return stay(state);
      return moveTo(GATE_1_STEP, false);
    }

    default: {
      // Exhaustiveness: unknown events are a no-op rather than a crash.
      return stay(state);
    }
  }
}
