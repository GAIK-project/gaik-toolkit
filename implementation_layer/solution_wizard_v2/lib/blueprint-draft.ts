import type { Blueprint, BlueprintStep } from "@/lib/mock-sessions";

/**
 * The Blueprint form's draft: what it sends when it saves, and when it may
 * save. The form saves by itself, so "is there something to save" and "may it
 * be saved" are decided here, on the content a save would write.
 */

/** How long the form waits after the last edit before it saves by itself. */
export const BLUEPRINT_AUTOSAVE_DELAY_MS = 2500;

function settingsEntries(step: BlueprintStep): [string, string][] {
  return Object.entries(step.settings ?? {});
}

/**
 * The blueprint a save writes: strings trimmed, empty optional step fields
 * left out, and the keys the form does not edit (data_objects, gateways,
 * integration_targets) kept, so a save never loses what the diagram synced.
 * The keys come in one order, so two drafts with the same content compare equal.
 */
export function blueprintPayload(draft: Blueprint): Blueprint {
  const { name, description, goal, steps, ...rest } = draft;
  const kept = Object.fromEntries(Object.entries(rest).sort(([a], [b]) => a.localeCompare(b)));
  return {
    name: name.trim(),
    description: description?.trim() ?? "",
    goal: goal?.trim() ?? "",
    steps: steps.map((s) => {
      const settings = Object.fromEntries(
        settingsEntries(s)
          .map(([k, v]) => [k.trim(), v.trim()] as [string, string])
          .filter(([k]) => k.length > 0),
      );
      return {
        id: s.id,
        name: s.name.trim(),
        type: s.type,
        ...(s.component && s.component.trim() ? { component: s.component.trim() } : {}),
        ...(s.description && s.description.trim() ? { description: s.description.trim() } : {}),
        ...(Object.keys(settings).length ? { settings } : {}),
      };
    }),
    ...kept,
  };
}

/** The saved content as a comparable key: equal keys mean a save would change nothing. */
export function blueprintPayloadKey(draft: Blueprint): string {
  return JSON.stringify(blueprintPayload(draft));
}

/**
 * A short tag of the blueprint an edit was made on, sent with a save that
 * starts by itself. The route compares it with the blueprint the server holds
 * and refuses the save (409 changed_elsewhere) when they differ: a version
 * the agent wrote after the page last read the blueprint would otherwise be
 * replaced by a canvas or form that never showed it. Not a secret and not a
 * check of content, only "is this still the version the edit started from".
 */
export function blueprintBaseTag(blueprint: Blueprint): string {
  const text = blueprintPayloadKey(blueprint);
  // cyrb53: a fast 53-bit string hash, the same in the browser and on the server.
  let h1 = 0xdeadbeef;
  let h2 = 0x41c6ce57;
  for (let i = 0; i < text.length; i++) {
    const ch = text.charCodeAt(i);
    h1 = Math.imul(h1 ^ ch, 2654435761);
    h2 = Math.imul(h2 ^ ch, 1597334677);
  }
  h1 = Math.imul(h1 ^ (h1 >>> 16), 2246822507) ^ Math.imul(h2 ^ (h2 >>> 13), 3266489909);
  h2 = Math.imul(h2 ^ (h2 >>> 16), 2246822507) ^ Math.imul(h1 ^ (h1 >>> 13), 3266489909);
  return (4294967296 * (2097151 & h2) + (h1 >>> 0)).toString(36);
}

/** The 409 a save gets when the blueprint changed since its edit started. */
export const BLUEPRINT_CHANGED_ELSEWHERE = "changed_elsewhere";

/** Whether a save sent with `base` would write over a blueprint it never showed. */
export function baseIsStale(base: unknown, current: Blueprint): boolean {
  return typeof base === "string" && base.length > 0 && base !== blueprintBaseTag(current);
}

export type BlueprintDraftProblem = "name" | "stepName";

/** Why a draft is not saved yet: the blueprint or one of its steps has no name. */
export function blueprintDraftProblem(draft: Blueprint): BlueprintDraftProblem | null {
  if (draft.steps.some((s) => !s.name.trim())) return "stepName";
  if (!draft.name.trim()) return "name";
  return null;
}

/**
 * A step's settings with one key renamed, at its place in the list. The
 * settings come back as they are when the new key is empty or is already
 * another setting's: a rename never drops a value or writes over one.
 */
export function renameSetting(
  settings: Record<string, string>,
  oldKey: string,
  newKey: string,
): Record<string, string> {
  const key = newKey.trim();
  const keys = Object.keys(settings);
  if (!key || key === oldKey || !keys.includes(oldKey)) return settings;
  if (keys.some((k) => k !== oldKey && k.trim() === key)) return settings;
  return Object.fromEntries(Object.entries(settings).map(([k, v]) => [k === oldKey ? key : k, v]));
}

/**
 * The largest save body sent with fetch's `keepalive`, in bytes. The browser
 * lets a page's keepalive requests carry 64 KiB together and refuses a larger
 * one outright, so this leaves room for the headers.
 */
export const BLUEPRINT_KEEPALIVE_MAX_BYTES = 60_000;

/** A removed step back at its place ("Kumoa"); at the end when the list got shorter meanwhile. */
export function restoreStep(steps: BlueprintStep[], step: BlueprintStep, index: number): BlueprintStep[] {
  if (steps.some((s) => s.id === step.id)) return steps;
  const at = Math.min(Math.max(index, 0), steps.length);
  return [...steps.slice(0, at), step, ...steps.slice(at)];
}
