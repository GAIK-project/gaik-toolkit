import type { SemanticIconKind } from "./semantic-icon";
import { iconAccentColor, semanticIconPaths } from "./semantic-icon";

export function escapeHtml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

export function iconSvgHtml(kind: SemanticIconKind, size = 16): string {
  const accent = iconAccentColor(kind);
  const paths = semanticIconPaths(kind)
    .map(
      (d) =>
        `<path d="${d}" fill="none" stroke="${accent}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>`,
    )
    .join("");
  return `<svg class="bpmn-icon-svg" width="${size}" height="${size}" viewBox="0 0 24 24" aria-hidden="true">${paths}</svg>`;
}
