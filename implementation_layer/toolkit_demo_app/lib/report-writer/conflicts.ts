// Report Writer v2: settling a conflict of a knowledge file by hand. Pure functions only.

/** A conflict as a knowledge file holds it. */
export interface KnowledgeConflict {
  topic: string;
  description: string;
  status: string;
  unit_ids?: string[];
  /** Set by a gaik that decides conflicts from source_precedence; older files lack it. */
  preferred_unit_ids?: string[];
  resolved_by?: string | null;
}

/**
 * Whether the conflict names the side the report follows in `preferred_unit_ids`. A gaik
 * with the field writes it on every conflict (empty when unresolved) and reads a resolved
 * conflict without it as unresolved; an older gaik has no such field and follows the side
 * the description gives.
 */
export function namesSides(conflict: KnowledgeConflict): boolean {
  return "preferred_unit_ids" in conflict;
}

/**
 * The reason the chosen side cannot settle the conflict, or null when it can: it must name
 * at least one of the conflict's units and not all of them.
 */
export function sideProblem(
  conflict: KnowledgeConflict,
  preferred: string[],
): string | null {
  if (!namesSides(conflict)) return null;
  const ids = conflict.unit_ids ?? [];
  if (preferred.length === 0) return "Choose the fact the report should follow.";
  if (preferred.some((id) => !ids.includes(id)))
    return "Choose only facts of this conflict.";
  if (ids.every((id) => preferred.includes(id)))
    return "Leave out at least one fact: the report follows the chosen side.";
  return null;
}

/**
 * Mark the conflict resolved with the user's reason, and, where the knowledge names
 * sides, the facts to follow, so that the writer does not read it as unresolved.
 * Throws when the side cannot settle it (see `sideProblem`).
 */
export function resolveConflict(
  conflict: KnowledgeConflict,
  decision: string,
  preferred: string[],
): void {
  const problem = sideProblem(conflict, preferred);
  if (problem) throw new Error(problem);
  conflict.status = "resolved";
  conflict.description = decision;
  if (namesSides(conflict)) {
    conflict.preferred_unit_ids = [...preferred];
    conflict.resolved_by = "user";
  }
}
