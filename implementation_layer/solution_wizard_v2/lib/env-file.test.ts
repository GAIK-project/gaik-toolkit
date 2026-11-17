import { describe, expect, it } from "vitest";
import {
  composeEnv,
  configProviders,
  envExampleKeyValues,
  envLayout,
  envValue,
  hasEnvValues,
  layoutVariables,
  parseEnvExample,
  parseEnvSections,
} from "./env-file";

const EXAMPLE = [
  "# Azure OpenAI: the model the PoC calls.",
  "# Ask your administrator for the key.",
  "AZURE_API_KEY=",
  "AZURE_ENDPOINT=https://example.openai.azure.com/",
  "",
  "# ---------------",
  "# Web search (optional)",
  "# TAVILY_API_KEY=",
  'export MODEL_NAME="gpt-4.1" # the deployment',
  "",
  "not a variable line",
  "AZURE_API_KEY=again",
].join("\n");

/**
 * The shape of the `.env.example` the scaffolder writes (solution_wizard's
 * `templates/poc/_common/env.example.tmpl`): a header, one `# --- Name ---`
 * section per provider with every variable commented out, notes between the
 * variables, and a few settings under no heading at the end. With the
 * external-services section a package that calls a third-party API adds.
 */
const GENERATED = `# Environment variables for Invoice extraction
# Copy to .env and enable only providers used by config.yaml stages.
# Never commit .env. Credentials are loaded independently for each stage.

# --- Azure OpenAI (model is your deployment name) ---
# AZURE_API_KEY=
# AZURE_ENDPOINT=https://your-resource.openai.azure.com/
# AZURE_API_VERSION=2025-03-01-preview
# AZURE_DEPLOYMENT=gpt-6-luna
# AZURE_TRANSCRIPTION_MODEL=gpt-4o-transcribe

# --- OpenAI ---
# OPENAI_API_KEY=
# OPENAI_MODEL=gpt-6-luna

# --- CSC Aitta ---
# AITTA_API_KEY=
# AITTA_API_TOKEN and AITTA_TOKEN are also accepted.
# AITTA_MODEL=google/gemma-4-31b-it
# AITTA_BASE_URL=https://aitta-api.csc.fi/openai/v1

# --- Explicit OpenAI-compatible endpoint ---
# Shares OPENAI_* with the OpenAI section, so one PoC cannot use both providers.
# OPENAI_API_KEY=
# OPENAI_BASE_URL=https://your-inference-server.example/v1
# OPENAI_MODEL=your-served-model

# --- Native Google Gemini Developer API ---
# GOOGLE_API_KEY=
# GEMINI_API_KEY is also accepted.
# GOOGLE_MODEL=gemini-2.5-flash

# --- Native Google Vertex AI ---
# GOOGLE_PROJECT_ID=your-gcp-project-id
# Unset: the EU multi-region first, the global endpoint as its fallback.
# A location set here is used as given, without a fallback.
# GOOGLE_CLOUD_LOCATION=eu
# GOOGLE_APPLICATION_CREDENTIALS=/absolute/path/to/credentials.json

# --- Anthropic / Anthropic in Microsoft Foundry ---
# ANTHROPIC_API_KEY=
# ANTHROPIC_MODEL=claude-sonnet-5-5
# ANTHROPIC_FOUNDRY_API_KEY=
# ANTHROPIC_FOUNDRY_RESOURCE=your-resource

# --- Optional LiteLLM backend (provider-prefixed models required) ---
# LITELLM_MODEL=azure/gpt-6-luna
# LITELLM_API_KEY=

# Audio components currently require an OpenAI or Azure stage.
# Self-hosted Whisper is selected with transcription_model=whisper_local.
# LOCAL_TRANSCRIBER_API_BASE=http://whisper.example.com:8080
# LOCAL_TRANSCRIBER_API_KEY=

# --- Remote Docling parsing service ---
# DOCLING_API_BASE=https://docling.example.com
# DOCLING_API_PASSWORD=

# --- External services (outside GAIK) ---
# Web search for the enrichment step.
TAVILY_API_KEY=
# How many results a search returns.
# TAVILY_MAX_RESULTS=5

# From the gaik release after 0.10.0, a config.yaml address not on this machine needs its host here.
# GAIK_ALLOWED_ENDPOINT_HOSTS=
`;

