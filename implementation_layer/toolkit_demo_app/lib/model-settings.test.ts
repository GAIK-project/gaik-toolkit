import { afterEach, expect, test } from "bun:test";
import { apiFetch } from "./api-client";
import { setModelSettings, getModelSettings } from "./model-settings-store";
import {
  MODEL_SETTINGS_HEADER,
  normalizeAzureEndpoint,
  parseModelSettingsHeader,
  supportsModelSettings,
} from "./model-settings";

const originalFetch = globalThis.fetch;
const originalWindow = globalThis.window;
afterEach(() => {
  setModelSettings(null);
  globalThis.fetch = originalFetch;
  globalThis.window = originalWindow;
});

test("settings only apply to supported POST operations", () => {
  expect(supportsModelSettings("/api/extract")).toBe(true);
  expect(supportsModelSettings("/api/extract/plain-language")).toBe(true);
  expect(supportsModelSettings("/api/extract-vision")).toBe(true);
  expect(supportsModelSettings("/api/llm-judge/panel/text-pair")).toBe(false);
  expect(supportsModelSettings("/api/wizard/message/abc")).toBe(true);
  expect(supportsModelSettings("/api/wizard/start")).toBe(false);
  expect(supportsModelSettings("/api/extract", "GET")).toBe(false);
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
