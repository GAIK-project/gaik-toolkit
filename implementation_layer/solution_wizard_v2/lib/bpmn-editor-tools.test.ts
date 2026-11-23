import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

// The read-only viewer and the modeler share the .bpmn-viewer-themed styles. The rule that
// hides bpmn-js's palette and context pad must leave the modeler (.bpmn-editable) alone, or
// the Workflow tab says "editable" while every editing tool is invisible.
const root = join(__dirname, "..");
const css = readFileSync(join(root, "app/globals.css"), "utf8");
const modeler = readFileSync(join(root, "components/bpmn-modeler.tsx"), "utf8");
const viewer = readFileSync(join(root, "components/bpmn-viewer.tsx"), "utf8");

// On a phone the modeler has no palette (the diagram is for reading there); that one
// rule sits in its own media query and is checked by itself below.
const PHONE_RULE = /@media \(max-width: 767px\) \{\s*\.bpmn-editable \.djs-palette \{\s*display: none;\s*\}\s*\}/;

function rulesHiding(selectorPart: string): string[] {
  const rules = css.replace(PHONE_RULE, "").match(/[^{}]+\{[^{}]*display:\s*none[^{}]*\}/g) ?? [];
  return rules
    .map((r) => r.slice(0, r.indexOf("{")))
    .filter((sel) => sel.includes(selectorPart));
}

describe("BPMN editing tools", () => {
  it("hides the palette and context pad only outside the modeler", () => {
    for (const part of [".djs-palette", ".djs-context-pad"]) {
      const selectors = rulesHiding(part);
      expect(selectors.length).toBeGreaterThan(0);
      for (const sel of selectors) {
        for (const one of sel.split(",").filter((s) => s.includes(part))) {
          expect(one).toContain(":not(.bpmn-editable)");
        }
      }
    }
  });

  it("hides the modeler's palette on a phone only", () => {
    expect(css).toMatch(PHONE_RULE);
  });

  it("keeps the modeler's palette compact enough for the tab's canvas", () => {
    const entry = css.match(/\.bpmn-editable \.djs-palette \.entry,[^{]*\{([^}]*)\}/);
    expect(entry, "a compact size for the modeler's palette entries").not.toBeNull();
    const size = Number(/\bwidth:\s*(\d+)px/.exec(entry![1])?.[1]);
    expect(size).toBeGreaterThan(0);
    expect(size).toBeLessThanOrEqual(32);
  });

  it("puts the compact palette outside @layer, where it can beat bpmn-js's unlayered CSS", () => {
    const layerStart = css.indexOf("@layer components {");
    expect(layerStart).toBeGreaterThanOrEqual(0);
    let depth = 0;
    let layerEnd = -1;
    for (let i = css.indexOf("{", layerStart); i < css.length; i++) {
      if (css[i] === "{") depth++;
      if (css[i] === "}" && --depth === 0) {
        layerEnd = i;
        break;
      }
    }
    expect(css.indexOf(".bpmn-editable .djs-palette .entry,")).toBeGreaterThan(layerEnd);
  });

  it("marks the modeler editable and leaves the viewer read-only", () => {
    expect(modeler).toMatch(/className=\{`bpmn-viewer-themed bpmn-editable /);
    expect(viewer).not.toContain("bpmn-editable");
  });
});
