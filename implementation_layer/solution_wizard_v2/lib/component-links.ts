// A GAIK component's name in the wizard's reply ("VisionExtractor") becomes a
// quiet inline control that opens a small card: the name, one line on what the
// component does and a link to its documentation.
//
// The names and what each takes and produces come from the Solution Wizard's
// component registry through lib/gaik-components.generated.json
// (scripts/build-component-catalog.mjs); the words come from the dictionary.

import catalog from "./gaik-components.generated.json";
import type { ChatActivityLabels } from "./chat-activity";
import { fillTemplate } from "./chat-template";
import { EXTERNAL_ICON } from "./markdown";
import { plainLabels } from "./plain-label";

export type ComponentInfo = { name: string; inputs: string[]; outputs: string[]; docs: string };
export type ComponentCardLabels = NonNullable<ChatActivityLabels["components"]>;

const COMPONENTS: ComponentInfo[] = catalog.components;
const BY_NAME = new Map(COMPONENTS.map((component) => [component.name, component]));

/** The component of that exact name, or undefined. */
export const componentNamed = (name: string) => BY_NAME.get(name);

// A whole name only: "Extractor" is not found inside "VisionExtractor" or
// "Extractors". The longest name goes first, so "LLMJudgePanel" is not read as
// "LLMJudge".
const NAME = new RegExp(
  `(?<![\\p{L}\\p{N}_])(?:${[...BY_NAME.keys()].sort((a, b) => b.length - a.length).join("|")})(?![\\p{L}\\p{N}_])`,
  "gu",
);

const escapeHtml = (s: string) =>
  s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

/** What the component does in one line: what it takes and what it produces, in plain words. */
export function componentLine(component: ComponentInfo, labels: ComponentCardLabels): string {
  return fillTemplate(labels.line, {
    inputs: plainLabels(component.inputs, labels.artifacts).join(", "),
    outputs: plainLabels(component.outputs, labels.artifacts).join(", "),
  });
}

function cardHtml(component: ComponentInfo, labels: ComponentCardLabels, id: string): string {
  const name = escapeHtml(component.name);
  // Spans throughout: the name sits inside a paragraph, a list item or a cell.
  return (
    `<span class="cmp">` +
    `<button type="button" class="cmp-name" data-testid="component-name" aria-describedby="${id}">${name}</button>` +
    `<span class="cmp-card" data-testid="component-card"><span class="cmp-card-box">` +
    `<span class="cmp-card-name">${name}</span>` +
    `<span class="cmp-card-line" id="${id}">${escapeHtml(componentLine(component, labels))}</span>` +
    `<a class="cmp-card-docs" href="${escapeHtml(component.docs)}" target="_blank" rel="noreferrer noopener">` +
    `${escapeHtml(labels.docs)}${EXTERNAL_ICON}</a>` +
    `</span></span></span>`
  );
}

// Text inside these is left alone: a link keeps its own target, a code block
// and a drawing keep their text.
const NOT_IN = /^<(\/?)(a|pre|svg|button)\b/i;

/**
 * The message's HTML (lib/markdown) with the first mention of each component
 * turned into its card. Later mentions of the same component stay plain text:
 * one quiet link per component is enough in one reply.
 */
export function withComponentLinks(
  html: string,
  labels: ComponentCardLabels | undefined,
  idPrefix: string,
): string {
  if (!labels || !html) return html;
  NAME.lastIndex = 0;
  if (!NAME.test(html)) return html;
  const seen = new Set<string>();
  let skip = 0;
  return html
    .split(/(<[^>]*>)/)
    .map((part) => {
      if (part.startsWith("<")) {
        const tag = NOT_IN.exec(part);
        if (tag) skip = Math.max(0, skip + (tag[1] ? -1 : 1));
        return part;
      }
      if (skip > 0) return part;
      return part.replace(NAME, (name) => {
        const component = BY_NAME.get(name);
        if (!component || seen.has(name)) return name;
        seen.add(name);
        return cardHtml(component, labels, `${idPrefix}-cmp-${seen.size}`);
      });
    })
    .join("");
}

type Box = { left: number; right: number; top: number; bottom: number };

/**
 * Where the card goes, in viewport pixels: under the name and starting at its
 * left edge; moved left as far as it must to stay inside `within` (the
 * message's column, inside the window); above the name when it would pass
 * `within`'s lower edge (the message field) and there is room above.
 */
export function cardPlacement(
  name: Box,
  card: { width: number; height: number },
  within: Box,
): { left: number; top: number; above: boolean } {
  const left = Math.max(within.left, Math.min(name.left, within.right - card.width));
  const above = name.bottom + card.height > within.bottom && name.top - card.height >= within.top;
  return { left, top: above ? name.top - card.height : name.bottom, above };
}
