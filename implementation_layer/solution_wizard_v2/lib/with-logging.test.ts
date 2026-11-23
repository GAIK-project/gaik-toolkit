import { beforeEach, describe, expect, it, vi } from "vitest";
import type { NextRequest } from "next/server";

const childLog = vi.hoisted(() => ({
  debug: vi.fn(),
  info: vi.fn(),
  warn: vi.fn(),
  error: vi.fn(),
}));
const loggerMock = vi.hoisted(() => ({ child: vi.fn(() => childLog), warn: vi.fn() }));
vi.mock("@/lib/logger", () => ({ logger: loggerMock }));

// request-context is left un-mocked on purpose — the whole point of this
// wrapper is that it actually establishes a real AsyncLocalStorage context.
import { getContext } from "@/lib/request-context";
import { withLogging } from "@/lib/with-logging";

function fakeRequest(overrides: { traceId?: string } = {}) {
  return {
    method: "POST",
    headers: { get: (name: string) => (name === "x-trace-id" ? overrides.traceId ?? null : null) },
    nextUrl: { pathname: "/api/sessions/s1/blueprint" },
  } as unknown as NextRequest;
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("withLogging", () => {
  it("uses the incoming x-trace-id and echoes it on the response", async () => {
    const handler = withLogging("blueprint.patch", async (_req: unknown) => Response.json({ ok: true }));
    const res = await handler(fakeRequest({ traceId: "trace-abc" }));
    expect(res.headers.get("x-trace-id")).toBe("trace-abc");
    expect(loggerMock.child).toHaveBeenCalledWith(
      expect.objectContaining({ traceId: "trace-abc", event: "blueprint.patch" }),
    );
  });

  it("generates a fresh traceId when the request has none", async () => {
    const handler = withLogging("blueprint.patch", async (_req: unknown) => Response.json({ ok: true }));
    const res = await handler(fakeRequest());
    expect(res.headers.get("x-trace-id")).toMatch(/^[0-9a-f-]{36}$/);
  });

  it("makes the handler's own context (e.g. userId) visible during the call", async () => {
    let sawUserId: string | undefined;
    const handler = withLogging("blueprint.patch", async (_req: unknown) => {
      const { setContextUserId } = await import("@/lib/request-context");
      setContextUserId("dev@gaik.local");
      sawUserId = getContext()?.userId;
      return Response.json({ ok: true });
    });
    await handler(fakeRequest());
    const { actorId } = await import("@/lib/actor-id");
    expect(sawUserId).toBe(actorId("dev@gaik.local"));
  });

  it("logs request.end at info for a 2xx response, with status and duration", async () => {
    const handler = withLogging("poc.generate", async (_req: unknown) => Response.json({ ok: true }, { status: 200 }));
    await handler(fakeRequest());
    expect(childLog.info).toHaveBeenCalledWith(
      expect.objectContaining({ httpStatus: 200, durationMs: expect.any(Number) }),
      "request.end",
    );
  });

  it("logs request.end at warn for a 4xx response", async () => {
    const handler = withLogging("blueprint.patch", async (_req: unknown) => new Response("bad", { status: 404 }));
    await handler(fakeRequest());
    expect(childLog.warn).toHaveBeenCalledWith(
      expect.objectContaining({ httpStatus: 404 }),
      "request.end",
    );
  });

  it("logs request.end at error for a 5xx response returned by the handler", async () => {
    const handler = withLogging("bpmn.sync", async (_req: unknown) => new Response("boom", { status: 500 }));
    await handler(fakeRequest());
    expect(childLog.error).toHaveBeenCalledWith(
      expect.objectContaining({ httpStatus: 500 }),
      "request.end",
    );
  });

  it("catches a thrown error, logs it, and returns a 500 without leaking the error to the caller", async () => {
    const handler = withLogging("bpmn.sync", async (_req: unknown): Promise<Response> => {
      throw new Error("unexpected");
    });
    const res = await handler(fakeRequest({ traceId: "trace-err" }));
    expect(res.status).toBe(500);
    expect(res.headers.get("x-trace-id")).toBe("trace-err");
    expect(await res.text()).not.toContain("unexpected");
    expect(childLog.error).toHaveBeenCalledWith(
      expect.objectContaining({ err: expect.any(Error) }),
      "request.error",
    );
  });

  it("passes through all handler arguments unchanged (e.g. the route's params promise)", async () => {
    const handler = withLogging(
      "blueprint.patch",
      async (_req: unknown, ctx: { params: Promise<{ id: string }> }) => {
        const { id } = await ctx.params;
        return Response.json({ id });
      },
    );
    const res = await handler(fakeRequest(), { params: Promise.resolve({ id: "s1" }) });
    expect(await res.json()).toEqual({ id: "s1" });
  });
});
