import { beforeEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({
  apiDeleteSession: vi.fn(),
  wizardApiEnabled: vi.fn(() => true),
}));
vi.mock("@/lib/wizard-api-client", () => api);

import { deleteSession } from "@/lib/sessions";

const answer = (status: number, error?: string) =>
  new Response(error ? JSON.stringify({ detail: { error } }) : null, { status });

describe("deleteSession", () => {
  beforeEach(() => api.apiDeleteSession.mockReset());

  it("is done when the api removed the session or it was gone already", async () => {
    api.apiDeleteSession.mockResolvedValueOnce(answer(204));
    expect(await deleteSession("s1")).toBe("deleted");
    api.apiDeleteSession.mockResolvedValueOnce(answer(404));
    expect(await deleteSession("s1")).toBe("deleted");
  });

  it("tells a kept session from one the wizard is working on", async () => {
    api.apiDeleteSession.mockResolvedValueOnce(answer(409, "session_protected"));
    expect(await deleteSession("s1")).toBe("protected");
    api.apiDeleteSession.mockResolvedValueOnce(answer(409, "session_busy"));
    expect(await deleteSession("s1")).toBe("busy");
  });

  it("reports anything else as failed", async () => {
    api.apiDeleteSession.mockResolvedValueOnce(answer(503, "session_delete_failed"));
    expect(await deleteSession("s1")).toBe("failed");
  });
});
