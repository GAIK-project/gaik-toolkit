import { fillTemplate } from "@/lib/chat-template";
import type { Dict } from "@/lib/i18n";

/**
 * A blueprint the page brought that the workspace panel did not save itself:
 * the wizard wrote a version in a chat turn, or it was changed in another
 * window. The Workflow tab's diagrams are drawn again from it without a word
 * (a customer reviewer could not tell whether the diagram and the blueprint
 * were in step), so their status line says where the diagram now stands.
 */
export type BlueprintUpdate = {
  /** The session's active blueprint version as the page read it; null when it is not known. */
  version: number | null;
  /** Written while the wizard was replying, or in the reply that ended just before the page read it. */
  fromChat: boolean;
};

/**
 * What the chat has done between two readings of the session by the page.
 * The page reads the session when a reply ends (and when the wizard changes
 * the session in the middle of one), so a blueprint that arrives then is the
 * chat's; one that arrives with no reply since the reading before is not.
 */
export type ChatActivity = { replying: boolean; sinceLastRead: boolean };

export function chatActivityAtLoad(replying: boolean): ChatActivity {
  return { replying, sinceLastRead: false };
}

/** The chat said that a reply started or ended. */
export function chatReplyingChanged(activity: ChatActivity, replying: boolean): ChatActivity {
  return { replying, sinceLastRead: activity.sinceLastRead || activity.replying || replying };
}

/** The page read the session: whether the chat had a part in what it brought, and the activity from here on. */
export function pageReadSession(activity: ChatActivity): { fromChat: boolean; next: ChatActivity } {
  return {
    fromChat: activity.replying || activity.sinceLastRead,
    next: { replying: activity.replying, sinceLastRead: false },
  };
}

/** A version number to show, or null: the session's own number, never a default. */
export function knownVersion(version: unknown): number | null {
  return typeof version === "number" && Number.isInteger(version) && version > 0 ? version : null;
}

/** The status line of a diagram drawn from `update`: where the change came from, and the version shown. */
export function blueprintUpdateText(
  update: BlueprintUpdate,
  t: Pick<Dict, "flowUpdatedFromChat" | "flowUpdatedElsewhere" | "flowBlueprintVersion">,
): string {
  const source = update.fromChat ? t.flowUpdatedFromChat : t.flowUpdatedElsewhere;
  if (update.version === null) return source;
  return `${source} · ${fillTemplate(t.flowBlueprintVersion, { n: String(update.version) })}`;
}
