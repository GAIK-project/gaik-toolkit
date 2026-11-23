import { describe, expect, it, vi } from "vitest";

const headersMock = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock("next/headers", () => ({
  headers: async () => headersMock,
}));

import { actorId } from "@/lib/actor-id";
import {
  TRACE_HEADER,
  getContext,
  getTraceId,
  getIncomingTraceId,
  newTraceId,
  runWithContext,
  setContextUserId,
} from "@/lib/request-context";

describe("newTraceId", () => {
  it("returns a fresh uuid-shaped string each time", () => {
    const a = newTraceId();
    const b = newTraceId();
    expect(a).not.toBe(b);
    expect(a).toMatch(/^[0-9a-f-]{36}$/);
  });
});

describe("runWithContext / getContext / getTraceId", () => {
  it("has no context outside a run", () => {
    expect(getContext()).toBeUndefined();
    expect(getTraceId()).toBeUndefined();
  });

  it("makes the context visible for the duration of the callback", () => {
    runWithContext({ traceId: "t-1" }, () => {
      expect(getTraceId()).toBe("t-1");
      expect(getContext()).toEqual({ traceId: "t-1" });
    });
    // Context does not leak out.
    expect(getTraceId()).toBeUndefined();
  });

  it("isolates concurrent async contexts from each other", async () => {
    const results: string[] = [];
    await Promise.all([
      runWithContext({ traceId: "a" }, async () => {
        await new Promise((r) => setTimeout(r, 10));
        results.push(getTraceId()!);
      }),
      runWithContext({ traceId: "b" }, async () => {
        results.push(getTraceId()!);
      }),
    ]);
    expect(results.sort()).toEqual(["a", "b"]);
  });
});

describe("setContextUserId", () => {
  it("attaches the user's pseudonym, not the e-mail, to the active context", () => {
    runWithContext({ traceId: "t-1" }, () => {
      setContextUserId("dev@gaik.local");
      expect(getContext()).toEqual({ traceId: "t-1", userId: actorId("dev@gaik.local") });
      expect(getContext()?.userId).not.toContain("@");
    });
  });

  it("is a no-op outside a context (never throws)", () => {
    expect(() => setContextUserId("dev@gaik.local")).not.toThrow();
  });
});

describe("getIncomingTraceId", () => {
  it("reads the trace header from the incoming request when present", async () => {
    headersMock.get.mockReturnValue("incoming-trace-id");
    expect(await getIncomingTraceId()).toBe("incoming-trace-id");
    expect(headersMock.get).toHaveBeenCalledWith(TRACE_HEADER);
  });

  it("generates a fresh id when the header is missing", async () => {
    headersMock.get.mockReturnValue(null);
    const id = await getIncomingTraceId();
    expect(id).toMatch(/^[0-9a-f-]{36}$/);
  });

  it("generates a fresh id instead of throwing when called outside a request scope", async () => {
    headersMock.get.mockImplementation(() => {
      throw new Error("headers() called outside a request scope");
    });
    const id = await getIncomingTraceId();
    expect(id).toMatch(/^[0-9a-f-]{36}$/);
  });
});
