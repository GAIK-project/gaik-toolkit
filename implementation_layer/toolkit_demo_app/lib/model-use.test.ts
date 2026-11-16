import { describe, expect, test } from "bun:test";
import { supportsModelSettings, supportsServerModel } from "./model-settings";
import {
  aittaName,
  aittaReadsImages,
  modelUse,
  type ActiveModel,
} from "./model-use";

const luna: ActiveModel = {
  own: false,
  provider: "azure",
  model: "gpt-6-luna",
  label: "GPT-6 Luna",
  vision: true,
  audio: true,
  isDefault: true,
};
const gemma: ActiveModel = {
  own: false,
  provider: "aitta",
  model: "google/gemma-4-31b-it",
  label: "Gemma 4 31B",
  vision: true,
  audio: true,
  isDefault: false,
};
const gptOss: ActiveModel = { ...gemma, label: "gpt-oss 120B", vision: false };
const claude: ActiveModel = {
  own: false,
  provider: "anthropic_foundry",
  model: "claude-haiku-5-5",
  label: "Claude Haiku 5.5",
  vision: true,
  audio: false,
  isDefault: false,
};
const ownAitta: ActiveModel = { ...gemma, own: true };

describe("modelUse", () => {
  test("an Aitta model keeps speech and embeddings on Aitta", () => {
    const audio = modelUse("/audio-structured", gemma);
    expect(audio.runsHere).toBe(true);
    expect(audio.summary).toBe("Gemma 4 31B runs this demo.");
    expect(audio.details).toEqual([
      "Recordings are transcribed by Whisper large v3 on CSC Aitta.",
    ]);
    expect(modelUse("/rag", gemma).details).toEqual([
      "Embeddings come from multilingual-e5-large on CSC Aitta.",
      "A collection keeps the models it was built with: load the documents again after switching.",
    ]);
    expect(modelUse("/transcriber", gemma).summary).toBe(
      "Whisper large v3 on CSC Aitta transcribes here.",
    );
  });

  test("an idle Aitta helper model is announced", () => {
    const idle = {
      ...gemma,
      aittaSpeech: { model: "openai/whisper-large-v3-turbo", idle: true },
      aittaEmbedding: { model: "intfloat/multilingual-e5-large", idle: false },
    };
    expect(modelUse("/audio-structured", idle).details).toEqual([
      "Recordings are transcribed by Whisper large v3 turbo on CSC Aitta. It is idle now: the first recording starts it, which can take minutes.",
    ]);
    expect(modelUse("/transcriber", idle).details).toEqual([
      "It is idle now: the first recording starts it, which can take minutes.",
    ]);
    expect(modelUse("/rag", idle).details[0]).toBe(
      "Embeddings come from multilingual-e5-large on CSC Aitta.",
    );
    expect(aittaName("some/new-speech-model")).toBe(
      "New Speech Model on CSC Aitta",
    );
  });

  test("a text-only model is a problem only where images are sent", () => {
    expect(modelUse("/extractor", gptOss).problem).toBeNull();
    expect(modelUse("/vision-extractor", gptOss).problem).toContain(
      "sends pages as images",
    );
    expect(modelUse("/parser", gptOss).problem).toContain("Text works here");
  });

  test("a demo that ignores the pick says so", () => {
    const tts = modelUse("/text-to-speech", gemma);
    expect(tts.runsHere).toBe(false);
    expect(tts.summary).toBe(
      "This demo runs on the server's own model, not Gemma 4 31B.",
    );
    // Claude has no embeddings, so RAG stays on the default.
    expect(modelUse("/rag", claude).runsHere).toBe(false);
    // A collection outlives the team check, so a team model never builds one.
    expect(modelUse("/rag", { ...gemma, teamOnly: true }).runsHere).toBe(false);
    expect(modelUse("/transcriber", luna).runsHere).toBe(false);
    expect(modelUse("/text-to-speech", luna).summary).toBe(
      "This demo runs on the server's own model.",
    );
  });

  test("an own key does not reach the server-model-only pages", () => {
    expect(modelUse("/rag", ownAitta).runsHere).toBe(false);
    expect(modelUse("/transcriber", ownAitta).summary).toContain(
      "Your key is not used here",
    );
    const audio = modelUse("/audio-structured", ownAitta);
    expect(audio.summary).toBe("Your own model runs this demo: Gemma 4 31B.");
    expect(audio.details).toHaveLength(1);
  });

  test("a model without speech-to-text is transcribed for", () => {
    expect(modelUse("/diary", claude).details).toEqual([
      "Recordings are transcribed on the server first.",
    ]);
    expect(modelUse("/diary", luna).details).toEqual([]);
  });
});

test("known text-only Aitta models", () => {
  expect(aittaReadsImages("openai/gpt-oss-120b")).toBe(false);
  expect(aittaReadsImages("Qwen/Qwen3-Coder-Next")).toBe(false);
  expect(aittaReadsImages("google/gemma-4-31b-it")).toBe(true);
  expect(aittaReadsImages("Qwen/Qwen3.8-27B")).toBe(true);
});

test("a picked server model reaches RAG and the transcriber; an own key does not", () => {
  for (const path of [
    "/api/rag/index",
    "/api/rag/load-example",
    "/api/transcribe",
  ]) {
    expect(supportsServerModel(path)).toBe(true);
    expect(supportsModelSettings(path)).toBe(false);
  }
  expect(supportsServerModel("/api/extract")).toBe(true);
  expect(supportsServerModel("/api/rag/query/stream")).toBe(false);
  expect(supportsServerModel("/api/rag/index", "GET")).toBe(false);
  expect(supportsServerModel("/api/text-to-speech")).toBe(false);
});
