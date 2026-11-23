import { describe, expect, it } from "vitest";
import { AI_FRONT_MATTER, AI_GENERATOR, AI_RECORD_MARK, aiHeaders, aiModel } from "@/lib/ai-marking";
import { toCsv } from "@/lib/case-process";

describe("marks on downloads", () => {
  it("passes on what the api set and nothing else", () => {
    const upstream = new Response(null, {
      headers: { "X-AI-Generated": "true", "X-AI-Model": "m1", "X-Other": "x" },
    });
    expect(aiHeaders(upstream)).toEqual({ "X-AI-Generated": "true", "X-AI-Model": "m1" });
    expect(aiModel(upstream)).toBe("m1");
  });

  it("adds no header the api did not send", () => {
    expect(aiHeaders(new Response(null))).toEqual({});
    expect(aiModel(new Response(null))).toBeUndefined();
  });
});

describe("marks on case exports", () => {
  it("reach the CSV as columns", () => {
    const csv = toCsv({ total: 5, ...AI_RECORD_MARK });
    expect(csv).toContain('"ai_generated"');
    expect(csv).toContain('"true"');
    expect(csv).toContain(AI_GENERATOR);
  });

  it("open a Markdown export as front matter", () => {
    expect(AI_FRONT_MATTER.startsWith("---\nai_generated: true\n")).toBe(true);
    expect(AI_FRONT_MATTER.endsWith("---\n\n")).toBe(true);
  });
});
