/**
 * From a case back to the wizard's chat.
 *
 * A case shows what the generated solution does with real material. When the
 * result says the solution itself is wrong (a field is missing, a step fails,
 * the schema needs another type), the change is made in the chat, not here.
 * The case view sits on its own page, so the reference travels in this
 * browser tab's sessionStorage: the case page keeps it, and the session page's
 * chat takes it once and shows it as the chip above the field, exactly as a
 * "Muuta chatissa" on the session page does. Nothing is sent until the user
 * writes and sends.
 */

import type { ChatReference } from "@/lib/chat-events";
import { asChatReference } from "@/lib/chat-reference";
import { fillTemplate, quoteOneLine } from "@/lib/chat-template";

export type CaseChatTexts = {
  /** "Tapaus #{n}" */
  label: string;
  /** The chip when no case is open. */
  labelNone: string;
  /** "Koskee ratkaisun kokeilua omalla tapauksella #{n} (tila: {status})." */
  prefix: string;
  /** The line when no case is open. */
  prefixNone: string;
  /** '… ajo epäonnistui, virhe lainattuna: "{reason}"' */
  prefixFailed: string;
  /** '… tulos palautettiin korjattavaksi, hyväksyjän kommentti lainattuna: "{comment}"' */
  prefixReturned: string;
  /** '… tapaus ajetaan uudelleen, käyttäjän huomio lainattuna: "{comment}"' */
  prefixRerun: string;
};

const pendingKey = (sessionId: string) => `gaik-wizard:pending-chat-reference:${sessionId}`;

/**
 * The chat reference for a case. `failure` is the run's own message when it
 * failed; `comment` is what the reviewer wrote when returning the case. Either
 * goes along as a quote on one line, so the wizard reads what went wrong
 * without the user typing it again.
 */
export function caseChatReference(
  sessionId: string,
  open: { number: number; status: string; failure?: string | null; comment?: string | null; rerun?: boolean } | null,
  t: CaseChatTexts,
): ChatReference {
  if (!open) return { key: `cases:${sessionId}`, label: t.labelNone, prefix: t.prefixNone };
  const n = String(open.number);
  const failure = open.failure?.trim();
  const comment = open.comment?.trim();
  return {
    key: `cases:${sessionId}`,
    label: fillTemplate(t.label, { n }),
    prefix: failure
      ? fillTemplate(t.prefixFailed, { n, reason: quoteOneLine(failure) })
      : comment
        ? fillTemplate(open.rerun ? t.prefixRerun : t.prefixReturned, { n, comment: quoteOneLine(comment) })
        : fillTemplate(t.prefix, { n, status: open.status }),
  };
}

/** Keeps the reference for the session page's chat. False when storage is blocked. */
export function keepChatReference(sessionId: string, reference: ChatReference): boolean {
  try {
    window.sessionStorage.setItem(pendingKey(sessionId), JSON.stringify(reference));
    return true;
  } catch {
    return false;
  }
}

/** The kept reference, once: it is removed as it is read. Null when there is none. */
export function takeChatReference(sessionId: string): ChatReference | null {
  try {
    const key = pendingKey(sessionId);
    const kept = window.sessionStorage.getItem(key);
    if (kept === null) return null;
    window.sessionStorage.removeItem(key);
    return asChatReference(JSON.parse(kept));
  } catch {
    return null;
  }
}
