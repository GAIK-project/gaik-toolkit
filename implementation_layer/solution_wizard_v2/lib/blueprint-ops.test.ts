import { afterEach, describe, expect, it, vi } from "vitest";
import {
  OperationRefused,
  postOperations,
  postUndo,
  refusalOf,
  saveRefusal,
  type BlueprintOperation,
} from "@/lib/blueprint-ops";

const BLUEPRINT = { name: "Invoices", description: "", goal: "", steps: [] };

function answer(status: number, body: unknown) {
  return vi.fn(async () => Response.json(body, { status }));
}

afterEach(() => vi.unstubAllGlobals());

describe("postOperations", () => {
  const ops: BlueprintOperation[] = [{ op: "rename_step", step_id: "s1", name: "Read the invoice" }];

  it("sends the base version and the operations to the session's route", async () => {
    const fetchMock = answer(200, {
      session: { id: "abc", active_version: 4, blueprint: BLUEPRINT },
      warnings: ["w"],
      needs_attention: ["steps[0].component"],
      bpmn_changed: true,
    });
    vi.stubGlobal("fetch", fetchMock);

    const result = await postOperations("abc", 3, ops);

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("/api/sessions/abc/blueprint/operations");
    expect(init.method).toBe("POST");
    expect(JSON.parse(String(init.body))).toEqual({ base_version: 3, operations: ops });
    expect(result).toEqual({
      blueprint: BLUEPRINT,
      warnings: ["w"],
      needsAttention: ["steps[0].component"],
      bpmnChanged: true,
      version: 4,
    });
  });

  it("maps 409 changed_elsewhere to OperationRefused", async () => {
    vi.stubGlobal(
      "fetch",
      answer(409, {
        detail: {
          error: "changed_elsewhere",
          message: "The blueprint has changed since this diagram was loaded; reload it and edit again.",
          trace_id: "trace-0000-1111",
        },
      }),
    );

    const err = await postOperations("abc", 3, ops).catch((e: unknown) => e);

    expect(err).toBeInstanceOf(OperationRefused);
    expect(err).toMatchObject({
      status: 409,
      code: "changed_elsewhere",
      message: "The blueprint has changed since this diagram was loaded; reload it and edit again.",
    });
    expect((err as OperationRefused).field).toBeUndefined();
  });

  it("maps 422 invalid_operation to OperationRefused with its field and index", async () => {
    vi.stubGlobal(
      "fetch",
      answer(422, {
        detail: {
          error: "invalid_operation",
          message: "No step s9.",
          field: "operations[0].step_id",
          index: 0,
          code: "not_found",
          trace_id: "trace-0000-1111",
        },
      }),
    );

    const err = await postOperations("abc", 3, ops).catch((e: unknown) => e);

    expect(err).toBeInstanceOf(OperationRefused);
    expect(err).toMatchObject({
      status: 422,
      code: "invalid_operation",
      field: "operations[0].step_id",
      index: 0,
      reason: "not_found",
      message: "No step s9.",
    });
  });

  it("maps the route's own 503 in mock mode to a plain error, not a refusal", async () => {
    vi.stubGlobal("fetch", answer(503, { error: "needs_wizard_api" }));

    const err = await postOperations("abc", 3, ops).catch((e: unknown) => e);

    expect(err).toBeInstanceOf(Error);
    expect(err).not.toBeInstanceOf(OperationRefused);
  });

  it("refuses an answer without a blueprint", async () => {
    vi.stubGlobal("fetch", answer(200, { warnings: [] }));
    await expect(postOperations("abc", 3, ops)).rejects.toThrow();
  });

  it("encodes the session id into the path", async () => {
    const fetchMock = answer(200, {
      session: { active_version: 2, blueprint: BLUEPRINT },
      warnings: [],
      needs_attention: [],
      bpmn_changed: false,
    });
    vi.stubGlobal("fetch", fetchMock);
    await postOperations("a/b", 1, ops);
    expect((fetchMock.mock.calls[0] as unknown as [string])[0]).toBe("/api/sessions/a%2Fb/blueprint/operations");
  });
});

describe("refusalOf", () => {
  it("reads a relayed detail and the route's own flat refusal", () => {
    expect(refusalOf({ detail: { error: "unsupported_edit", message: "Ask the wizard." } })).toEqual({
      code: "unsupported_edit",
      message: "Ask the wizard.",
    });
    expect(refusalOf({ error: "changed_elsewhere" })).toEqual({ code: "changed_elsewhere", message: "" });
  });

  it("reads nothing from a body that is no refusal", () => {
    expect(refusalOf(null)).toBeNull();
    expect(refusalOf("Session not found")).toBeNull();
    expect(refusalOf({ detail: [{ loc: ["body"], msg: "x" }] })).toBeNull();
  });
});

describe("saveRefusal (the form, flow and canvas saves)", () => {
  it("reads changed_elsewhere, from the route itself or relayed from wizard_api", () => {
    expect(saveRefusal(409, { error: "changed_elsewhere" })).toEqual({ kind: "changed" });
    expect(saveRefusal(409, { detail: { error: "changed_elsewhere", message: "reload" } })).toEqual({
      kind: "changed",
    });
  });

  it("gives a 409 or 422 refusal's own message", () => {
    expect(
      saveRefusal(422, { detail: { error: "unsupported_edit", message: "Ask the wizard to change x." } }),
    ).toEqual({ kind: "refused", message: "Ask the wizard to change x." });
    expect(saveRefusal(409, { detail: { error: "agent_busy", message: "The wizard is replying." } })).toEqual({
      kind: "refused",
      message: "The wizard is replying.",
    });
  });

  it("is nothing for a success, another status or a refusal without words", () => {
    expect(saveRefusal(200, { blueprint: {} })).toBeNull();
    expect(saveRefusal(500, { detail: { error: "internal_error", message: "x" } })).toBeNull();
    expect(saveRefusal(422, { detail: [{ loc: ["body"], msg: "x" }] })).toBeNull();
    expect(saveRefusal(422, { detail: { error: "unsupported_edit", message: "" } })).toBeNull();
  });
});

describe("postUndo", () => {
  it("sends the base version to the undo route and gives the blueprint and the new version", async () => {
    const fetchMock = answer(200, { id: "abc", active_version: 6, blueprint: BLUEPRINT });
    vi.stubGlobal("fetch", fetchMock);

    expect(await postUndo("abc", 5)).toEqual({ blueprint: BLUEPRINT, version: 6 });
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("/api/sessions/abc/blueprint/undo");
    expect(init.method).toBe("POST");
    expect(JSON.parse(String(init.body))).toEqual({ base_version: 5 });
  });

  it("throws OperationRefused for nothing_to_undo", async () => {
    vi.stubGlobal(
      "fetch",
      answer(409, { detail: { error: "nothing_to_undo", message: "There is nothing to undo." } }),
    );
    await expect(postUndo("abc", 5)).rejects.toMatchObject({ name: "OperationRefused", code: "nothing_to_undo" });
  });

  it("throws a plain error without wizard_api", async () => {
    vi.stubGlobal("fetch", answer(503, { error: "needs_wizard_api" }));
    await expect(postUndo("abc", 5)).rejects.not.toBeInstanceOf(OperationRefused);
  });
});
