import { describe, expect, test } from "bun:test";
import { existsSync } from "node:fs";
import path from "node:path";
import {
  DIALECT_AVERAGES,
  DIALECT_CLIPS,
  DIALECT_MODELS,
  clipAudio,
  clipWer,
} from "./dialect-data";

describe("the dialect comparison data", () => {
  test("every clip has every model's text and its audio", () => {
    expect(DIALECT_CLIPS.length).toBe(6);
    for (const clip of DIALECT_CLIPS) {
      expect(clip.reference.length).toBeGreaterThan(0);
      for (const model of DIALECT_MODELS) {
        expect(clip.results[model.id].refWords).toBeGreaterThan(0);
      }
      expect(existsSync(path.join("public", clipAudio(clip)))).toBe(true);
    }
  });

  test("every model has its average over the 600 test clips", () => {
    for (const model of DIALECT_MODELS) {
      expect(DIALECT_AVERAGES[model.id].segments).toBe(600);
    }
  });

  test("a clip's rate is its errors per hundred reference words", () => {
    expect(clipWer({ words: [], errors: 3, refWords: 19 })).toBe(16);
    expect(clipWer({ words: [], errors: 0, refWords: 0 })).toBe(0);
  });
});
