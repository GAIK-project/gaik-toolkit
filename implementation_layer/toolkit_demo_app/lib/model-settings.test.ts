import { afterEach, expect, test } from "bun:test";
import { apiFetch } from "./api-client";
import { setModelSettings, getModelSettings } from "./model-settings-store";
import { setReasoningEffort } from "./server-model-store";
import {
  MODEL_SETTINGS_HEADER,
  REASONING_EFFORT_HEADER,
  isReasoningEffort,
  normalizeAzureEndpoint,
  parseModelSettingsHeader,
  reasoningEffortFor,
  supportsModelSettings,
  takesReasoningEffort,
} from "./model-settings";

const originalFetch = globalThis.fetch;
const originalWindow = globalThis.window;
afterEach(() => {
  setModelSettings(null);
  setReasoningEffort(null);
  globalThis.fetch = originalFetch;
  globalThis.window = originalWindow;
});

test("settings only apply to supported POST operations", () => {
  expect(supportsModelSettings("/api/extract")).toBe(true);
  expect(supportsModelSettings("/api/extract/plain-language")).toBe(true);
  expect(supportsModelSettings("/api/extract-vision")).toBe(true);
  expect(supportsModelSettings("/api/llm-judge/panel/text-pair")).toBe(false);
  expect(supportsModelSettings("/api/wizard/message/abc")).toBe(false);
  expect(supportsModelSettings("/api/wizard/start")).toBe(false);
  expect(supportsModelSettings("/api/extract", "GET")).toBe(false);
  expect(supportsModelSettings("/api/pipeline/text/stream")).toBe(true);
  expect(supportsModelSettings("/api/pipeline/schema")).toBe(true);
  // Other demos share /api/pipeline but are not part of this.
  expect(supportsModelSettings("/api/pipeline/audio")).toBe(false);
  expect(supportsModelSettings("/api/pipeline/pdf/abc")).toBe(false);
  expect(supportsModelSettings("/api/report-writer/run")).toBe(false);
});

test("Azure URL validation blocks redirects to arbitrary hosts", () => {
  expect(
    normalizeAzureEndpoint("https://resource.services.ai.azure.com/openai/v1/"),
  ).toBe("https://resource.services.ai.azure.com");
  for (const url of [
    "http://resource.openai.azure.com",
    "https://localhost",
    "https://resource.openai.azure.com.attacker.example",
    "https://resource.openai.azure.com:8443",
    "https://user:key@resource.openai.azure.com",
    "https://resource.openai.azure.com/?x=y",
  ]) {
    expect(() => normalizeAzureEndpoint(url)).toThrow();
  }
});

test("invalid submitted keys never appear in validation errors", () => {
  const raw = JSON.stringify({
    provider: "invalid",
    model: "x",
    apiKey: "secret-do-not-echo",
  });
  try {
    parseModelSettingsHeader(raw);
  } catch (error) {
    expect(String(error)).not.toContain("secret-do-not-echo");
  }
});

test("apiFetch attaches keys only to same-origin supported requests", async () => {
  globalThis.window = {
    location: { origin: "https://demo.example" },
  } as Window & typeof globalThis;
  const observed: Headers[] = [];
  const redirects: (RequestRedirect | undefined)[] = [];
  globalThis.fetch = (async (_input: unknown, init?: RequestInit) => {
    observed.push(new Headers(init?.headers));
    redirects.push(init?.redirect);
    return new Response("{}", { status: 200 });
  }) as typeof fetch;
  setModelSettings({
    provider: "aitta",
    model: "test-model",
    apiKey: "test-key",
  });
  await apiFetch("/api/extract", { method: "POST" });
  await apiFetch("https://other.example/api/extract", { method: "POST" });
  await apiFetch("/api/extract", { method: "GET" });
  await apiFetch("/api/rag/index", { method: "POST" });
  expect(observed[0].get(MODEL_SETTINGS_HEADER)).toContain("test-key");
  expect(redirects[0]).toBe("error");
  for (const headers of observed.slice(1))
    expect(headers.has(MODEL_SETTINGS_HEADER)).toBe(false);
  setModelSettings(null);
  expect(getModelSettings()).toBeNull();
});

test("only GPT-6 models on OpenAI or Azure take a reasoning effort", () => {
  for (const model of ["gpt-6-sol", "gpt-6-luna", "gpt-6.2-sol", "GPT-6-Astra"])
    for (const provider of ["openai", "azure"])
      expect(takesReasoningEffort(provider, model)).toBe(true);
  expect(takesReasoningEffort("openai", "gpt-5.6-terra")).toBe(false);
  expect(takesReasoningEffort("azure", "my-deployment")).toBe(false);
  expect(takesReasoningEffort("anthropic_foundry", "claude-sonnet-5-5")).toBe(
    false,
  );
  expect(takesReasoningEffort("vertex", "gemini-3.8-flash")).toBe(false);
  expect(takesReasoningEffort("aitta", "openai/gpt-oss-120b")).toBe(false);
  expect(takesReasoningEffort("aitta", "gpt-6-sol")).toBe(false);
});

test("an effort is low, medium or high, and nothing else", () => {
  for (const value of ["low", "medium", "high"])
    expect(isReasoningEffort(value)).toBe(true);
  for (const value of ["none", "auto", "minimal", "High", "", null, undefined])
    expect(isReasoningEffort(value)).toBe(false);
});

test("a request carries the picked effort only for a model that takes it", () => {
  const gpt = { provider: "azure", model: "gpt-6.2-sol" };
  const claude = { provider: "anthropic_foundry", model: "claude-sonnet-5-5" };
  expect(reasoningEffortFor("high", gpt)).toBe("high");
  expect(reasoningEffortFor(null, gpt)).toBeNull();
  expect(reasoningEffortFor("high", claude)).toBeNull();
  // The model list has not loaded: the API decides.
  expect(reasoningEffortFor("low", null)).toBe("low");
  expect(reasoningEffortFor("none" as "low", gpt)).toBeNull();
});

test("apiFetch sends the effort with the model, and nothing for Auto", async () => {
  globalThis.window = {
    location: { origin: "https://demo.example" },
  } as Window & typeof globalThis;
  const observed: Headers[] = [];
  globalThis.fetch = (async (_input: unknown, init?: RequestInit) => {
    observed.push(new Headers(init?.headers));
    return new Response("{}", { status: 200 });
  }) as typeof fetch;
  const effortOf = async (url: string, method = "POST") => {
    await apiFetch(url, { method });
    return observed.at(-1)?.get(REASONING_EFFORT_HEADER) ?? null;
  };

  // Auto is the default: no header.
  expect(await effortOf("/api/extract")).toBeNull();

  setReasoningEffort("high");
  expect(await effortOf("/api/extract")).toBe("high");
  // Never on a route that takes no picked model, a GET or another origin.
  expect(await effortOf("/api/tabular-agent/ask")).toBeNull();
  expect(await effortOf("/api/extract", "GET")).toBeNull();
  expect(await effortOf("https://other.example/api/extract")).toBeNull();

  // An own key: a GPT-6 model takes it, an Aitta model does not.
  setModelSettings({ provider: "openai", model: "gpt-6-sol", apiKey: "k" });
  expect(await effortOf("/api/extract")).toBe("high");
  setModelSettings({ provider: "aitta", model: "test-model", apiKey: "k" });
  expect(await effortOf("/api/extract")).toBeNull();
  setModelSettings(null);

  setReasoningEffort(null);
  expect(await effortOf("/api/extract")).toBeNull();
});