const CONFIG = (provider: string, stage?: string) =>
  [
    "# Provider/stage settings. Keep credentials in .env.",
    `provider: ${provider}`,
    "model: gpt-6-luna",
    ...(stage ? ["stages:", "  extraction:", `    provider: "${stage}"   # the extraction stage`] : []),
    "",
  ].join("\n");

const names = (variables: { name: string }[]) => variables.map((v) => v.name);

describe("parseEnvExample", () => {
  it("lists each variable once, in the file's order, with the comments above it as help", () => {
    expect(parseEnvExample(EXAMPLE)).toEqual([
      {
        name: "AZURE_API_KEY",
        example: "",
        help: "Azure OpenAI: the model the PoC calls. Ask your administrator for the key.",
        optional: false,
        line: 2,
      },
      { name: "AZURE_ENDPOINT", example: "https://example.openai.azure.com/", help: "", optional: false, line: 3 },
      { name: "TAVILY_API_KEY", example: "", help: "Web search (optional)", optional: true, line: 7 },
      { name: "MODEL_NAME", example: "gpt-4.1", help: "", optional: false, line: 8 },
    ]);
  });

  it("reads Windows line ends and an empty file", () => {
    expect(parseEnvExample("# Key\r\nA_KEY=\r\n")).toEqual([
      { name: "A_KEY", example: "", help: "Key", optional: false, line: 1 },
    ]);
    expect(parseEnvExample("")).toEqual([]);
  });

  it("does not take a sentence with an equals sign for a variable", () => {
    expect(parseEnvExample("# Example: set FOO=bar below\nFOO=\n").map((v) => v.name)).toEqual(["FOO"]);
  });
});

describe("parseEnvSections", () => {
  const sections = parseEnvSections(GENERATED);

  it("takes a framed comment for a section's heading, without its dashes", () => {
    expect(sections.map((s) => s.title)).toEqual([
      "Azure OpenAI (model is your deployment name)",
      "OpenAI",
      "CSC Aitta",
      "Explicit OpenAI-compatible endpoint",
      "Native Google Gemini Developer API",
      "Native Google Vertex AI",
      "Anthropic / Anthropic in Microsoft Foundry",
      "Optional LiteLLM backend (provider-prefixed models required)",
      null,
      "Remote Docling parsing service",
      "External services (outside GAIK)",
      null,
    ]);
  });

  it("never gives a heading, or the file's own header, to a variable as help", () => {
    const all = sections.flatMap((s) => s.variables);
    expect(all.filter((v) => /---|Native Google|CSC Aitta|Copy to \.env/.test(v.help))).toEqual([]);
    expect(all.find((v) => v.name === "AZURE_API_KEY")?.help).toBe("");
    expect(all.find((v) => v.name === "GOOGLE_API_KEY")?.help).toBe("GEMINI_API_KEY is also accepted.");
  });

  it("gives a note to the variable it is about: above it, or under it when it names another spelling", () => {
    const of = (name: string, title: string) =>
      sections.find((s) => s.title === title)?.variables.find((v) => v.name === name);
    expect(of("AITTA_API_KEY", "CSC Aitta")?.help).toBe("AITTA_API_TOKEN and AITTA_TOKEN are also accepted.");
    expect(of("AITTA_MODEL", "CSC Aitta")?.help).toBe("");
    expect(of("GOOGLE_CLOUD_LOCATION", "Native Google Vertex AI")?.help).toBe(
      "Unset: the EU multi-region first, the global endpoint as its fallback. A location set here is used as given, without a fallback.",
    );
    expect(of("OPENAI_API_KEY", "Explicit OpenAI-compatible endpoint")?.help).toBe(
      "Shares OPENAI_* with the OpenAI section, so one PoC cannot use both providers.",
    );
    expect(of("TAVILY_API_KEY", "External services (outside GAIK)")?.help).toBe(
      "Web search for the enrichment step.",
    );
  });

  it("ends a section at a blank line: what follows without a heading is under none", () => {
    const loose = sections.filter((s) => s.title === null).map((s) => names(s.variables));
    expect(loose).toEqual([["LOCAL_TRANSCRIBER_API_BASE", "LOCAL_TRANSCRIBER_API_KEY"], ["GAIK_ALLOWED_ENDPOINT_HOSTS"]]);
  });

  it("keeps every occurrence of a variable listed under two providers", () => {
    const keys = sections.flatMap((s) => s.variables).filter((v) => v.name === "OPENAI_API_KEY");
    expect(keys).toHaveLength(2);
    expect(parseEnvExample(GENERATED).filter((v) => v.name === "OPENAI_API_KEY")).toHaveLength(1);
  });
});

