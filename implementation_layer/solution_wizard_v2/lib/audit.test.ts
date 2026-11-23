import { describe, expect, it, vi } from "vitest";

const loggerMock = vi.hoisted(() => ({ info: vi.fn(), warn: vi.fn() }));
vi.mock("@/lib/logger", () => ({ logger: loggerMock }));

const traceIdMock = vi.hoisted(() => ({ value: undefined as string | undefined }));
vi.mock("@/lib/request-context", () => ({
  getTraceId: () => traceIdMock.value,
}));

import { actorId } from "@/lib/actor-id";
import { audit } from "@/lib/audit";

describe("audit", () => {
  it("logs a tagged, structured audit record via logger.info", () => {
    audit("session.create", {
      actor: "dev@gaik.local",
      resource: { type: "session", id: "s1" },
      outcome: "success",
    });
    expect(loggerMock.info).toHaveBeenCalledWith(
      expect.objectContaining({
        type: "audit",
        event: "session.create",
        actor: actorId("dev@gaik.local"),
        resource: { type: "session", id: "s1" },
        outcome: "success",
      }),
      "audit.session.create",
    );
  });

  it("writes the actor's pseudonym, never the e-mail address", () => {
    audit("session.create", { actor: "dev@gaik.local", outcome: "success" });
    const record = loggerMock.info.mock.calls.at(-1)?.[0] as Record<string, unknown>;
    expect(record.actor).toMatch(/^u_[0-9a-f]{16}$/);
    expect(JSON.stringify(record)).not.toContain("dev@gaik.local");
  });

  it("leaves actor out when the caller has none", () => {
    audit("poc.generate", { outcome: "error" });
    const record = loggerMock.info.mock.calls.at(-1)?.[0] as Record<string, unknown>;
    expect(record).not.toHaveProperty("actor");
  });

  it("falls back to the ambient request traceId when none is passed explicitly", () => {
    traceIdMock.value = "ambient-trace";
    audit("auth.login", { actor: "dev@gaik.local", outcome: "success" });
    expect(loggerMock.info).toHaveBeenCalledWith(
      expect.objectContaining({ traceId: "ambient-trace" }),
      expect.any(String),
    );
    traceIdMock.value = undefined;
  });

  it("prefers an explicitly passed traceId over the ambient one", () => {
    traceIdMock.value = "ambient-trace";
    audit("auth.login", { actor: "dev@gaik.local", outcome: "success", traceId: "explicit" });
    expect(loggerMock.info).toHaveBeenCalledWith(
      expect.objectContaining({ traceId: "explicit" }),
      expect.any(String),
    );
    traceIdMock.value = undefined;
  });

  it("passes through extra fields (e.g. reason) without dropping them", () => {
    audit("bpmn.sync", { actor: "dev@gaik.local", outcome: "denied", reason: "lint_failed" });
    expect(loggerMock.info).toHaveBeenCalledWith(
      expect.objectContaining({ reason: "lint_failed" }),
      expect.any(String),
    );
  });
});
