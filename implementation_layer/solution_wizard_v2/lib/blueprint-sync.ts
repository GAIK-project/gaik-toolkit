import type { Blueprint } from "@/lib/mock-sessions";

/**
 * The blueprint's content as a comparable key. Every router.refresh() hands
 * the panel a new object, so identity says nothing about whether the
 * blueprint itself changed.
 */
export function blueprintKey(blueprint: Blueprint): string {
  return JSON.stringify(blueprint);
}

/**
 * What the blueprint editor shows when the blueprint it was opened on changes
 * underneath it — the agent wrote a new version from the chat, or the BPMN
 * tab saved one. A draft without edits takes the new blueprint; a draft the
 * user has edited is kept, and `changedElsewhere` says that saving it will
 * replace the newer blueprint. Before this the panel never took the new
 * blueprint at all, so the Plan and Blueprint tabs showed the first version
 * and a save from there wrote it back over the agent's work.
 */
export function draftOnBlueprintChange(
  draft: Blueprint,
  previous: Blueprint,
  next: Blueprint,
): { draft: Blueprint; changedElsewhere: boolean } {
  const draftKey = blueprintKey(draft);
  if (draftKey === blueprintKey(previous) || draftKey === blueprintKey(next)) {
    return { draft: structuredClone(next), changedElsewhere: false };
  }
  return { draft, changedElsewhere: true };
}
