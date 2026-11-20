import { beforeEach, describe, expect, it, vi } from "vitest";

const state = vi.hoisted(() => ({
  user: { email: "alice@example.test" } as { email: string } | null,
  locale: "fi" as string | undefined,
  createSession: vi.fn(),
  deleteSession: vi.fn(),
  listSessions: vi.fn(),
  renameSessionTitle: vi.fn(),
  requireOwnedSession: vi.fn(),
  revalidatePath: vi.fn(),
  audit: vi.fn(),
}));

vi.mock("next/headers", () => ({
  cookies: async () => ({
    get: (name: string) =>
      name === "gaik_locale" && state.locale ? { value: state.locale } : undefined,
  }),
  headers: async () => ({ get: () => null }),
}));
vi.mock("next/navigation", () => ({
  redirect: (url: string) => {
    throw new Error(`REDIRECT ${url}`);
  },
}));
vi.mock("next/cache", () => ({ revalidatePath: state.revalidatePath }));
vi.mock("@/lib/current-user", () => ({ getCurrentUser: async () => state.user }));
vi.mock("@/lib/sessions", () => ({
  createSession: state.createSession,
  deleteSession: state.deleteSession,
  listSessions: state.listSessions,
  renameSessionTitle: state.renameSessionTitle,
}));
vi.mock("@/lib/session-access", () => ({ requireOwnedSession: state.requireOwnedSession }));
vi.mock("@/lib/audit", () => ({ audit: state.audit }));
vi.mock("@/lib/logger", () => ({ logger: { error: vi.fn(), info: vi.fn() } }));

import { dictionary } from "@/lib/i18n";
import { withStartLines } from "@/lib/chat-background";
import { MAX_CHAT_MESSAGE_CHARS } from "@/lib/chat-limits";
import { WizardApiError } from "@/lib/wizard-api-client";
import { removeSession, renameSession, startSessionFromMessage } from "./actions";

const fi = dictionary("fi");
const en = dictionary("en");

beforeEach(() => {
  vi.clearAllMocks();
  state.user = { email: "alice@example.test" };
  state.locale = "fi";
  state.createSession.mockResolvedValue({ id: "ses_new" });
});

describe("startSessionFromMessage", () => {
  it("creates one session named by the message and reads the sidebar again", async () => {
    expect(await startSessionFromMessage("  Luokittele saapuvat laskut. Niitä on paljon.  ")).toEqual({
      id: "ses_new",
    });
    expect(state.createSession).toHaveBeenCalledTimes(1);
    expect(state.createSession).toHaveBeenCalledWith("alice@example.test", "Luokittele saapuvat laskut", {
      chatLed: true,
    });
    expect(state.revalidatePath).toHaveBeenCalledWith("/", "layout");
    expect(state.audit).toHaveBeenCalledWith(
      "session.create",
      expect.objectContaining({ outcome: "success", resource: { type: "session", id: "ses_new" } }),
    );
  });

  it("names a session started from an example by the example", async () => {
    const example = fi.chatActivity.panel.start.exampleList[1];
    await startSessionFromMessage(
      withStartLines(example.prompt, [fi.chatActivity.panel.technicalText, fi.chatActivity.panel.quickText]),
    );
    expect(state.createSession).toHaveBeenCalledWith("alice@example.test", example.title, {
      chatLed: true,
    });
  });

  it("reads background and pace lines left from the other language", async () => {
    state.locale = "en";
    await startSessionFromMessage(
      withStartLines("Tiivistä kokousmuistiot", [
        fi.chatActivity.panel.nonTechnicalText,
        fi.chatActivity.panel.thoroughText,
      ]),
    );
    expect(state.createSession).toHaveBeenCalledWith("alice@example.test", "Tiivistä kokousmuistiot", {
      chatLed: true,
    });
  });

  it("names a session by an example picked before the language was switched", async () => {
    state.locale = "en";
    const example = fi.chatActivity.panel.start.exampleList[1];
    await startSessionFromMessage(example.prompt);
    expect(state.createSession).toHaveBeenCalledWith("alice@example.test", example.title, {
      chatLed: true,
    });
  });

  it("falls back to the untitled name in the interface's language", async () => {
    state.locale = "en";
    await startSessionFromMessage(
      `${en.chatActivity.panel.technicalText}\n${en.chatActivity.panel.quickText}`,
    );
    expect(state.createSession).toHaveBeenCalledWith("alice@example.test", en.untitledSession, {
      chatLed: true,
    });
  });

  it("refuses an empty message without creating anything", async () => {
    expect(await startSessionFromMessage("   \n ")).toEqual({ error: "empty" });
    expect(state.createSession).not.toHaveBeenCalled();
  });

  it("refuses a message the chat would refuse as too long", async () => {
    expect(await startSessionFromMessage("x".repeat(MAX_CHAT_MESSAGE_CHARS + 1))).toEqual({
      error: "too_long",
    });
    expect(state.createSession).not.toHaveBeenCalled();
  });

  it("says so when the session could not be created", async () => {
    state.createSession.mockRejectedValueOnce(new Error("api down"));
    expect(await startSessionFromMessage("Luokittele laskut")).toEqual({ error: "failed" });
    expect(state.revalidatePath).not.toHaveBeenCalled();
    expect(state.audit).toHaveBeenCalledWith(
      "session.create",
      expect.objectContaining({ outcome: "error" }),
    );
  });

  it("says the account has no sessions left when the api refuses one more", async () => {
    state.createSession.mockRejectedValueOnce(
      new WizardApiError(
        429,
        "/sessions",
        JSON.stringify({ detail: { error: "session_limit", message: "x" } }),
      ),
    );
    expect(await startSessionFromMessage("Luokittele laskut")).toEqual({ error: "session_limit" });
    expect(state.audit).toHaveBeenCalledWith(
      "session.create",
      expect.objectContaining({ outcome: "denied" }),
    );
  });

  it("sends a signed-out caller to the login page", async () => {
    state.user = null;
    await expect(startSessionFromMessage("Luokittele laskut")).rejects.toThrow("REDIRECT /login");
    expect(state.createSession).not.toHaveBeenCalled();
  });
});

