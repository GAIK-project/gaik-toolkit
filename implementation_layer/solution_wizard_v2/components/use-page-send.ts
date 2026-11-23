"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { followPageSends, type PageSendState, type PageSends } from "@/lib/page-send";

export type { PageSendState } from "@/lib/page-send";

/**
 * Sends one message from a field on the page as a chat turn (CHAT_SEND_EVENT:
 * the chat owns sending) and follows what became of it: "sent" until the
 * wizard has finished the reply to it, "failed" when it never reached the
 * wizard (the sender then offers it again), "idle" otherwise. `replying` is
 * true while the wizard answers any turn, when a new send would be refused.
 * The following itself is lib/page-send.
 */
export function usePageSend(): {
  state: PageSendState;
  replying: boolean;
  send: (message: string) => void;
  /** Back to "idle" after a failed send the user gave up on. */
  reset: () => void;
} {
  const [state, setState] = useState<PageSendState>("idle");
  const [replying, setReplying] = useState(false);
  const sends = useRef<PageSends | null>(null);

  useEffect(() => {
    const following = followPageSends(window, { state: setState, replying: setReplying });
    sends.current = following;
    return () => {
      following.stop();
      sends.current = null;
    };
  }, []);

  const send = useCallback((message: string) => sends.current?.send(message), []);
  const reset = useCallback(() => sends.current?.reset(), []);

  return { state, replying, send, reset };
}
