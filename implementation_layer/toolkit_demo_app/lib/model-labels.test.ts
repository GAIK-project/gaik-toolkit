import { describe, expect, test } from "bun:test";
import { modelLabel, runSummary } from "./model-labels";

describe("modelLabel", () => {
  test("names the models the demo runs", () => {
    expect(modelLabel("gpt-6-luna")).toBe("GPT-6 Luna");
    expect(modelLabel("gpt-6.1-sol")).toBe("GPT-6.1 Sol");
    expect(modelLabel("gpt-5.4-mini")).toBe("GPT-5.4 Mini");
    expect(modelLabel("claude-haiku-5-5")).toBe("Claude Haiku 5.5");
    expect(modelLabel("gemini-3.8-flash")).toBe("Gemini 3.8 Flash");
    expect(modelLabel("google/gemma-4-31b-it")).toBe("Gemma 4 31b It");
    expect(modelLabel("whisper_local")).toBe("Whisper on GAIK's server");
    expect(modelLabel("gpt-4o-transcribe")).toBe("GPT-4o Transcribe");
    expect(modelLabel(null)).toBeNull();
  });
});

describe("runSummary", () => {
  test("says what transcribed and what extracted", () => {
    expect(
      runSummary(13, {
        transcription_model: "whisper_local",
        extraction_model: "claude-haiku-5-5",
      }),
    ).toBe(
      "in 13.0 s, transcribed by Whisper on GAIK's server, extracted by Claude Haiku 5.5",
    );
    expect(runSummary(null, { extraction_model: "gpt-6-luna" })).toBe(
      "extracted by GPT-6 Luna",
    );
    expect(runSummary(null, {})).toBeNull();
  });
});
