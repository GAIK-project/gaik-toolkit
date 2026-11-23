"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { getCurrentUser } from "@/lib/current-user";
import { createSession, deleteSession, listSessions, renameSessionTitle } from "@/lib/sessions";
import { audit } from "@/lib/audit";
import { logger } from "@/lib/logger";
import { getIncomingTraceId } from "@/lib/request-context";
import { dictionary, getI18n, LOCALES } from "@/lib/i18n";
import { chatMessageTooLong } from "@/lib/chat-limits";
import { requireOwnedSession } from "@/lib/session-access";
import { WizardApiError } from "@/lib/wizard-api-client";
import { sessionTitleFrom, titleExampleIn, type TitleSource } from "@/lib/session-title";

/** The longest name a session can be given by hand. */
const TITLE_MAX = 80;

export type RemoveSessionState = {
  error: "mismatch" | "busy" | "protected" | "failed" | null;
  /** The session is gone; the dialog that asked closes. */
  deleted?: true;
};

export async function removeSession(
  _previous: RemoveSessionState,
  formData: FormData,
): Promise<RemoveSessionState> {
  const user = await getCurrentUser();
  if (!user) redirect("/login");

  const id = String(formData.get("sessionId") ?? "");
  const typed = String(formData.get("confirmation") ?? "").trim();
  // Only a session on this user's own list, confirmed by its name.
  const session = (await listSessions(user.email)).find((s) => s.id === id);
  if (!session || typed !== session.title.trim()) return { error: "mismatch" };

  const result = await deleteSession(id);
  audit("session.delete", {
    actor: user.email,
    resource: { type: "session", id },
    outcome: result === "deleted" ? "success" : "error",
    traceId: await getIncomingTraceId(),
  });
  if (result !== "deleted") return { error: result };
  // The sidebar lists the sessions on every page.
  revalidatePath("/", "layout");
  // The page that was open showed the session that is gone: on to the start,
  // so it never renders "not found" for a moment.
  if (formData.get("current") === "1") redirect("/");
  return { error: null, deleted: true };
}

export type StartResult =
  | { id: string }
  | { error: "empty" | "too_long" | "session_limit" | "failed" };

/** What names a session in `locale`: the start view's examples. */
function titleSource(locale: (typeof LOCALES)[number], fallback: string): TitleSource {
  return { examples: dictionary(locale).chatActivity.panel.start.exampleList, fallback };
}

/**
 * Starts a session from the user's first message. The message is not stored
 * here: it names the session, and the session's chat sends it as its first
 * turn (lib/first-message), so a message reaches the wizard by one path only.
 */
export async function startSessionFromMessage(message: string): Promise<StartResult> {
  const user = await getCurrentUser();
  if (!user) redirect("/login");

  const text = typeof message === "string" ? message.trim() : "";
  if (!text) return { error: "empty" };
  if (chatMessageTooLong(text)) return { error: "too_long" };

  const { locale, t } = await getI18n();
  // An example picked before the language was switched is in the other
  // language's words. The background sentence the message may start with is
  // left out of the name in either language (lib/chat-background).
  const sources = [locale, ...LOCALES.filter((l) => l !== locale)].map((l) =>
    titleSource(l, t.untitledSession),
  );
  const source = sources.find((s) => titleExampleIn(text, s) !== null) ?? sources[0];
  const title = sessionTitleFrom(text, source);

  const traceId = await getIncomingTraceId();
  let id: string;
  try {
    id = (await createSession(user.email, title, { chatLed: true })).id;
  } catch (err) {
    if (err instanceof WizardApiError && err.code === "session_limit") {
      // The account has started as many sessions as it may: a refusal, not a failure.
      audit("session.create", { actor: user.email, outcome: "denied", traceId });
      return { error: "session_limit" };
    }
    logger.error({ traceId, err }, "session.create failed");
    audit("session.create", { actor: user.email, outcome: "error", traceId });
    return { error: "failed" };
  }
  audit("session.create", {
    actor: user.email,
    resource: { type: "session", id },
    outcome: "success",
    traceId,
  });
  revalidatePath("/", "layout");
  return { id };
}

export type RenameResult =
  | { ok: true; title: string }
  | { ok: false; error: "invalid" | "failed" };

/** A new name for one of the user's own sessions. */
export async function renameSession(id: string, title: string): Promise<RenameResult> {
  const owned = await requireOwnedSession(typeof id === "string" ? id : "");
  if (!owned) return { ok: false, error: "failed" };

  const name = typeof title === "string" ? title.replace(/\s+/g, " ").trim() : "";
  if (!name || name.length > TITLE_MAX) return { ok: false, error: "invalid" };

  const renamed = await renameSessionTitle(id, name);
  audit("session.rename", {
    actor: owned.user.email,
    resource: { type: "session", id },
    outcome: renamed ? "success" : "error",
    traceId: await getIncomingTraceId(),
  });
  if (!renamed) return { ok: false, error: "failed" };
  revalidatePath("/", "layout");
  return { ok: true, title: name };
}
