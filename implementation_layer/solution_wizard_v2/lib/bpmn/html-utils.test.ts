import { describe, expect, it } from "vitest";
import { escapeHtml, iconSvgHtml } from "./html-utils";

describe("escapeHtml", () => {
  it("escapes the five HTML-significant characters", () => {
    expect(escapeHtml(`<a href="x">Tom & Jerry's</a>`)).toBe(
      "&lt;a href=&quot;x&quot;&gt;Tom &amp; Jerry's&lt;/a&gt;",
    );
  });

  it("leaves plain text untouched", () => {
    expect(escapeHtml("Retrieval (RAG)")).toBe("Retrieval (RAG)");
  });
});

describe("iconSvgHtml", () => {
  it("renders an svg with the icon's paths and accent colour", () => {
    const svg = iconSvgHtml("human", 20);
    expect(svg).toContain('width="20" height="20"');
    expect(svg).toContain("<path");
    expect(svg).toContain('stroke="#e09a52"'); // human accent colour
  });

  it("defaults to size 16", () => {
    expect(iconSvgHtml("generic")).toContain('width="16" height="16"');
  });
});
