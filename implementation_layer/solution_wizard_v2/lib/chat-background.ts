/**
 * What the wizard is told with the user's first message: who the user is
 * (not technical or technical) and how much to ask (quick or thorough). Both
 * are choices beside the message field and state only: nothing is written
 * into the field. Each choice's sentence goes to the wizard as a line of its
 * own at the start of the user's first message, added as that message is
 * sent, and is taken out again wherever the message is shown. Nothing is
 * stored on the server.
 */

export const BACKGROUNDS = ["nonTechnical", "technical"] as const;
export type Background = (typeof BACKGROUNDS)[number];

export const PACES = ["quick", "thorough"] as const;
export type Pace = (typeof PACES)[number];
/** How much the wizard asks until the user says otherwise. */
export const DEFAULT_PACE: Pace = "quick";

/** The choices a viewer last made; a per-browser convenience. */
export const BACKGROUND_KEY = "gaik-wizard.chat-background";
export const PACE_KEY = "gaik-wizard.chat-pace";

/**
 * What the wizard is told, in the interface's language. The dictionaries
 * (lib/i18n) take their sentences from here, so the sentence that is sent and
 * the one that is taken out of a shown message are always the same words.
 */
export const BACKGROUND_SENTENCES: Record<"fi" | "en", Record<Background, string>> = {
  fi: {
    nonTechnical: "Taustani: en ole tekninen. Kysy arkikielellä ja ehdota oletukset teknisiin kohtiin.",
    technical: "Taustani: olen tekninen. Voit käyttää teknisiä termejä ja kysyä teknisistä valinnoista suoraan.",
  },
  en: {
    nonTechnical: "My background: not technical. Ask in plain language and suggest defaults for the technical parts.",
    technical: "My background: technical. Feel free to use technical terms and ask me about technical choices directly.",
  },
};

export const PACE_SENTENCES: Record<"fi" | "en", Record<Pace, string>> = {
  fi: {
    quick:
      "Tahti: nopea. Kysy vain se, mitä et voi kohtuudella olettaa, mieluiten yhdellä kierroksella; ehdota muuhun oletukset ja listaa ne oletuksina.",
    thorough: "Tahti: perusteellinen. Kysy se, mitä tarvitset yksityiskohtien saamiseksi oikein.",
  },
  en: {
    quick:
      "Pace: quick. Ask only what you cannot reasonably assume, in one round if you can; propose defaults for the rest and list them as assumptions.",
    thorough: "Pace: thorough. Ask what you need to get the details right.",
  },
};

/** Every sentence of one choice, in both languages. */
const all = <T extends string>(sentences: Record<string, Record<T, string>>): string[] =>
  Object.values(sentences).flatMap((byChoice) => Object.values<string>(byChoice));

// In the order the lines are sent: who the user is, then how much to ask.
const START_LINES: readonly string[][] = [all(BACKGROUND_SENTENCES), all(PACE_SENTENCES)];

export function isBackground(value: unknown): value is Background {
  return typeof value === "string" && (BACKGROUNDS as readonly string[]).includes(value);
}

export function isPace(value: unknown): value is Pace {
  return typeof value === "string" && (PACES as readonly string[]).includes(value);
}

/**
 * The first message as the wizard gets it: each choice's sentence on a line
 * of its own (the background first, then the pace), then the user's words. A
 * message that says nothing is left as it is, so the sentences are never sent
 * alone.
 */
export function withStartLines(message: string, lines: readonly (string | null | undefined)[]): string {
  const text = message.trim();
  const lead = lines.map((line) => line?.trim()).filter((line): line is string => Boolean(line));
  if (!text || lead.length === 0) return message;
  return [...lead, text].join("\n");
}

/**
 * A user's message as it is shown and as a session is named from it: without
 * the choices' sentences at its start, in either language and for either
 * option. A session started while the background sentence still stood in the
 * message field has it on the same line as the user's words; that reads clean
 * too. A message that does not start with one is returned as it is.
 */
export function withoutStartLines(message: string): string {
  let text = message.trimStart();
  let found = false;
  for (const sentences of START_LINES) {
    const sentence = sentences.find((s) => text.startsWith(s));
    if (!sentence) continue;
    text = text.slice(sentence.length).trimStart();
    found = true;
  }
  return found ? text : message;
}

/** The most the sentences and their line breaks add to a first message, in characters. */
export const START_LINES_ROOM = START_LINES.reduce(
  (room, sentences) => room + Math.max(...sentences.map((s) => s.length)) + 1,
  0,
);

/**
 * One remembered choice. Kept in the browser's storage, and in memory as this
 * page holds it: what a browser that blocks storage goes by, on the start
 * view and on the session's page it opens.
 */
function choiceStore<T extends string>(key: string, known: (value: unknown) => value is T) {
  let held: T | null = null;
  let blocked = false;
  const listeners = new Set<() => void>();
  return {
    /** The choice made now or in an earlier session in this browser; null when none is. */
    saved(): T | null {
      if (blocked) return held;
      try {
        const saved = window.localStorage.getItem(key);
        return known(saved) ? saved : null;
      } catch {
        // Storage blocked: what was chosen on this page stands.
        return held;
      }
    },
    /** Makes the choice and remembers it for the next session; null takes it back. */
    save(chosen: T | null): void {
      held = chosen;
      try {
        if (chosen) window.localStorage.setItem(key, chosen);
        else window.localStorage.removeItem(key);
        blocked = false;
      } catch {
        // Not remembered past this page.
        blocked = true;
      }
      for (const listener of listeners) listener();
    },
    /** Calls `listener` when the choice changes, here or in another tab. */
    onChange(listener: () => void): () => void {
      listeners.add(listener);
      window.addEventListener("storage", listener);
      return () => {
        listeners.delete(listener);
        window.removeEventListener("storage", listener);
      };
    },
  };
}

const background = choiceStore(BACKGROUND_KEY, isBackground);
const pace = choiceStore(PACE_KEY, isPace);

/** Who the user said they are. Null when they have not said. */
export const savedBackground = background.saved;
export const saveBackground = background.save;
export const onBackgroundChange = background.onChange;

/** How much the wizard asks: what the user chose, or the default. */
export const savedPace = (): Pace => pace.saved() ?? DEFAULT_PACE;
/** Null goes back to the default. */
export const savePace = pace.save;
export const onPaceChange = pace.onChange;
