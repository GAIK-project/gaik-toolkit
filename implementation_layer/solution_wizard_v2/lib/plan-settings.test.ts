import { describe, expect, it } from "vitest";
import { planSettings } from "./plan-settings";

describe("planSettings", () => {
  it("keeps plain values in order", () => {
    expect(planSettings({ provider: "Azure AI Search", top_k: "5" })).toEqual({
      readable: [
        ["provider", "Azure AI Search"],
        ["top_k", "5"],
      ],
      hidden: 0,
    });
  });

  it("leaves out JSON objects and arrays, and counts them", () => {
    expect(
      planSettings({
        transcriber_ctor: '{"model": "whisper", "language": "fi"}',
        fields: ' ["a", "b"]',
        model: "gpt-4o",
      }),
    ).toEqual({ readable: [["model", "gpt-4o"]], hidden: 2 });
  });

  it("counts the hidden ones when a step has nothing else", () => {
    expect(planSettings({ transcriber_ctor: '{"model": "whisper"}' })).toEqual({ readable: [], hidden: 1 });
  });

  it("keeps ordinary text that only starts like JSON", () => {
    expect(
      planSettings({
        prompt: "[luonnos] Tiivistä asiakkaan viesti",
        greeting: "{nimi}, kiitos viestistäsi",
      }),
    ).toEqual({
      readable: [
        ["prompt", "[luonnos] Tiivistä asiakkaan viesti"],
        ["greeting", "{nimi}, kiitos viestistäsi"],
      ],
      hidden: 0,
    });
  });

  it("takes an empty value and the backend's \"null\" as no value, neither shown nor counted", () => {
    expect(planSettings({ note: "  ", language: "null", other: " null ", model: "gpt-4o" })).toEqual({
      readable: [["model", "gpt-4o"]],
      hidden: 0,
    });
  });

  it("keeps the other values JSON can hold: numbers, true and false", () => {
    expect(planSettings({ top_k: "5", rerank: "true", stream: "false" })).toEqual({
      readable: [
        ["top_k", "5"],
        ["rerank", "true"],
        ["stream", "false"],
      ],
      hidden: 0,
    });
  });

  it("has nothing for a step without settings", () => {
    expect(planSettings(undefined)).toEqual({ readable: [], hidden: 0 });
  });
});
