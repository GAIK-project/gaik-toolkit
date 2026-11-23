import { describe, expect, it } from "vitest";
import {
  captionText,
  formatFullLabel,
  humanizeToken,
  iconAccentColor,
  inBoxLabelLines,
  resolveSemanticIcon,
  semanticIconPaths,
  shortenLabel,
  stepCaptionLines,
  taskStrokeColor,
} from "./semantic-icon";

describe("resolveSemanticIcon", () => {
  it("reads a bracketed GAIK component code first, ignoring case/spacing", () => {
    expect(resolveSemanticIcon("[Transcriber] Transcribe audio", "t1")).toBe("audio");
    expect(resolveSemanticIcon("[ LLMJudge ] Validate", "v1")).toBe("validation");
  });

  it("falls back to keyword matching in the name/id when there's no bracket", () => {
    expect(resolveSemanticIcon("Customer photo upload", "p1")).toBe("photo");
    expect(resolveSemanticIcon("Store in database", "d1")).toBe("database");
    expect(resolveSemanticIcon("Human review", "h1")).toBe("human");
  });

  it("uses the BPMN type as a last resort", () => {
    expect(resolveSemanticIcon("Something", "s1", "bpmn:UserTask")).toBe("human");
    expect(resolveSemanticIcon("Something", "s1", "bpmn:ServiceTask")).toBe("ai");
    expect(resolveSemanticIcon("Something", "s1", "bpmn:StartEvent")).toBe("start");
  });

  it("defaults to generic when nothing matches", () => {
    expect(resolveSemanticIcon("Unrelated label", "x1")).toBe("generic");
  });
});

describe("semanticIconPaths / iconAccentColor", () => {
  it("returns a non-empty path list for every icon kind used by resolveSemanticIcon", () => {
    const kinds = [
      "audio", "photo", "transcript", "json", "validation", "approved", "database",
      "ai", "human", "submit", "record", "start", "end", "reject", "gateway", "enhance", "generic",
    ] as const;
    for (const kind of kinds) {
      expect(semanticIconPaths(kind).length).toBeGreaterThan(0);
      expect(iconAccentColor(kind)).toMatch(/^#[0-9a-f]{6}$/i);
    }
  });
});

describe("taskStrokeColor", () => {
  it("differentiates UserTask from ServiceTask/SendTask and the default", () => {
    expect(taskStrokeColor("bpmn:UserTask")).toBe("#e09a52");
    expect(taskStrokeColor("bpmn:ServiceTask")).toBe("#d6b878");
    expect(taskStrokeColor("bpmn:SendTask")).toBe("#d6b878");
    expect(taskStrokeColor(undefined)).toBe("#6fd6c6");
  });
});

describe("label formatting", () => {
  it("formatFullLabel joins trimmed non-empty lines with a middle dot", () => {
    expect(formatFullLabel("Line one\n  \nLine two ")).toBe("Line one · Line two");
  });

  it("inBoxLabelLines drops blank lines and trims each one", () => {
    expect(inBoxLabelLines("  a  \n\n b ")).toEqual(["a", "b"]);
  });

  it("shortenLabel truncates with an ellipsis only past maxLen", () => {
    expect(shortenLabel("Short")).toBe("Short");
    expect(shortenLabel("A very long step name indeed", 10)).toBe("A very lo…");
  });

  it("shortenLabel only looks at the first line", () => {
    expect(shortenLabel("First\nSecond", 20)).toBe("First");
  });

  it("humanizeToken turns snake_case into spaced words", () => {
    expect(humanizeToken("extract_structured_data")).toBe("extract structured data");
  });
});

describe("stepCaptionLines", () => {
  it("preserves existing multi-line names as-is", () => {
    expect(stepCaptionLines("Extract data\n[SE]")).toEqual(["Extract data", "[SE]"]);
  });

  it("adds a role suffix for a single-line human-review UserTask", () => {
    expect(stepCaptionLines("Manager approval", "bpmn:UserTask")).toEqual([
      "Manager approval",
      "[Human review]",
    ]);
  });

  it("adds [User input] for a plain UserTask", () => {
    expect(stepCaptionLines("Customer question", "bpmn:UserTask")).toEqual([
      "Customer question",
      "[User input]",
    ]);
  });

  it("adds [Integration] for a SendTask and [Data store] for a data store", () => {
    expect(stepCaptionLines("Submit", "bpmn:SendTask")).toEqual(["Submit", "[Integration]"]);
    expect(stepCaptionLines("Knowledge base", "bpmn:DataStoreReference")).toEqual([
      "Knowledge base",
      "[Data store]",
    ]);
  });

  it("adds no suffix for types without a role mapping", () => {
    expect(stepCaptionLines("Some gateway", "bpmn:ExclusiveGateway")).toEqual(["Some gateway"]);
  });
});

describe("captionText", () => {
  it("humanizes a short snake_case identifier", () => {
    expect(captionText("extract_data")).toEqual({
      short: "extract data",
      full: "extract data",
    });
  });

  it("uses a wider max length for pools/lanes/gateways/events", () => {
    const pool = captionText("A very long participant pool name here", "bpmn:Participant");
    expect(pool.short.length).toBeLessThanOrEqual(37); // 36 + ellipsis
    const gateway = captionText("Is the answer confident enough to send", "bpmn:ExclusiveGateway");
    expect(gateway.short.length).toBeLessThanOrEqual(13); // 12 + ellipsis
  });
});
