import type { ChatReference } from "./chat-events";

/**
 * A CHAT_REFERENCE_EVENT detail as a reference, or null when it is not one.
 * The event is a window event any script on the page could send, so the chat
 * takes only the fields it knows, as strings.
 */
export function asChatReference(detail: unknown): ChatReference | null {
  if (!detail || typeof detail !== "object") return null;
  const { key, label, prefix, draft } = detail as Record<string, unknown>;
  if (typeof key !== "string" || typeof label !== "string" || typeof prefix !== "string") return null;
  const line = oneLine(prefix);
  if (!key.trim() || !label.trim() || !line) return null;
  return {
    key,
    label: label.trim(),
    prefix: line,
    ...(typeof draft === "string" && draft ? { draft } : {}),
  };
}

function oneLine(text: string): string {
  return text.replace(/\s*[\r\n]+\s*/g, " ").trim();
}

/**
 * The message a reference sends: its line, a blank line, then what the user
 * wrote. Empty when the user wrote nothing, so an empty send with a chip does
 * nothing.
 */
export function referenceMessage(prefix: string, text: string): string {
  const own = text.trim();
  if (!own) return "";
  const line = oneLine(prefix);
  return line ? `${line}\n\n${own}` : own;
}

/**
 * The wake-up turn a gate approval in the panel sends (`gateApprovedWake` in
 * lib/i18n.ts), in every language: a stored conversation keeps the language it
 * was approved in. lib/chat-reference.test.ts checks these against the
 * dictionaries.
 */
export const GATE_APPROVED_WAKE_TEMPLATES = [
  "Gate {n} hyväksytty paneelista, jatka.",
  "Gate {n} approved in the panel, continue.",
] as const;

const escapeRegExp = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

const WAKE_PATTERNS = GATE_APPROVED_WAKE_TEMPLATES.map(
  (template) => new RegExp(`^${escapeRegExp(template).replace("\\{n\\}", "([1-4])")}$`),
);

/**
 * The gate a user message approved, when it is the wake-up turn the page sent
 * after "Hyväksy gate"; otherwise null. The chat shows it as an event line
 * instead of a bubble. A stored message is only its role and text, so in a
 * conversation loaded from the server this goes by the text; the chat panel
 * leaves out the messages it saw the user send.
 */
export function approvedGateIn(text: string): number | null {
  const trimmed = text.trim();
  for (const pattern of WAKE_PATTERNS) {
    const m = pattern.exec(trimmed);
    if (m) return Number(m[1]);
  }
  return null;
}
