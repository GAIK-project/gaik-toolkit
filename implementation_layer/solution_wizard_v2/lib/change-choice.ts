import { fillTemplate } from "@/lib/chat-template";

// A Gate 1 item whose value is one of a known few (the knowledge processes,
// whether an assumption holds) is corrected by choosing, not by writing. The
// choice still goes to the wizard as words in a chat turn, under the line
// that names the item, as a written correction does.

export type ChangeChoiceOption = {
  value: string;
  label: string;
  /** One plain line on what the option means. */
  description?: string;
  /** What the message says for the option; its label when left out. */
  sent?: string;
};

export type ChangeChoices = {
  /** The question the options answer. */
  legend: string;
  /** Several options can hold together (checkboxes); otherwise one (radio buttons). */
  multiple?: boolean;
  options: ChangeChoiceOption[];
  /** The options that hold now. */
  selected?: string[];
  /** The message's line for what was chosen: {choice}. */
  message: string;
  /** The label of the free-text field under the options. */
  other: string;
};

/** The chosen values in the options' own order, without ones that are not options. */
export function pickedInOrder(choices: ChangeChoices, picked: string[]): string[] {
  return choices.options.map((option) => option.value).filter((value) => picked.includes(value));
}

/** Whether the choice differs from what holds now. */
export function choiceChanged(choices: ChangeChoices, picked: string[]): boolean {
  const now = pickedInOrder(choices, choices.selected ?? []);
  const next = pickedInOrder(choices, picked);
  return now.length !== next.length || now.some((value, i) => value !== next[i]);
}

/**
 * What a correction says under the item's line: the choice when it changed
 * something, then what the user wrote. Empty when neither says anything, so
 * there is nothing to send.
 */
export function choiceCorrection(choices: ChangeChoices, picked: string[], text: string): string {
  const next = pickedInOrder(choices, picked);
  const lines: string[] = [];
  if (next.length > 0 && choiceChanged(choices, picked)) {
    const words = next.map((value) => {
      const option = choices.options.find((o) => o.value === value);
      return option?.sent ?? option?.label ?? value;
    });
    lines.push(fillTemplate(choices.message, { choice: words.join(", ") }));
  }
  const own = text.trim();
  if (own) lines.push(own);
  return lines.join("\n");
}
