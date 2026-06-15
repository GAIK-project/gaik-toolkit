import { expect, test } from "bun:test";
import { extractReportUsage } from "./usage";

test("returns sawResult=false when no result event present", () => {
  const sse = 'event: progress\ndata: {"message":"working"}\n\n';
  expect(extractReportUsage(sse)).toEqual({ sawResult: false, totalTokens: 0 });
});

test("extracts total_tokens from a result event", () => {
  const sse =
    'event: progress\ndata: {"message":"x"}\n\n' +
    'event: result\ndata: {"markdown":"# R","sections":[],"usage":{"total_tokens":1234},"docx_b64":null}\n\n';
  expect(extractReportUsage(sse)).toEqual({ sawResult: true, totalTokens: 1234 });
});

test("result without usage counts as a run with 0 tokens", () => {
  const sse =
    'event: result\ndata: {"markdown":"# R","sections":[],"usage":{},"docx_b64":null}\n\n';
  expect(extractReportUsage(sse)).toEqual({ sawResult: true, totalTokens: 0 });
});