describe("configProviders", () => {
  it("reads the top-level provider and each stage's, once each", () => {
    expect(configProviders(CONFIG("azure"))).toEqual(["azure"]);
    expect(configProviders(CONFIG("azure", "aitta"))).toEqual(["azure", "aitta"]);
    expect(configProviders(CONFIG("azure", "azure"))).toEqual(["azure"]);
    expect(configProviders("provider: azure_openai         # azure_openai | openai\nuse_azure: true\n")).toEqual([
      "azure_openai",
    ]);
    expect(configProviders("provider: 'OpenAI-Compatible'\n")).toEqual(["openai_compatible"]);
  });

  it("finds none in a file that names none", () => {
    expect(configProviders("models:\n  extraction: gpt-5.4\n# provider: azure\n")).toEqual([]);
    expect(configProviders("")).toEqual([]);
  });
});

describe("envLayout", () => {
  it("shows the provider the package uses and the external services, and folds the rest", () => {
    const layout = envLayout(GENERATED, CONFIG("azure"));
    if (layout.kind !== "grouped") throw new Error("expected a grouped layout");

    expect(layout.shown.map((s) => [s.title, names(s.variables)])).toEqual([
      [
        "Azure OpenAI (model is your deployment name)",
        ["AZURE_API_KEY", "AZURE_ENDPOINT", "AZURE_API_VERSION", "AZURE_DEPLOYMENT", "AZURE_TRANSCRIPTION_MODEL"],
      ],
      ["External services (outside GAIK)", ["TAVILY_API_KEY", "TAVILY_MAX_RESULTS"]],
    ]);
    // The key and what has only a placeholder; not what comes with a working default.
    expect(layout.needed).toEqual(["AZURE_API_KEY", "AZURE_ENDPOINT", "TAVILY_API_KEY"]);
    // Everything else once, under its own heading.
    const rest = layout.rest.flatMap((s) => names(s.variables));
    expect(new Set(rest).size).toBe(rest.length);
    expect(layout.restCount).toBe(rest.length);
    expect(rest).toContain("OPENAI_API_KEY");
    expect(rest).toContain("GAIK_ALLOWED_ENDPOINT_HOSTS");
    expect(rest).not.toContain("AZURE_API_KEY");
    expect(layout.rest[0].title).toBe("OpenAI");
    expect(new Set(names(layoutVariables(layout))).size).toBe(parseEnvExample(GENERATED).length);
  });

  it.each([
    ["azure_openai", "Azure OpenAI (model is your deployment name)", ["AZURE_API_KEY", "AZURE_ENDPOINT"]],
    ["openai", "OpenAI", ["OPENAI_API_KEY"]],
    ["aitta", "CSC Aitta", ["AITTA_API_KEY"]],
    ["openai_compatible", "Explicit OpenAI-compatible endpoint", ["OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENAI_MODEL"]],
    ["google", "Native Google Gemini Developer API", ["GOOGLE_API_KEY"]],
    ["vertex", "Native Google Vertex AI", ["GOOGLE_PROJECT_ID", "GOOGLE_APPLICATION_CREDENTIALS"]],
    ["litellm", "Optional LiteLLM backend (provider-prefixed models required)", ["LITELLM_API_KEY"]],
  ])("finds the section of %s", (provider, title, needed) => {
    const layout = envLayout(GENERATED, CONFIG(provider));
    if (layout.kind !== "grouped") throw new Error("expected a grouped layout");
    expect(layout.shown[0].title).toBe(title);
    expect(layout.needed.filter((name) => !name.startsWith("TAVILY"))).toEqual(needed);
  });

  it("shows the two Anthropic providers their own variables of the shared section", () => {
    const direct = envLayout(GENERATED, CONFIG("anthropic"));
    const foundry = envLayout(GENERATED, CONFIG("anthropic_foundry"));
    if (direct.kind !== "grouped" || foundry.kind !== "grouped") throw new Error("expected grouped layouts");
    expect(names(direct.shown[0].variables)).toEqual(["ANTHROPIC_API_KEY", "ANTHROPIC_MODEL"]);
    expect(names(foundry.shown[0].variables)).toEqual(["ANTHROPIC_FOUNDRY_API_KEY", "ANTHROPIC_FOUNDRY_RESOURCE"]);
    expect(direct.rest.flatMap((s) => names(s.variables))).toContain("ANTHROPIC_FOUNDRY_API_KEY");
  });

  it("shows every provider the stages use, and the OpenAI key on the line of the section in use", () => {
    const layout = envLayout(GENERATED, CONFIG("azure", "openai_compatible"));
    if (layout.kind !== "grouped") throw new Error("expected a grouped layout");
    expect(layout.shown.map((s) => s.title)).toEqual([
      "Azure OpenAI (model is your deployment name)",
      "Explicit OpenAI-compatible endpoint",
      "External services (outside GAIK)",
    ]);

    const env = composeEnv(GENERATED, { OPENAI_API_KEY: "typed" }, [], layoutVariables(layout)).split("\n");
    const at = env.indexOf("OPENAI_API_KEY=typed");
    expect(env[at - 2]).toBe("# --- Explicit OpenAI-compatible endpoint ---");
    expect(env.filter((line) => line === "OPENAI_API_KEY=typed")).toHaveLength(1);
    // Under the provider the package does not use, the line stays as it was.
    expect(env[env.indexOf("# --- OpenAI ---") + 1]).toBe("# OPENAI_API_KEY=");
  });

  it("falls back to the flat list when the provider cannot be told", () => {
    const flat = { kind: "flat", variables: parseEnvExample(GENERATED) };
    // No config.yaml, one that names no provider, one that names an unknown one.
    expect(envLayout(GENERATED, null)).toEqual(flat);
    expect(envLayout(GENERATED, "models:\n  extraction: gpt-5.4\n")).toEqual(flat);
    expect(envLayout(GENERATED, CONFIG("bedrock"))).toEqual(flat);
    // A known provider, and an example that has no section for it.
    expect(envLayout(EXAMPLE, CONFIG("azure"))).toEqual({ kind: "flat", variables: parseEnvExample(EXAMPLE) });
    expect(envLayout("# --- External services ---\nTAVILY_API_KEY=\n", CONFIG("azure")).kind).toBe("flat");
  });
});

