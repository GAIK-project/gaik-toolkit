import type { Dict } from "@/lib/i18n";
import type { ChatReference } from "@/lib/chat-events";
import { fillTemplate, quoteOneLine } from "@/lib/chat-template";
import { GATE_STEPS, STEP_COUNT, gateNumber, type GateStatus } from "@/lib/wizard-state-machine";

/** Longest answer one missing-item field takes; the chat allows far more. */
export const MISSING_ANSWER_MAX = 2000;

/**
 * The one line under the phase title: what the user does now, and where. It
 * names what to look at, not the approval: the approve button says that. At
 * Gate 3, and on the PoC step before it, it follows the test run, which is the
 * real task until one has succeeded. After that the decision is all that is
 * left, and on a wide screen the bar that holds it sits far from the result,
 * at the bottom right: the line names its two buttons by their labels. Unless
 * the package changed after that run: the approval then waits for a run of the
 * package that is there, and the line asks for that run instead. Once
 * Gate 4 is approved there is only the package left to take.
 * On an earlier gate that is already approved (the step came back onto it)
 * there is nothing to check again, only the way on.
 */
export function nowLine(
  t: Dict,
  step: number,
  gateStatus: Record<number, GateStatus>,
  hasSuccessfulRun: boolean,
  /** The package changed after the run that succeeded (Gate 3 waits for a new run). */
  packageChanged = false,
): string {
  // The lines name the workspace tabs by their labels, so a renamed tab stays right.
  const tabs = (line: string) =>
    fillTemplate(line, {
      flow: t.wsTabFlow,
      json: t.wsTabJson,
      poc: t.wsTabPoc,
      approve: t.gateDecisions[2] ?? "",
      request: t.gateRequestChanges,
    });
  const gate = gateNumber(step);
  // From the PoC step a run that succeeded is waiting for the same decision.
  const runWaits = hasSuccessfulRun && (gate === 3 || step === GATE_STEPS[2] - 1);
  if (gate && gateStatus[step] === "approved") {
    if (step < STEP_COUNT) return fillTemplate(t.nowGateApproved, { n: String(gate) });
    // The package can be taken only after a run has succeeded.
    return hasSuccessfulRun ? t.nowDone : tabs(t.nowDoneNoRun);
  }
  if (runWaits && packageChanged) return tabs(t.nowGate3Changed);
  return tabs(runWaits ? t.nowGate3Run : (t.nowSteps[step - 1] ?? ""));
}

/** A topic inside a sentence: "Ratkaisun rakenne" → "ratkaisun rakenne". */
function inSentence(topic: string): string {
  return topic.charAt(0).toLocaleLowerCase() + topic.slice(1);
}

export type GateReferenceLabels = {
  /** Each gate's business topic, Gate 1–4. */
  topics: string[];
  /** "Gate {n} · {topic}" */
  chip: string;
  /** The line the message starts with: {n} and {topic}. */
  prefix: string;
};

/**
 * A chat reference to one gate (a change request before approving, or a change
 * to an approved stage). The key is the gate's step, so asking about the same
 * gate again replaces its chip instead of adding a second one.
 */
export function gateReference(
  labels: GateReferenceLabels,
  gate: number,
  gateStep: number,
): ChatReference {
  const topic = labels.topics[gate - 1] ?? "";
  return {
    key: `gate:${gateStep}`,
    label: fillTemplate(labels.chip, { n: String(gate), topic }),
    prefix: fillTemplate(labels.prefix, { n: String(gate), topic: inSentence(topic) }),
  };
}

export type MissingAnswerLabels = {
  /** The message's first line. */
  messageIntro: string;
  /** One answered item: {item} and {answer}. */
  messageAnswer: string;
  /** One item the user does not know: {item}. */
  messageNotKnown: string;
};

/**
 * The chat turn that answers what Gate 1 still lacks: a first line, then one
 * line per item. An answer is the user's own words, kept to one line. An item
 * marked not known asks the wizard to write its own estimate and record it as
 * an open assumption: a value left empty, or a placeholder such as "unknown",
 * keeps the approval closed (gate1Missing), so "not known" alone would too.
 */
export function missingAnswersMessage(
  labels: MissingAnswerLabels,
  entries: { item: string; answer: string; notKnown: boolean }[],
): string {
  const lines = entries.map(({ item, answer, notKnown }) =>
    notKnown
      ? fillTemplate(labels.messageNotKnown, { item })
      : fillTemplate(labels.messageAnswer, { item, answer: quoteOneLine(answer, MISSING_ANSWER_MAX) }),
  );
  return [labels.messageIntro, ...lines].join("\n");
}
