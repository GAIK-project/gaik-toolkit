// What the agent writes for something it has not learned yet ("unknown", "n/a",
// "tuntematon"). The review shows it as missing, not as an answer, and it does
// not count as captured when deciding whether Gate 1 can be approved.
const NOT_KNOWN = /^(unknown|n\/?a|none|tbd|-|tuntematon|ei (vielä )?tiedossa|not known( yet)?)\.?$/i;

/** The value, or null when it is empty or a "not known yet" placeholder. */
export function known(value?: string | null): string | null {
  return value && !NOT_KNOWN.test(value.trim()) ? value : null;
}

/** The values that are not placeholders. */
export function knownList(values?: string[] | null): string[] {
  return (values ?? []).filter((v) => known(v) !== null);
}

/**
 * The knowledge processes a use case is classified by: the wizard's own three
 * (solution_wizard's KnowledgeProcess enum), which is why a correction to them
 * is a choice and not free text.
 */
export const KNOWLEDGE_PROCESSES = ["knowledge_capture", "knowledge_access", "knowledge_synthesis"] as const;
export type KnowledgeProcess = (typeof KNOWLEDGE_PROCESSES)[number];

/**
 * The process the agent's word stands for ("knowledge_capture", "Knowledge
 * capture", "capture"); null for a value that is not one of the three.
 */
export function knowledgeProcess(value: string): KnowledgeProcess | null {
  const key = value.trim().toLowerCase().replace(/[\s-]+/g, "_");
  const full = key.startsWith("knowledge_") ? key : `knowledge_${key}`;
  return (KNOWLEDGE_PROCESSES as readonly string[]).includes(full) ? (full as KnowledgeProcess) : null;
}
