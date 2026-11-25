/**
 * The conversation the browser sends back, cut to what the helpdesk chat
 * itself writes. The server sets the assistant's instructions
 * (`createHelpdeskAgent`); a message from the browser must not add to them.
 *
 * - Only the user's and the assistant's turns: a `system` message (or any other
 *   role) refuses the request.
 * - A user turn keeps its text. An assistant turn keeps its text, its step and
 *   reasoning marks, and the calls of the chat's own three tools (their results
 *   and the user's approval of a handoff travel in them). Any other part, a
 *   file, an image, a URL source or a data part, is dropped: the page never
 *   sends one, and the model would read it.
 * - A turn left with no part is dropped.
 */

const ROLES = new Set(["user", "assistant"]);
const USER_PARTS = new Set(["text"]);
const ASSISTANT_PARTS = new Set([
  "text",
  "step-start",
  "reasoning",
  "tool-searchServices",
  "tool-searchKnowledge",
  "tool-requestHumanHandoff",
]);

type Part = { type: string } & Record<string, unknown>;
type Message = { role: string; parts: Part[] } & Record<string, unknown>;

function isPart(value: unknown): value is Part {
  return (
    typeof value === "object" &&
    value !== null &&
    typeof (value as { type?: unknown }).type === "string"
  );
}

/** The conversation without what the chat does not write, or null when a turn
 * is not the user's or the assistant's, or is not a message at all. */
export function conversationFromBrowser(messages: unknown[]): Message[] | null {
  const kept: Message[] = [];
  for (const value of messages) {
    if (typeof value !== "object" || value === null) return null;
    const message = value as Partial<Message>;
    if (typeof message.role !== "string" || !ROLES.has(message.role)) return null;
    if (!Array.isArray(message.parts)) return null;
    const allowed = message.role === "user" ? USER_PARTS : ASSISTANT_PARTS;
    const parts = message.parts.filter(
      (part): part is Part => isPart(part) && allowed.has(part.type),
    );
    if (parts.length) kept.push({ ...(message as Message), parts });
  }
  return kept.length ? kept : null;
}
