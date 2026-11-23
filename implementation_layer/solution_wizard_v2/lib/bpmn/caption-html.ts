import { escapeHtml } from "./html-utils";
import { formatFullLabel, stepCaptionLines } from "./semantic-icon";

export function captionHtml(options: {
  short: string;
  full: string;
  variant?: "step" | "lane" | "pool";
  width?: number;
}): string {
  const { short, full, variant = "step", width } = options;
  const widthStyle = width ? ` style="width:${width}px;max-width:${width}px"` : "";

  return `<div class="bpmn-caption bpmn-caption--${variant}"${widthStyle} data-tooltip="${escapeHtml(full)}" aria-label="${escapeHtml(full)}" title="${escapeHtml(full)}" tabindex="0"><span class="bpmn-caption__text">${escapeHtml(short)}</span></div>`;
}

export function laneHeaderCaptionHtml(name: string, width: number): string {
  const full = formatFullLabel(name);
  return `<div class="bpmn-caption bpmn-caption--lane" style="width:${width}px;max-width:${width}px" aria-label="${escapeHtml(full)}">${escapeHtml(full)}</div>`;
}

/** Full multi-line label above a task box. */
export function stepAboveCaptionHtml(
  name: string,
  width: number,
  bpmnType?: string,
): string {
  const lines = stepCaptionLines(name, bpmnType);
  const full = formatFullLabel(name);
  const lineHtml = lines
    .map((line, index) => {
      const isComponent = index > 0 && /^\[[^\]]+\]$/.test(line);
      const cls = isComponent
        ? "bpmn-caption__line bpmn-caption__line--component"
        : "bpmn-caption__line";
      return `<span class="${cls}">${escapeHtml(line)}</span>`;
    })
    .join("");

  return `<div class="bpmn-caption bpmn-caption--step-above" style="width:${width}px;max-width:${width}px" aria-label="${escapeHtml(full)}" title="${escapeHtml(full)}">${lineHtml}</div>`;
}
