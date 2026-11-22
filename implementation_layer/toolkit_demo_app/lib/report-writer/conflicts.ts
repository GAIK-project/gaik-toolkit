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
 * The chosen facts that are still facts of the conflict: one removed while the choice
 * was open is no longer chosen.
 */
export function stillChosen(
  conflict: KnowledgeConflict,
  preferred: string[],
): string[] {
  const ids = conflict.unit_ids ?? [];
  return preferred.filter((id) => ids.includes(id));
}

/**
 * The facts a resolved conflict follows: its `preferred_unit_ids`. Empty for an
 * unresolved conflict, for a file from a gaik that names no sides, and where gaik reads
 * the side as none chosen (`Conflict._side_named`): it names a fact that is not one of
 * the conflict's, or every one of them. gaik then reads the conflict as unresolved.
 */
export function followedIds(conflict: KnowledgeConflict): string[] {
  if (conflict.status !== "resolved") return [];
  const ids = conflict.unit_ids ?? [];
  const preferred = conflict.preferred_unit_ids ?? [];
  if (
    preferred.some((id) => !ids.includes(id)) ||
    ids.every((id) => preferred.includes(id))
  )
    return [];
  return [...preferred];
}

/**
 * A key for each conflict that stays the same when facts are removed: its topic and
 * description, which `withoutFact` leaves as they are, whatever else it drops. Conflicts
 * alike in both are told apart by their order.
 */
export function conflictKeys(conflicts: KnowledgeConflict[]): string[] {
  const seen = new Map<string, number>();
  return conflicts.map((conflict) => {
    const key = JSON.stringify([conflict.topic, conflict.description]);
    const count = seen.get(key) ?? 0;
    seen.set(key, count + 1);
    return count === 0 ? key : `${key}#${count}`;
  });
}

/**
 * Who settled a resolved conflict, in a few words: "by hand", or the source class that
 * ranks first ("by primary sources"). Null when the file does not say.
 */
export function resolvedByText(conflict: KnowledgeConflict): string | null {
  if (followedIds(conflict).length === 0 || !conflict.resolved_by) return null;
  return conflict.resolved_by === "user"
    ? "by hand"
    : `by ${conflict.resolved_by} sources`;
}

/**
 * The conflicts after the fact `unitId` was removed, so that none names a fact that is
 * gone. Its id leaves `unit_ids` and `preferred_unit_ids`. A conflict with fewer than two
 * facts left, or a resolved one left with only the facts it follows, has no other side
 * and is dropped. A resolved conflict whose followed facts are all gone is unresolved
 * again, as gaik reads it: the report gives the sides that are left until a person
 * settles it again. A file from a gaik that names no sides only loses the id.
 */
export function withoutFact(
  conflicts: KnowledgeConflict[],
  unitId: string,
): KnowledgeConflict[] {
  const kept: KnowledgeConflict[] = [];
  for (const conflict of conflicts) {
    if (!conflict.unit_ids?.includes(unitId)) {
      kept.push(conflict);
      continue;
    }
    const unitIds = conflict.unit_ids.filter((id) => id !== unitId);
    if (unitIds.length < 2) continue;
    const next: KnowledgeConflict = { ...conflict, unit_ids: unitIds };
    if (namesSides(conflict)) {
      const preferred = (conflict.preferred_unit_ids ?? []).filter(
        (id) => id !== unitId,
      );
      next.preferred_unit_ids = preferred;
      if (conflict.status === "resolved") {
        if (unitIds.every((id) => preferred.includes(id))) continue;
        if (!preferred.some((id) => unitIds.includes(id))) {
          next.status = "unresolved";
          next.preferred_unit_ids = [];
          next.resolved_by = null;
        }
      }
    }
    kept.push(next);
  }
  return kept;
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
