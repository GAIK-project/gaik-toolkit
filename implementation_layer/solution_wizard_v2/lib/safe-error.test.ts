import { describe, expect, it } from "vitest";
import { dictionary } from "@/lib/i18n";
import { MESSAGE_MAX_CHARS, safeErrorDetail, sanitizeSseErrors } from "@/lib/safe-error";

const en = dictionary("en");
const TRACE = "trace-0000-1111";
const LEAK = 'Traceback (most recent call last):\n  File "/srv/wizard/out/poc/run_poc.py", line 3';

describe("safeErrorDetail", () => {
  it("passes a known code with its message and what the person needs to act", () => {
    const detail = safeErrorDetail(
      {
        detail: {
          error: "gate_not_ready",
          gate: "gate_2",
          missing: "the workflow diagram",
          message: "gate_2 cannot be approved yet: the wizard has not produced the workflow diagram.",
          trace_id: "api-trace-1234",
        },
      },
      TRACE,
      en,
    );
    expect(detail).toEqual({
      error: "gate_not_ready",
      gate: "gate_2",
      missing: "the workflow diagram",
      message: "gate_2 cannot be approved yet: the wizard has not produced the workflow diagram.",
      trace_id: "api-trace-1234",
    });
  });

  it("keeps the sandbox_busy code and the package's problems", () => {
    expect(
      safeErrorDetail({ detail: { error: "sandbox_busy", message: "the sandbox is busy" } }, TRACE, en),
    ).toMatchObject({ error: "sandbox_busy", message: "the sandbox is busy" });
    expect(
      safeErrorDetail(
        { detail: { error: "poc_package_incomplete", message: "x", problems: ["README.md is missing"] } },
        TRACE,
        en,
      ).problems,
    ).toEqual(["README.md is missing"]);
  });

  it("drops the keys a known refusal has that are not on the list", () => {
    const detail = safeErrorDetail(
      { detail: { error: "case_state", message: "the case is approved", path: "/srv/x", errors: [LEAK] } },
      TRACE,
      en,
    );
    expect(Object.keys(detail).sort()).toEqual(["error", "message", "trace_id"]);
  });

  it("turns an unknown code, a plain string or a FastAPI list into the generic message", () => {
    const bodies: unknown[] = [
      { detail: { error: "weird", message: LEAK } },
      { detail: LEAK },
      { detail: [{ loc: ["body", "x"], msg: "field required", input: LEAK }] },
      { detail: { message: LEAK } },
      "<html>502 Bad Gateway</html>",
      null,
    ];
    for (const body of bodies) {
      const detail = safeErrorDetail(body, TRACE, en);
      expect(detail.error).toBe("internal_error");
      expect(detail.message).toBe(en.errorGeneric.replace("{trace}", TRACE));
      expect(JSON.stringify(detail)).not.toContain("/srv/wizard");
      expect(JSON.stringify(detail)).not.toContain("Traceback");
    }
  });

  it("keeps an internal code but says only our own words", () => {
    const detail = safeErrorDetail(
      { detail: { error: "sandbox_unavailable", message: "set WIZARD_SANDBOX_NAMESPACE" } },
      TRACE,
      en,
    );
    expect(detail.error).toBe("sandbox_unavailable");
    expect(detail.message).toBe(en.errorSandboxUnavailable.replace("{trace}", TRACE));
  });

  it("does not take a trace id that is not one", () => {
    const detail = safeErrorDetail(
      { detail: { error: "not_found", message: "session not found", trace_id: "<b>x</b>" } },
      TRACE,
      en,
    );
    expect(detail.trace_id).toBe(TRACE);
  });

  it("flattens and shortens a known message", () => {
    const detail = safeErrorDetail(
      { detail: { error: "input_rejected", message: `a\n b ${"x".repeat(1000)}` } },
      TRACE,
      en,
    );
    expect(detail.message.startsWith("a b ")).toBe(true);
    expect(detail.message.length).toBe(MESSAGE_MAX_CHARS);
  });
});

async function readAll(stream: ReadableStream<Uint8Array>): Promise<string> {
  return new Response(stream).text();
}

function streamOf(...chunks: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  return new ReadableStream({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk));
      controller.close();
    },
  });
}

describe("sanitizeSseErrors", () => {
  it("passes log and done frames as they came, split across chunks", async () => {
    const frames =
      'data: {"log": "Traceback (most recent call last):"}\n\n' +
      'data: {"heartbeat": true}\n\n' +
      'data: {"done": true, "phase": "failed", "reason": "ValueError: x"}\n\n';
    const out = await readAll(
      sanitizeSseErrors(streamOf(frames.slice(0, 17), frames.slice(17)), TRACE, en),
    );
    expect(out).toBe(frames);
  });

  it("rewrites an error frame with a raw message to the generic one", async () => {
    const out = await readAll(
      sanitizeSseErrors(
        streamOf(`data: ${JSON.stringify({ error: true, message: LEAK })}\n\n`),
        TRACE,
        en,
      ),
    );
    expect(out).not.toContain("/srv/wizard");
    const evt = JSON.parse(out.slice(6));
    expect(evt).toEqual({
      error: true,
      code: "internal_error",
      message: en.errorGeneric.replace("{trace}", TRACE),
      trace_id: TRACE,
    });
  });

  it("keeps a known code's error frame", async () => {
    const frame = { error: true, code: "agent_capacity", message: "busy", trace_id: "api-trace-1234" };
    const out = await readAll(sanitizeSseErrors(streamOf(`data: ${JSON.stringify(frame)}\n\n`), TRACE, en));
    expect(JSON.parse(out.slice(6))).toEqual(frame);
  });
});
