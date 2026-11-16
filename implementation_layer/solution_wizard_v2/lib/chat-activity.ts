/**
 * The chat's progress line while the agent works.
 *
 * wizard_api sends `{"activity": {"kind", "file"}}` when the agent starts a
 * tool: writing or reading a file, running a check, searching. Long steps
 * (schema generation, writing the package) used to show only the typing dots
 * for minutes. The kind and a file's base name come from the server; the
 * words are chosen here, in the user's language.
 *
 * That frame is all the stream tells about a step: one arrives as a tool
 * starts, none when it ends, and a check that is run says nothing about what
 * it checks. So a step counts as finished when the next one starts, and
 * several of the same in a row are one line with their number.
 */

export type ActivityKind = "write" | "read" | "run" | "search" | "work";
export type ChatActivity = { kind: ActivityKind; file: string | null };

export type ChatActivityLabels = {
  write: string;
  writeFile: string;
  read: string;
  readFile: string;
  run: string;
  search: string;
  work: string;
  elapsed: string;
  /** Summary of a finished turn's steps, with {n}. */
  steps: string;
  /**
   * Plain words for the files the agent writes, by base name
   * ("use_case.blueprint.json" → "the solution plan"). A file not listed is
   * named as it is.
   */
  files: Record<string, string>;
  /** Accessible name of a diagram drawn in the chat. */
  diagram: string;
  /** Accessible name of a diagram whose steps are known, with {steps}. */
  diagramSteps: string;
  /** Shown in place of a diagram while it is still being written or drawn. */
  diagramDrawing: string;
  /** Opens a diagram at full size. */
  diagramExpand: string;
  /** Closes the full-size diagram. */
  diagramClose: string;
  /** The card behind a GAIK component's name in a reply (lib/component-links);
   *  without these words the name stays plain text. */
  components?: {
    /** What the component does, with {inputs} and {outputs}. */
    line: string;
    /** The link to the component's documentation. */
    docs: string;
    /** Plain words for the registry's artifact types. */
    artifacts: Record<string, string>;
  };
  /** The chat panel's own words; kept here because the page hands the chat this group. */
  panel: ChatPanelLabels;
};

export type ChatPanelLabels = {
  /** In the message field while a gate's chip is attached: what to write, with {n}. */
  gatePlaceholder: string;
  /** Accessible name of the button that removes the reference chip. */
  referenceRemove: string;
  /** Group name of the background choice. */
  background: string;
  nonTechnical: string;
  /** The sentence the choice sends ahead of the first message (lib/chat-background). */
  nonTechnicalText: string;
  technical: string;
  technicalText: string;
  /** What each background changes, said under its name in the choice's menu. */
  nonTechnicalHint: string;
  technicalHint: string;
  /** Group name of the choice of how much the wizard asks. */
  pace: string;
  quick: string;
  /** The sentence the choice sends ahead of the first message, after the background's. */
  quickText: string;
  thorough: string;
  thoroughText: string;
  /** What each pace changes, said under its name in the choice's menu. */
  quickHint: string;
  thoroughHint: string;
  /** The empty chat while it is the page (lib/session-start). */
  start: {
    /** The question the page opens with. */
    title: string;
    /** What the wizard does with the answer. */
    lede: string;
    /** In the field: what a first message tells. */
    placeholder: string;
    /** Group name of the examples. */
    examples: string;
    /** Each example's chip and the text it puts into the field. */
    exampleList: { title: string; prompt: string }[];
  };
  /** A gate approved in the panel, as an event line in the chat; with {n}. */
  gateApproved: string;
  /** The button the wizard offers when asked for the other language, and the
   *  message sent once the interface has switched; each in its own language. */
  languageOffer: Record<"fi" | "en", { label: string; message: string }>;
};

const KINDS: ReadonlySet<string> = new Set(["write", "read", "run", "search", "work"]);

/** The activity of one stream event, or null when it has none. */
export function parseActivity(evt: unknown): ChatActivity | null {
  if (!evt || typeof evt !== "object") return null;
  const raw = (evt as { activity?: unknown }).activity;
  if (!raw || typeof raw !== "object") return null;
  const { kind, file } = raw as { kind?: unknown; file?: unknown };
  if (typeof kind !== "string" || !KINDS.has(kind)) return null;
  return { kind: kind as ActivityKind, file: typeof file === "string" && file ? file : null };
}

/** A file's plain name for the user, or its own name when it has none. */
export function fileName(file: string, labels: Pick<ChatActivityLabels, "files">): string {
  return Object.prototype.hasOwnProperty.call(labels.files, file) ? labels.files[file] : file;
}

/** "Writing the solution plan", "Reading raportti.pdf", "Running a check", … */
export function activityText(activity: ChatActivity, labels: ChatActivityLabels): string {
  if (activity.kind === "write") {
    return activity.file ? labels.writeFile.replace("{file}", () => fileName(activity.file!, labels)) : labels.write;
  }
  if (activity.kind === "read") {
    return activity.file ? labels.readFile.replace("{file}", () => fileName(activity.file!, labels)) : labels.read;
  }
  return labels[activity.kind];
}

/** A step of the running reply, and how many times in a row the agent took it. */
export type TurnStep = { text: string; times: number };

/** The steps with one more: a step taken again straight away is counted, not listed twice. */
export function addStep(steps: TurnStep[], text: string): TurnStep[] {
  const last = steps[steps.length - 1];
  if (last && last.text === text) return [...steps.slice(0, -1), { text, times: last.times + 1 }];
  return [...steps, { text, times: 1 }];
}

/** A step as the chat lists it: "Running a check", "Running a check ×3". */
export function stepLine(step: TurnStep): string {
  return step.times > 1 ? `${step.text} ×${step.times}` : step.text;
}

/** How many finished steps the live line shows under the running one. */
const LIVE_FINISHED = 2;

/**
 * What the chat shows while a reply is on its way: the step that is running
 * (null before the first) and the last finished ones, newest first, each with
 * its place in the turn so the line it is drawn on stays the same line.
 */
export function liveSteps(steps: TurnStep[]): {
  current: string | null;
  finished: { at: number; text: string }[];
} {
  if (steps.length === 0) return { current: null, finished: [] };
  const finished = steps
    .slice(0, -1)
    .map((step, at) => ({ at, text: stepLine(step) }))
    .slice(-LIVE_FINISHED)
    .reverse();
  return { current: stepLine(steps[steps.length - 1]), finished };
}

/** How long a step runs before the chat shows its time, in seconds. */
const ELAPSED_FROM = 10;

/** How long the running step has taken, once that is longer than ten seconds. */
export function elapsedText(seconds: number, labels: ChatActivityLabels): string | null {
  if (!(seconds > ELAPSED_FROM)) return null;
  return labels.elapsed.replace("{s}", String(Math.floor(seconds)));
}
