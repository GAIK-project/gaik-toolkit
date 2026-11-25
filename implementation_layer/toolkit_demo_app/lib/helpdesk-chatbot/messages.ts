/**
 * The conversation the browser sends back, cut to what the helpdesk chat
 * itself writes. The server sets the assistant's instructions
 * (`createHelpdeskAgent`); a message from the browser must not add to them.
 *
 * - Only the user's and the assistant's turns: a `system` message (or any other
 *   role) refuses the request.
 * - A user turn keeps its text. An assistant turn keeps its text, its step and
 *   reasoning marks, and its handoff request (the user's approval travels in
 *   it). The search tools' results are dropped: they are the server's to give,
 *   and the model searches again. Any other part, a file, an image, a URL
 *   source or a data part, is dropped: the page never sends one, and the model
 *   would read it.
 * - A kept part keeps only the fields the chat writes (no provider metadata).
 * - A turn left with no part is dropped.
 */

const ROLES = new Set(["user", "assistant"]);
const TEXT_PARTS = new Set(["text", "reasoning"]);
/** The one tool part the browser must send back: the user's answer to a handoff
 * request travels in it. The search tools' results are not taken from the
 * browser; the model searches again when it needs to. */
const HANDOFF = "tool-requestHumanHandoff";

type Part = { type: string } & Record<string, unknown>;
type Message = { id?: string; role: "user" | "assistant"; parts: Part[] };

function isPart(value: unknown): value is Part {
  return (
    typeof value === "object" &&
    value !== null &&
    typeof (value as { type?: unknown }).type === "string"
  );
}

/** A part the chat writes, with only the fields the chat writes, or null. */
function keptPart(part: Part, role: string): Part | null {
  if (TEXT_PARTS.has(part.type) && typeof part.text === "string") {
    if (role === "user" && part.type !== "text") return null;
    return { type: part.type, text: part.text };
  }
  if (role !== "assistant") return null;
  if (part.type === "step-start") return { type: "step-start" };
  if (part.type === HANDOFF) {
    const { type, toolCallId, state, input, output, approval, errorText } =
      part;
    return Object.fromEntries(
      Object.entries({
        type,
        toolCallId,
        state,
        input,
        output,
        approval,
        errorText,
      }).filter(([, value]) => value !== undefined),
    ) as Part;
  }
  return null;
}

/** The conversation without what the chat does not write, or null when a turn
 * is not the user's or the assistant's, or is not a message at all. */
export function conversationFromBrowser(messages: unknown[]): Message[] | null {
  const kept: Message[] = [];
  for (const value of messages) {
    if (typeof value !== "object" || value === null) return null;
    const message = value as { id?: unknown; role?: unknown; parts?: unknown };
    if (typeof message.role !== "string" || !ROLES.has(message.role))
      return null;
    if (!Array.isArray(message.parts)) return null;
    const role = message.role as Message["role"];
    const parts = message.parts
      .filter(isPart)
      .map((part) => keptPart(part, role))
      .filter((part): part is Part => part !== null);
    if (!parts.length) continue;
    kept.push({
      ...(typeof message.id === "string" ? { id: message.id } : {}),
      role,
      parts,
    });
  }
  return kept.length ? kept : null;
}
