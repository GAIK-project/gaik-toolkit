// Upper bound for one chat message, in characters. The API refuses longer ones
// too (WIZARD_MAX_CHAT_MESSAGE_CHARS, default the same); checking here first
// keeps an oversized body from being forwarded at all. Every message is a
// model call billed by length, and a pasted document belongs in an upload.
export const MAX_CHAT_MESSAGE_CHARS = 20_000;

// What the chat says when a message cannot be answered, instead of the
// generic stream failure: too long (413), no free agent slot (503), the user's
// own agents all busy (429 agent_busy), too many messages a minute (429
// rate_limited), or the agent stopped at its per-message step limit (an error
// frame with limit).
export type ChatErrorLabels = {
  tooLong: string;
  capacity: string;
  agentBusy: string;
  rateLimited: string;
  turnLimit: string;
  usageSession: string;
  usageUser: string;
  usageDeployment: string;
};

/**
 * The chat's own message for a refused chat request, or undefined for any other
 * answer. `error` is the code the chat route answers a 429 with: `agent_busy`
 * (WIZARD_MAX_LIVE_AGENTS_PER_USER) or `rate_limited`
 * (WIZARD_MAX_CHAT_TURNS_PER_MINUTE). A 402 is a reached usage cap, and `scope`
 * says whose: `session`, `user` or `deployment` (the API's usage caps).
 */
export function chatRefusalLabel(
  status: number,
  error: unknown,
  labels: ChatErrorLabels | undefined,
  scope?: unknown,
): string | undefined {
  if (!labels) return undefined;
  if (status === 413) return labels.tooLong;
  if (status === 503) return labels.capacity;
  if (status === 429) return error === "rate_limited" ? labels.rateLimited : labels.agentBusy;
  if (status === 402) {
    if (scope === "user") return labels.usageUser;
    if (scope === "deployment") return labels.usageDeployment;
    return labels.usageSession;
  }
  return undefined;
}

export function chatMessageTooLong(message: string): boolean {
  return message.length > MAX_CHAT_MESSAGE_CHARS;
}
