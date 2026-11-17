/**
 * A reply the user stopped while it was being written.
 *
 * wizard_api stores what was written so far as the reply, with `stopped: true`
 * and, at the end of its text, a short note in the user's language
 * (`stoppedNote`, "(Pysäytetty)"): a reader that does not know the flag, an
 * export or the wizard itself reading the conversation again, still sees that
 * the reply is not whole. The chat shows the text without that note and a
 * quiet mark under it instead, in the interface's language.
 */

/** What the stored text of a stopped reply ends with; the same words as wizard_api's. */
export const STOPPED_NOTE: Record<"fi" | "en", string> = {
  fi: "(Pysäytetty)",
  en: "(Stopped)",
};

type StoppedMessage = { content: string; stopped?: boolean; stoppedNote?: string };

/** The text as it is stored: what was written, then the note; the note alone when nothing was. */
export function withStoppedNote(written: string, note: string): string {
  const text = written.trim();
  return text ? `${text}\n\n${note}` : note;
}

/**
 * A reply's text as the chat shows it: a stopped one without the note it was
 * stored with (the mark under it says the same), any other as it is.
 */
export function shownReply(message: StoppedMessage): string {
  const { content, stopped, stoppedNote } = message;
  if (!stopped || !stoppedNote) return content;
  const text = content.trimEnd();
  return text.endsWith(stoppedNote) ? text.slice(0, -stoppedNote.length).trimEnd() : content;
}
