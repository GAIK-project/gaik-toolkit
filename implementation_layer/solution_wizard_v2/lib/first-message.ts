/**
 * The message that starts a session, on its way from the start view to the
 * session's chat.
 *
 * A session is created by its first message, on a page that has no chat yet.
 * The start view keeps the message here under the new session's id and opens
 * the session; that page's chat sends it as a normal chat turn, so a message
 * reaches the wizard by one path only. It travels in this browser tab's
 * sessionStorage (as lib/case-chat does), with a copy in memory for a browser
 * that blocks storage: the move between the two pages keeps this module alive.
 *
 * The message is kept until the wizard has started on a turn
 * (dropFirstMessage). It was removed as the session's page read it, and a
 * first turn the wizard refused (no free slot, too many messages a minute)
 * was gone after a reload, in a session named after it. The chat sends it
 * once: a message read before comes back marked `sentBefore`, and goes into
 * the field instead of out again.
 */

export type FirstMessage = {
  text: string;
  /** Where the start view's field stood in the window, in px from its top. */
  fieldTop?: number;
};

/** The kept message as the session's chat reads it. */
export type PendingFirstMessage = FirstMessage & {
  /** An earlier reading already sent it (this page before a reload, say): it is not sent again. */
  sentBefore: boolean;
};

type Kept = FirstMessage & { sent?: boolean };

const pendingKey = (sessionId: string) => `gaik-wizard:pending-first-message:${sessionId}`;
const inMemory = new Map<string, Kept>();

function asKept(value: unknown): Kept | null {
  if (!value || typeof value !== "object") return null;
  const { text, fieldTop, sent } = value as Record<string, unknown>;
  if (typeof text !== "string" || !text.trim()) return null;
  return {
    text,
    ...(typeof fieldTop === "number" && Number.isFinite(fieldTop) ? { fieldTop } : {}),
    ...(sent === true ? { sent: true } : {}),
  };
}

function store(sessionId: string, kept: Kept): void {
  inMemory.set(sessionId, kept);
  try {
    window.sessionStorage.setItem(pendingKey(sessionId), JSON.stringify(kept));
  } catch {
    // Storage blocked: the copy in memory carries it.
  }
}

/** Keeps the message for the session page's chat. */
export function keepFirstMessage(sessionId: string, message: FirstMessage): void {
  store(sessionId, { ...message });
}

/**
 * The kept message, or null when there is none. It stays kept, marked as read:
 * the first reading is the one that sends it (`sentBefore` false), every later
 * one finds it already sent. Content that is not a message is removed.
 */
export function pendingFirstMessage(sessionId: string): PendingFirstMessage | null {
  let kept = inMemory.get(sessionId) ?? null;
  try {
    const stored = window.sessionStorage.getItem(pendingKey(sessionId));
    if (stored !== null) {
      let read: Kept | null = null;
      try {
        read = asKept(JSON.parse(stored));
      } catch {
        // Not JSON: not a message.
      }
      if (read) kept = read;
      else window.sessionStorage.removeItem(pendingKey(sessionId));
    }
  } catch {
    // Storage blocked: the copy in memory stands.
  }
  if (!kept) return null;
  const sentBefore = kept.sent === true;
  if (!sentBefore) store(sessionId, { ...kept, sent: true });
  const { text, fieldTop } = kept;
  return { text, ...(fieldTop === undefined ? {} : { fieldTop }), sentBefore };
}

/** The wizard has started on a turn of this session: nothing is left to hand over. */
export function dropFirstMessage(sessionId: string): void {
  inMemory.delete(sessionId);
  try {
    window.sessionStorage.removeItem(pendingKey(sessionId));
  } catch {
    // Storage blocked: there was only the copy in memory.
  }
}
