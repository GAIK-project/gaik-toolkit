import {
  ACTION_STATUS,
  CONFIDENCE,
  FINDING_QUESTIONS,
  FINDING_STATUS,
  formatDate,
  ROLES,
  ROUTE_LABEL,
  type Screening,
  TIERS,
  conditionText,
  isCurrentGap,
} from "./types";

function cites(list: { ref: string; instrument?: string }[] = []): string {
  return list
    .map(
      (c) =>
        (c.instrument && c.instrument !== "AI Act" ? `${c.instrument} ` : "") +
        c.ref,
    )
    .join(", ");
}

// A table cell: a backslash first, so the one put before "|" is not taken back.
function cell(text: string): string {
  return text
    .replace(/\\/g, "\\\\")
    .replace(/\|/g, "\\|")
    .replace(/\s*\n\s*/g, " ");
}

/** The screening as a readable Markdown report, from the validated data only. */
export function screeningToMarkdown(s: Screening, name: string): string {
  const { summary } = s;
  const tier = summary.risk_class ? TIERS[summary.risk_class] : null;
  const lines: string[] = [];
  lines.push(`# EU AI Act screening: ${name}`, "");
  lines.push(
    `> A preliminary screening against the EU AI Act, based only on the description and answers given on ${formatDate(s.screened_on)} and on a summary of the law checked on ${formatDate(s.reference_last_verified)}. It is not legal advice and does not confirm compliance.`,
    "",
  );
  lines.push("## In short", "", summary.one_line, "");
  lines.push("## The result", "");
  lines.push(`**What was assessed:** ${summary.screened_use}`, "");
  if (tier) {
    lines.push(`**Risk tier:** ${tier.label}. ${tier.means}`, "");
  } else if (summary.outcome === "not_in_scope") {
    lines.push("**Risk tier:** Outside the AI Act.", "");
  } else {
    lines.push("**Risk tier:** Not yet determined.", "");
    for (const alt of summary.alternatives ?? [])
      lines.push(
        `- If ${conditionText(alt.if)}: ${TIERS[alt.risk_class].label}`,
      );
    lines.push("");
  }
  lines.push(
    `**Your role:** ${ROLES[summary.role].label}. ${ROLES[summary.role].means}`,
    "",
    `**How certain this is:** ${CONFIDENCE[summary.confidence].label}. ${CONFIDENCE[summary.confidence].means}`,
    "",
  );

  const gaps = s.actions.filter((a) => isCurrentGap(a, s.screened_on));
  if (gaps.length) {
    lines.push("## Current gaps", "");
    for (const a of gaps)
      lines.push(
        `- **${a.action}** (required since ${formatDate(a.applies_from ?? "")}; ${ACTION_STATUS[a.status ?? "unknown"]})`,
      );
    lines.push("");
  }

  const required = s.actions.filter((a) => a.type === "required");
  if (required.length) {
    lines.push("## What you must do", "");
    const existing = summary.mode === "existing";
    lines.push(
      `| What to do | Legal basis | From | Who acts |${existing ? " Status |" : ""}`,
      `|---|---|---|---|${existing ? "---|" : ""}`,
    );
    for (const a of required)
      lines.push(
        `| ${cell(a.action)} | ${cell(cites(a.citations))} | ${a.applies_from ? formatDate(a.applies_from) : ""} | ${ROUTE_LABEL[a.route]} |${existing ? ` ${ACTION_STATUS[a.status ?? "unknown"]} |` : ""}`,
      );
    lines.push("");
  }

  const recommended = s.actions.filter((a) => a.type === "recommended");
  if (recommended.length) {
    lines.push("## Recommendations (optional)", "");
    for (const a of recommended)
      lines.push(
        `- **${a.action}** ${a.reason ?? ""} These are suggestions, not legal requirements.`,
      );
    lines.push("");
  }

  if (s.timeline.length) {
    lines.push(
      "## Dates that affect you",
      "",
      "| Date | What applies | Status |",
      "|---|---|---|",
    );
    for (const t of s.timeline)
      lines.push(
        `| ${formatDate(t.date)} | ${cell(t.what)} | ${t.status === "in_force" ? "In force" : "Upcoming"} |`,
      );
    lines.push("");
  }

  lines.push("## How we reached this result", "");
  for (const f of s.findings) {
    lines.push(`### ${FINDING_QUESTIONS[f.id] ?? f.question}`, "");
    lines.push(
      `**Answer:** ${FINDING_STATUS[f.status]}. ${f.answer}`,
      "",
      f.reasoning,
      "",
    );
    for (const e of f.evidence) lines.push(`> "${e.quote}"`);
    if (f.evidence.length) lines.push("");
    if (f.citations.length)
      lines.push(`**Legal basis:** ${cites(f.citations)}`, "");
  }

  if (s.triggers.length) {
    lines.push("## What would change the result", "");
    for (const t of s.triggers)
      lines.push(
        `- If ${t.change}, the use case would become ${TIERS[t.would_become].label}.`,
      );
    lines.push("");
  }
  if (s.open_questions.length) {
    lines.push("## Open questions", "");
    for (const q of s.open_questions) lines.push(`- ${q}`);
    lines.push("");
  }
  if (s.adjacent.length) {
    lines.push("## Related rules to check", "");
    for (const a of s.adjacent) lines.push(`- ${a.flag}`);
    lines.push("");
  }
  lines.push("---", "", s.disclaimer, "");
  return lines.join("\n");
}
