import {
  CHAT_REPLYING_EVENT,
  CHAT_SEND_DELIVERED_EVENT,
  CHAT_SEND_EVENT,
  CHAT_SEND_FAILED_EVENT,
} from "@/lib/chat-events";

/** How long the "working" state stays after the reply ends, for the page's new data to arrive. */
export const SETTLE_MS = 1200;

export type PageSendState = "idle" | "sent" | "failed";

export type PageSends = {
  /** Sends `message` as a chat turn (CHAT_SEND_EVENT) and follows it. */
  send: (message: string) => void;
  /** Back to "idle" after a failed send the user gave up on. */
  reset: () => void;
  /** Stops listening; a state change still waiting is dropped. */
  stop: () => void;
};

/**
 * Follows the messages one field on the page sends through the chat: "sent"
 * until the wizard has finished the reply to it, "failed" when it never
 * reached the wizard, "idle" otherwise. `replying` is told whenever the wizard
 * starts or ends a reply to any turn.
 *
 * The state goes back to "idle" a moment after the reply has ended
 * (SETTLE_MS). A message sent within that moment is a new one on its way: the
 * wait of the one before is dropped, or it would call the new message done
 * while the wizard had not started on it.
 *
 * `events` is the window in the page (components/use-page-send).
 */
export function followPageSends(
  events: EventTarget,
  on: { state: (state: PageSendState) => void; replying: (replying: boolean) => void },
): PageSends {
  // The message on its way, and whether the wizard has started on it.
  let last: string | null = null;
  let delivered = false;
  let settle: ReturnType<typeof setTimeout> | undefined;
  const dropSettle = () => {
    clearTimeout(settle);
    settle = undefined;
  };

  const mine = (e: Event) => last !== null && (e as CustomEvent<string>).detail === last;
  const onFailed = (e: Event) => {
    if (!mine(e)) return;
    last = null;
    on.state("failed");
  };
  const onDelivered = (e: Event) => {
    if (mine(e)) delivered = true;
  };
  const onReplying = (e: Event) => {
    const now = Boolean((e as CustomEvent<boolean>).detail);
    on.replying(now);
    if (now || !delivered) return;
    // The reply to this message is done.
    delivered = false;
    last = null;
    dropSettle();
    settle = setTimeout(() => {
      settle = undefined;
      on.state("idle");
    }, SETTLE_MS);
  };
  events.addEventListener(CHAT_SEND_FAILED_EVENT, onFailed);
  events.addEventListener(CHAT_SEND_DELIVERED_EVENT, onDelivered);
  events.addEventListener(CHAT_REPLYING_EVENT, onReplying);

  return {
    send(message) {
      // The chat reports on a message by its trimmed text.
      const text = message.trim();
      if (!text) return;
      // The reply before this one may have ended a moment ago: its "idle" is
      // not this message's.
      dropSettle();
      last = text;
      delivered = false;
      on.state("sent");
      events.dispatchEvent(new CustomEvent(CHAT_SEND_EVENT, { detail: text }));
    },
    reset() {
      dropSettle();
      last = null;
      delivered = false;
      on.state("idle");
    },
    stop() {
      dropSettle();
      events.removeEventListener(CHAT_SEND_FAILED_EVENT, onFailed);
      events.removeEventListener(CHAT_SEND_DELIVERED_EVENT, onDelivered);
      events.removeEventListener(CHAT_REPLYING_EVENT, onReplying);
    },
  };
}
