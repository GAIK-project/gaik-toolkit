/**
 * A session's name, taken from the message that starts it. Nobody is asked to
 * name a session before saying what it is about; the name can be changed
 * afterwards from the session's row.
 */
import { withoutStartLines } from "@/lib/chat-background";
import { exampleIn } from "@/lib/session-start";

/** The longest name made here. A name typed at a rename may be longer. */
export const DERIVED_TITLE_MAX = 40;
/** A first sentence shorter than this is not cut off from what follows it. */
const SENTENCE_MIN = 12;

export type TitleSource = {
  /** The start view's examples: one sent as it was picked names the session by its title. */
  examples: readonly { title: string; prompt: string }[];
  /** The name when the message leaves nothing to name the session by. */
  fallback: string;
};

/** The example a first message was started from as it was picked, if any. */
export function titleExampleIn(message: string, source: TitleSource): number | null {
  return exampleIn(
    withoutStartLines(message),
    source.examples.map((example) => example.prompt),
  );
}

export function sessionTitleFrom(message: string, source: TitleSource): string {
  const example = titleExampleIn(message, source);
  if (example !== null) return source.examples[example].title;

  // The choices' lines say who the user is and how much to ask, not what
  // the session is.
  const rest = withoutStartLines(message);
  let line =
    rest
      .split(/\r?\n/)
      .map((part) => part.replace(/\s+/g, " ").trim())
      .find((part) => part !== "") ?? "";
  // The first sentence, when it says enough to stand as a name.
  const end = /[.!?](?= |$)/.exec(line);
  if (end && end.index >= SENTENCE_MIN) line = line.slice(0, end.index);
  line = line.replace(/[.,;:!?\s]+$/, "");
  if (line.length > DERIVED_TITLE_MAX) {
    // No ellipsis: deleting a session asks for its name to be typed as it is.
    const cut = line.lastIndexOf(" ", DERIVED_TITLE_MAX);
    line = line.slice(0, cut > 0 ? cut : DERIVED_TITLE_MAX).replace(/[.,;:!?\s]+$/, "");
  }
  return line || source.fallback;
}

/**
 * The name a page shows for a session. A session started without a name
 * stores the placeholder ("Untitled session", in the language of that moment)
 * as its name, and nothing replaces it when the wizard later names the
 * solution. Where that is so and the blueprint has a name of its own, the
 * blueprint's name stands for the session.
 */
export function shownSessionTitle(
  title: string,
  blueprintName: string | null | undefined,
  placeholders: readonly string[],
): string {
  const unnamed = (name: string) => name === "" || placeholders.includes(name);
  const own = title.trim();
  const blueprint = (blueprintName ?? "").trim();
  return unnamed(own) && !unnamed(blueprint) ? blueprint : own;
}