describe("composeEnv", () => {
  it("is .env.example with the typed values in place and the rest as it was", () => {
    const env = composeEnv(EXAMPLE, { AZURE_API_KEY: " typed-value-1 ", TAVILY_API_KEY: "typed-value-2" });

    expect(env.split("\n")).toEqual([
      "# Azure OpenAI: the model the PoC calls.",
      "# Ask your administrator for the key.",
      "AZURE_API_KEY=typed-value-1",
      "AZURE_ENDPOINT=https://example.openai.azure.com/",
      "",
      "# ---------------",
      "# Web search (optional)",
      "TAVILY_API_KEY=typed-value-2",
      'export MODEL_NAME="gpt-4.1" # the deployment',
      "",
      "not a variable line",
      "AZURE_API_KEY=again",
      "",
    ]);
  });

  it("appends the variables the user added, once, and only with a name and a value", () => {
    const env = composeEnv("A_KEY=\n", { A_KEY: "one" }, [
      { name: "GOOGLE_CSE_ID", value: "two" },
      { name: "GOOGLE_CSE_ID", value: "again" },
      { name: "A_KEY", value: "listed already" },
      { name: "not a name", value: "x" },
      { name: "EMPTY", value: "  " },
    ]);

    expect(env).toBe("A_KEY=one\nGOOGLE_CSE_ID=two\n");
  });

  it("writes a package without .env.example from the added variables alone", () => {
    expect(composeEnv("", {}, [{ name: "TAVILY_API_KEY", value: "typed" }])).toBe("TAVILY_API_KEY=typed\n");
  });

  it("keeps a value on one line and quotes what a shell or dotenv would split", () => {
    expect(composeEnv("A=\n", { A: "two words\nmore" })).toBe("A='two wordsmore'\n");
    expect(envValue("plain-Value_1.2:3/4@x")).toBe("plain-Value_1.2:3/4@x");
    expect(envValue("with#hash")).toBe("'with#hash'");
    expect(envValue(`it's "quoted" $x`)).toBe(`"it's \\"quoted\\" \\$x"`);
  });

  it("uncomments only the lines that got a value in the generated file", () => {
    const env = composeEnv(GENERATED, { AZURE_API_KEY: "typed" }).split("\n");
    expect(env).toContain("AZURE_API_KEY=typed");
    expect(env).toContain("# AZURE_ENDPOINT=https://your-resource.openai.azure.com/");
    expect(env.filter((line) => !line.startsWith("#") && line.includes("="))).toEqual([
      "AZURE_API_KEY=typed",
      "TAVILY_API_KEY=",
    ]);
  });
});

