"use client";

import { useEffect, useRef } from "react";
import { releaseWizard } from "@/app/(app)/sessions/[id]/actions";
import { CHAT_REPLYING_EVENT } from "@/lib/chat-events";
import {
  alreadyReleased,
  forgetReleased,
  releaseFailed,
  releaseStarted,
  rememberReleased,
} from "@/lib/wizard-release";

/**
 * Releases the wizard held for a finished session, once. "End session" was a
 * button on the finished solution, and users asked what it was for: a live
 * wizard is a process on the server, and they are few. Nothing is left for
 * the user to decide there, so the page does it: after the wizard's reply to
 * the last approval has ended (`replyAhead`: that reply is on its way or
 * about to be asked for), or at once for a session opened when it is already
 * done. The next message starts the wizard again by itself, so nothing is
 * shown. A refusal changes nothing on the page: a wizard that is replying is
 * asked again when the reply ends, a failure when the session is next opened.
 * Draws nothing.
 */
export function ReleaseWizardWhenDone({ sessionId, replyAhead }: { sessionId: string; replyAhead: boolean }) {
  // As the page was first drawn: a later reading of the session (the address
  // loses its one-time parameter) is not a reason to release at that moment.
  const waitForReply = useRef(replyAhead);
  useEffect(() => {
    if (alreadyReleased(sessionId)) return;
    let replying = false;
    const release = () => {
      if (alreadyReleased(sessionId)) return;
      const started = releaseStarted(sessionId);
      releaseWizard(sessionId)
        .then((outcome) => {
          if (outcome === "ended") rememberReleased(sessionId, started);
          else releaseFailed(sessionId);
        })
        .catch(() => releaseFailed(sessionId));
    };
    const onReplying = (e: Event) => {
      const now = Boolean((e as CustomEvent<boolean>).detail);
      if (replying && !now) release();
      replying = now;
    };
    window.addEventListener(CHAT_REPLYING_EVENT, onReplying);
    if (!waitForReply.current) release();
    return () => window.removeEventListener(CHAT_REPLYING_EVENT, onReplying);
  }, [sessionId]);
  return null;
}

/**
 * The other half, on a session that is not finished: the mark of an earlier
 * release goes, so that approving the last gate again (it was reopened for a
 * change) releases the wizard again. Draws nothing.
 */
export function ForgetWizardRelease({ sessionId }: { sessionId: string }) {
  useEffect(() => {
    forgetReleased(sessionId);
  }, [sessionId]);
  return null;
}
