export const MODEL_SETTINGS_HEADER = "x-gaik-model-settings";

export type ModelProvider = "openai" | "azure" | "aitta";
export interface ModelSettings {
  provider: ModelProvider;
  model: string;
  apiKey: string;
  azureEndpoint?: string;
  apiVersion?: string;
}

const SUPPORTED_PATHS = [
  "/api/extract",
  "/api/extract-vision",
  "/api/llm-judge/text-pair",
  "/api/llm-judge/hallucinations",
  "/api/llm-judge/validate",
  "/api/schema-generator",
  "/api/classify",
  "/api/parse",
  "/api/postgres-agent/ask",
  // Incident reporting: the schema, then text, scanned-form and audio extraction.
  "/api/pipeline/schema",
  "/api/pipeline/text/stream",
  "/api/pipeline/document/stream",
  "/api/pipeline/audio/stream",
  "/api/model-settings/test",
  // Web scraper: the extraction step after the crawl.
  "/api/web-scraper/run",
];

export function supportsModelSettings(path: string, method = "POST"): boolean {
  if (method.toUpperCase() !== "POST") return false;
  return SUPPORTED_PATHS.some(
    (prefix) => path === prefix || path.startsWith(`${prefix}/`),
  );
}

export function pageUsesModelSettings(path: string): boolean {
  return [
    "/extractor",
    "/vision-extractor",
    "/llm-judge",
    "/schema-generator",
    "/classifier",
    "/parser",
    "/postgres-agent",
    "/incident-report",
    "/document-structured",
    "/audio-structured",
    "/diary",
    "/web-scraper",
  ].includes(path);
}

export function normalizeAzureEndpoint(value: string): string {
  const endpoint = new URL(value);
  const host = endpoint.hostname.toLowerCase();
  // Exactly one resource label: excludes private-link names and suffix lookalikes.
  if (
    endpoint.protocol !== "https:" ||
    endpoint.port ||
    endpoint.username ||
    endpoint.password ||
    endpoint.search ||
    endpoint.hash ||
    !/^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.(?:openai\.azure\.com|services\.ai\.azure\.com)$/.test(
      host,
    ) ||
    !["", "/", "/openai/v1", "/openai/v1/"].includes(endpoint.pathname)
  ) {
    throw new Error(
      "Use your public Azure resource URL (https://name.openai.azure.com or https://name.services.ai.azure.com).",
    );
  }
  return endpoint.origin;
}

export function validateModelSettings(value: unknown): ModelSettings {
  if (!value || typeof value !== "object" || Array.isArray(value))
    throw new Error("Invalid model settings.");
  const input = value as Record<string, unknown>;
  const allowed = new Set([
    "provider",
    "model",
    "apiKey",
    "azureEndpoint",
    "apiVersion",
  ]);
  if (Object.keys(input).some((key) => !allowed.has(key)))
    throw new Error("Invalid model settings.");
  if (!["openai", "azure", "aitta"].includes(String(input.provider)))
    throw new Error("Select a supported provider.");
  if (
    typeof input.model !== "string" ||
    !input.model.trim() ||
    input.model.length > 200 ||
    /[\x00-\x1f\x7f]/.test(input.model)
  ) {
    throw new Error("Enter the model ID or Azure deployment name.");
  }
  if (
    typeof input.apiKey !== "string" ||
    !input.apiKey.trim() ||
    input.apiKey.length > 6000 ||
    !/^[\x21-\x7e]+$/.test(input.apiKey.trim())
  ) {
    throw new Error("Enter a valid API key or Aitta token.");
  }
  const result: ModelSettings = {
    provider: input.provider as ModelProvider,
    model: input.model.trim(),
    apiKey: input.apiKey.trim(),
  };
  if (result.provider === "azure") {
    if (typeof input.azureEndpoint !== "string")
      throw new Error("Enter your Azure resource URL.");
    result.azureEndpoint = normalizeAzureEndpoint(input.azureEndpoint.trim());
    if (input.apiVersion !== undefined && input.apiVersion !== "") {
      if (
        typeof input.apiVersion !== "string" ||
        !/^\d{4}-\d{2}-\d{2}(?:-preview)?$/.test(input.apiVersion)
      ) {
        throw new Error(
          "Enter an Azure API version such as 2025-03-01-preview.",
        );
      }
      result.apiVersion = input.apiVersion;
    }
  } else if (input.azureEndpoint || input.apiVersion) {
    throw new Error("Endpoint overrides are only available for Azure.");
  }
  return result;
}

export function encodeModelSettings(settings: ModelSettings): string {
  return JSON.stringify(validateModelSettings(settings));
}

export function parseModelSettingsHeader(raw: string): ModelSettings {
  if (raw.length > 8192) throw new Error("Model settings are too large.");
  try {
    return validateModelSettings(JSON.parse(raw));
  } catch {
    // Never include submitted values (especially apiKey) in validation errors.
    throw new Error(
      "Invalid model settings. Check the provider, model, key, and Azure endpoint.",
    );
  }
}

/** A server model the user picked: `provider:model`, run on the server's keys. */
export const SERVER_MODEL_HEADER = "x-gaik-server-model";

// A picked server model also runs these; an own key does not. The RAG index
// stays on the server between requests, where a browser key must not, and the
// transcriber takes a speech model, not the chat model of the key dialog.
const SERVER_MODEL_PATHS = [
  "/api/rag/index",
  "/api/rag/load-example",
  "/api/transcribe",
];

export function supportsServerModel(path: string, method = "POST"): boolean {
  if (supportsModelSettings(path, method)) return true;
  if (method.toUpperCase() !== "POST") return false;
  return SERVER_MODEL_PATHS.some(
    (prefix) => path === prefix || path.startsWith(`${prefix}/`),
  );
}

export function isServerModelId(value: unknown): value is string {
  return (
    typeof value === "string" &&
    /^[a-z_]{2,30}:[A-Za-z0-9._/-]{1,120}$/.test(value)
  );
}

/** The reasoning effort picked in the model menu; left out for Auto. */
export const REASONING_EFFORT_HEADER = "x-gaik-reasoning-effort";
export const REASONING_EFFORTS = ["low", "medium", "high"] as const;
export type ReasoningEffort = (typeof REASONING_EFFORTS)[number];

export function isReasoningEffort(value: unknown): value is ReasoningEffort {
  return REASONING_EFFORTS.includes(value as ReasoningEffort);
}

/** GPT-6 models on OpenAI or Azure take an effort; the API sends it to no other. */
export function takesReasoningEffort(provider: string, model: string): boolean {
  return (
    (provider === "openai" || provider === "azure") &&
    model.toLowerCase().startsWith("gpt-6")
  );
}

/**
 * The effort a request carries: the picked one when the model in use takes it.
 * Null is Auto. While the model list has not loaded the model is unknown, and
 * the pick is sent for the API to decide.
 */
export function reasoningEffortFor(
  picked: ReasoningEffort | null,
  model: { provider: string; model: string } | null,
): ReasoningEffort | null {
  if (!picked || !isReasoningEffort(picked)) return null;
  if (model && !takesReasoningEffort(model.provider, model.model)) return null;
  return picked;
}