describe("hasEnvValues", () => {
  it("is false until something is typed", () => {
    expect(hasEnvValues({})).toBe(false);
    expect(hasEnvValues({ A: "  " }, [{ name: "B", value: "" }])).toBe(false);
    expect(hasEnvValues({ A: "x" })).toBe(true);
    expect(hasEnvValues({}, [{ name: "B", value: "x" }])).toBe(true);
    expect(hasEnvValues({}, [{ name: "not a name", value: "x" }])).toBe(false);
  });
});

describe("envExampleKeyValues", () => {
  it("names each credential given a value, also commented out, and nothing else of it", () => {
    const text = [
      "AZURE_API_KEY=typed-by-mistake",
      "# OPENAI_API_KEY=typed-by-mistake",
      "export HF_TOKEN=typed-by-mistake",
      'CLIENT_SECRET="typed by mistake"',
      "DOCLING_API_PASSWORD=hunter2  # the service's",
      "OPENAI_APIKEY=typed-by-mistake",
      'GOOGLE_SERVICE_ACCOUNT_JSON={"type": "x"}',
      "AZURE_API_KEY=again",
    ].join("\n");

    expect(envExampleKeyValues(text)).toEqual([
      "AZURE_API_KEY",
      "OPENAI_API_KEY",
      "HF_TOKEN",
      "CLIENT_SECRET",
      "DOCLING_API_PASSWORD",
      "OPENAI_APIKEY",
      "GOOGLE_SERVICE_ACCOUNT_JSON",
    ]);
  });

  it("lets placeholders and settings that are not credentials stand", () => {
    const text = [
      "AZURE_API_KEY=",
      "# AZURE_API_KEY=",
      'AZURE_API_KEY=""',
      "AZURE_API_KEY=<your key>",
      "AZURE_API_KEY=your-key-here",
      "OPENAI_API_KEY=YOUR_API_KEY",
      "TAVILY_API_KEY=xxxx",
      "TAVILY_API_KEY=   # from the provider's portal",
      "AZURE_ENDPOINT=https://your-resource.openai.azure.com/",
      "AZURE_API_VERSION=2025-03-01-preview",
      "MAX_TOKENS=4000",
      "KEYWORDS=invoice,receipt",
      "# GOOGLE_APPLICATION_CREDENTIALS=/absolute/path/to/credentials.json",
      "# Set OPENAI_API_KEY in .env, not here.",
    ].join("\n");

    expect(envExampleKeyValues(text)).toEqual([]);
  });
});
