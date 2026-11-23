import type { ChatReference } from "@/lib/chat-events";
import { fillTemplate, quoteOneLine } from "@/lib/chat-template";
import type { Dict } from "@/lib/i18n";

type StepTexts = Pick<Dict, "stepChatLabel" | "stepChatPrefix" | "stepChatAsk">;

/**
 * The chat reference for "Muuta chatissa" on one process step: the chip says
 * which step, and the message starts with the step's number, id and name. The
 * name and id are written by the agent, so they travel as a one-line quote.
 */
export function stepChatReference(
  step: { id: string; name: string },
  index: number,
  t: StepTexts,
): ChatReference {
  const n = String(index + 1);
  const name = quoteOneLine(step.name || step.id);
  return {
    key: `step:${step.id}`,
    label: fillTemplate(t.stepChatLabel, { n, name: quoteOneLine(step.name || step.id, 60) }),
    prefix: fillTemplate(t.stepChatPrefix, { n, id: quoteOneLine(step.id, 80), name }),
  };
}

/** The accessible name of a step's "Muuta chatissa" button. */
export function stepChatAskLabel(step: { id: string; name: string }, t: StepTexts): string {
  return fillTemplate(t.stepChatAsk, { name: step.name.trim() || step.id });
}
