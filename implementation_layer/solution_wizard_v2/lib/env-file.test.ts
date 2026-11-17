import { describe, expect, it } from "vitest";
import { composeEnv, envValue, hasEnvValues, parseEnvExample } from "./env-file";

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

describe("parseEnvExample", () => {
  it("lists each variable once, in the file's order, with the comments above it as help", () => {
    expect(parseEnvExample(EXAMPLE)).toEqual([
      {
        name: "AZURE_API_KEY",
        example: "",
        help: "Azure OpenAI: the model the PoC calls. Ask your administrator for the key.",
        optional: false,
      },
      { name: "AZURE_ENDPOINT", example: "https://example.openai.azure.com/", help: "", optional: false },
      { name: "TAVILY_API_KEY", example: "", help: "Web search (optional)", optional: true },
      { name: "MODEL_NAME", example: "gpt-4.1", help: "", optional: false },
    ]);
  });

  it("reads Windows line ends and an empty file", () => {
    expect(parseEnvExample("# Key\r\nA_KEY=\r\n")).toEqual([
      { name: "A_KEY", example: "", help: "Key", optional: false },
    ]);
    expect(parseEnvExample("")).toEqual([]);
  });

  it("does not take a sentence with an equals sign for a variable", () => {
    expect(parseEnvExample("# Example: set FOO=bar below\nFOO=\n").map((v) => v.name)).toEqual(["FOO"]);
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
