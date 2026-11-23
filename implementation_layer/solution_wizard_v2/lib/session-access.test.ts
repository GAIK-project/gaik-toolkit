import { beforeEach, describe, expect, it, vi } from "vitest";
import type { WizardSession } from "@/lib/mock-sessions";

const currentUserMock = vi.hoisted(() => ({ getCurrentUser: vi.fn() }));
vi.mock("@/lib/current-user", () => currentUserMock);

// The mock store's rule: a session is owned by the address (`sessionOwnerFor`);
// against wizard_api it is the owner id, covered in sessions.test.ts.
const sessionsMock = vi.hoisted(() => ({
  getSession: vi.fn(),
  claimLegacySessions: vi.fn(),
  sessionOwnerFor: (email: string) => `owner:${email}`,
}));
vi.mock("@/lib/sessions", () => sessionsMock);

import { getSessionForUser, requireOwnedSession } from "@/lib/session-access";

const session = { id: "s1", userId: "owner:owner@gaik.local" } as unknown as WizardSession;

beforeEach(() => {
  vi.clearAllMocks();
});

describe("getSessionForUser", () => {
  it("returns undefined when the session does not exist", async () => {
    sessionsMock.getSession.mockResolvedValue(undefined);
    expect(await getSessionForUser("s1", "owner@gaik.local")).toBeUndefined();
  });

  it("returns undefined when the session belongs to someone else", async () => {
    sessionsMock.getSession.mockResolvedValue(session);
    expect(await getSessionForUser("s1", "someone-else@gaik.local")).toBeUndefined();
  });

  it("returns the session when the caller owns it, after moving their old sessions", async () => {
    sessionsMock.getSession.mockResolvedValue(session);
    expect(await getSessionForUser("s1", "owner@gaik.local")).toBe(session);
    expect(sessionsMock.claimLegacySessions).toHaveBeenCalledWith("owner@gaik.local");
  });
});

describe("requireOwnedSession", () => {
  it("returns null when there is no signed-in user", async () => {
    currentUserMock.getCurrentUser.mockResolvedValue(null);
    expect(await requireOwnedSession("s1")).toBeNull();
    expect(sessionsMock.getSession).not.toHaveBeenCalled();
  });

  it("returns null when the signed-in user does not own the session", async () => {
    currentUserMock.getCurrentUser.mockResolvedValue({ email: "someone-else@gaik.local" });
    sessionsMock.getSession.mockResolvedValue(session);
    expect(await requireOwnedSession("s1")).toBeNull();
  });

  it("returns the user + session when ownership checks out", async () => {
    currentUserMock.getCurrentUser.mockResolvedValue({ email: "owner@gaik.local" });
    sessionsMock.getSession.mockResolvedValue(session);
    const result = await requireOwnedSession("s1");
    expect(result).toEqual({ user: { email: "owner@gaik.local" }, session });
  });
});