describe("renameSession", () => {
  beforeEach(() => {
    state.requireOwnedSession.mockResolvedValue({ user: state.user, session: { id: "s1" } });
    state.renameSessionTitle.mockResolvedValue(true);
  });

  it("saves the name with its whitespace collapsed", async () => {
    expect(await renameSession("s1", "  Laskujen   luokittelu \n")).toEqual({
      ok: true,
      title: "Laskujen luokittelu",
    });
    expect(state.renameSessionTitle).toHaveBeenCalledWith("s1", "Laskujen luokittelu");
    expect(state.revalidatePath).toHaveBeenCalledWith("/", "layout");
    expect(state.audit).toHaveBeenCalledWith(
      "session.rename",
      expect.objectContaining({ outcome: "success" }),
    );
  });

  it("refuses an empty name and one over 80 characters", async () => {
    expect(await renameSession("s1", "   ")).toEqual({ ok: false, error: "invalid" });
    expect(await renameSession("s1", "x".repeat(81))).toEqual({ ok: false, error: "invalid" });
    expect((await renameSession("s1", "x".repeat(80))).ok).toBe(true);
    expect(state.renameSessionTitle).toHaveBeenCalledTimes(1);
  });

  it("renames nothing that is not the caller's own session", async () => {
    state.requireOwnedSession.mockResolvedValueOnce(null);
    expect(await renameSession("not-mine", "Uusi nimi")).toEqual({ ok: false, error: "failed" });
    expect(state.renameSessionTitle).not.toHaveBeenCalled();
  });

  it("says so when the name could not be saved", async () => {
    state.renameSessionTitle.mockResolvedValueOnce(false);
    expect(await renameSession("s1", "Uusi nimi")).toEqual({ ok: false, error: "failed" });
    expect(state.revalidatePath).not.toHaveBeenCalled();
  });
});

describe("removeSession", () => {
  const form = (fields: Record<string, string>) => {
    const data = new FormData();
    for (const [key, value] of Object.entries(fields)) data.set(key, value);
    return data;
  };

  beforeEach(() => {
    state.listSessions.mockResolvedValue([{ id: "s1", title: "Laskut" }]);
    state.deleteSession.mockResolvedValue("deleted");
  });

  it("deletes a session confirmed by its name and reads the sidebar again", async () => {
    expect(await removeSession({ error: null }, form({ sessionId: "s1", confirmation: " Laskut " }))).toEqual({
      error: null,
      deleted: true,
    });
    expect(state.deleteSession).toHaveBeenCalledWith("s1");
    expect(state.revalidatePath).toHaveBeenCalledWith("/", "layout");
  });

  it("leaves the page of a deleted session for the start", async () => {
    await expect(
      removeSession({ error: null }, form({ sessionId: "s1", confirmation: "Laskut", current: "1" })),
    ).rejects.toThrow("REDIRECT /");
    expect(state.deleteSession).toHaveBeenCalledWith("s1");
  });

  it("deletes nothing on a wrong name or another user's session", async () => {
    expect(await removeSession({ error: null }, form({ sessionId: "s1", confirmation: "laskut" }))).toEqual({
      error: "mismatch",
    });
    expect(await removeSession({ error: null }, form({ sessionId: "s2", confirmation: "Laskut" }))).toEqual({
      error: "mismatch",
    });
    expect(state.deleteSession).not.toHaveBeenCalled();
  });

  it("stays on the page when the session could not be deleted", async () => {
    state.deleteSession.mockResolvedValueOnce("busy");
    expect(
      await removeSession({ error: null }, form({ sessionId: "s1", confirmation: "Laskut", current: "1" })),
    ).toEqual({ error: "busy" });
    expect(state.revalidatePath).not.toHaveBeenCalled();
  });
});
