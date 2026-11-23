#!/usr/bin/env node
/**
 * Sprint acceptance matrix: docs/sprint3-acceptance.json -> docs/sprint3-acceptance.md.
 *
 * Every acceptance criterion names the tests that verify it. This resolves each
 * reference against the working tree, so a renamed or deleted test breaks the
 * build instead of leaving a criterion that looks covered and is not.
 *
 * Usage:
 *   node scripts/acceptance-matrix.mjs           # check refs + rewrite the doc
 *   node scripts/acceptance-matrix.mjs --check   # check refs only (CI)
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const appRoot = path.join(path.dirname(fileURLToPath(import.meta.url)), "..");
const specPath = path.join(appRoot, "docs", "sprint3-acceptance.json");
const outPath = path.join(appRoot, "docs", "sprint3-acceptance.md");
const checkOnly = process.argv.includes("--check");

const spec = JSON.parse(fs.readFileSync(specPath, "utf8"));
const problems = [];
const fileCache = new Map();

function readSource(rel) {
  if (!fileCache.has(rel)) {
    const abs = path.join(appRoot, rel);
    fileCache.set(rel, fs.existsSync(abs) ? fs.readFileSync(abs, "utf8") : null);
  }
  return fileCache.get(rel);
}

/** Resolve one evidence reference, recording why it failed rather than throwing. */
function resolve(evidence, where) {
  const level = spec.levels[evidence.level];
  if (!level) {
    problems.push(`${where}: unknown level "${evidence.level}"`);
    return { ...evidence, ok: false, runs: "manual" };
  }
  if (!evidence.file) {
    // A recorded fact (merged PR, deploy) has no file to resolve.
    return { ...evidence, ok: true, runs: level.runs, label: evidence.note ?? "recorded" };
  }
  const source = readSource(evidence.file);
  if (source === null) {
    problems.push(`${where}: missing file ${evidence.file}`);
    return { ...evidence, ok: false, runs: level.runs };
  }
  if (evidence.name && !source.includes(evidence.name)) {
    problems.push(`${where}: ${evidence.file} no longer contains "${evidence.name}"`);
    return { ...evidence, ok: false, runs: level.runs };
  }
  return { ...evidence, ok: true, runs: level.runs, label: evidence.name ?? evidence.file };
}

const CADENCE = {
  pr: "✅ PR",
  nightly: "🌙 nightly",
  manual: "🖐 manual",
};
const STATUS = {
  pr: "✅ every PR",
  nightly: "🌙 nightly / on demand",
  manual: "🖐 manual",
  gap: "❌ no evidence",
  withdrawn: "⊘ withdrawn",
};

/**
 * A criterion is graded by which cadences its evidence actually runs at — all of
 * them, not the best one. "PR + nightly" and "nightly only" are different claims,
 * and collapsing them to the strongest would hide exactly what we set out to see.
 *
 * A criterion marked `"withdrawn": true` describes something the product no
 * longer has, by decision; its gapNote says which. It keeps its row as the record
 * of what was accepted, and any evidence it lists is still resolved, but it counts
 * neither as covered nor as a gap: a test of what remains of it does not check it.
 */
function gradeCriterion(criterion, where) {
  const evidence = (criterion.evidence ?? []).map((e, i) => resolve(e, `${where} evidence[${i}]`));
  if (criterion.withdrawn) {
    if (!criterion.gapNote) problems.push(`${where}: withdrawn without a gapNote saying why`);
    return { ...criterion, evidence, cadences: [], status: "withdrawn" };
  }
  const cadences = ["pr", "nightly", "manual"].filter((c) => evidence.some((e) => e.runs === c));
  return {
    ...criterion,
    evidence,
    cadences,
    status: cadences.length === 0 ? "gap" : cadences.includes("pr") ? "pr" : cadences[0],
  };
}

function gradeTicket(ticket, group) {
  const criteria = (ticket.criteria ?? []).map((c, i) =>
    gradeCriterion(c, `#${ticket.id} ${group} criterion[${i}]`),
  );
  return { ...ticket, criteria };
}

const tickets = (spec.tickets ?? []).map((t) => gradeTicket(t, "scope"));
const extras = (spec.alsoShippedInSprint3 ?? []).map((t) => gradeTicket(t, "extra"));
const allCriteria = [...tickets, ...extras].flatMap((t) => t.criteria);
const counts = allCriteria.reduce((acc, c) => ({ ...acc, [c.status]: (acc[c.status] ?? 0) + 1 }), {});
const deepOnly = allCriteria.filter((c) => c.cadences.length > 0 && !c.cadences.includes("pr"));

function evidenceCell(criterion) {
  if (criterion.evidence.length === 0) return "—";
  return criterion.evidence
    .map((e) => {
      const mark = e.ok ? "" : " ⚠️ **broken ref**";
      const where = e.file ? `\`${e.level}\` ${path.basename(e.file)} › ${e.label}` : `\`${e.level}\` ${e.label}`;
      return `${where}${mark}`;
    })
    .join("<br>");
}

function ticketSection(ticket) {
  const lines = [
    `### #${ticket.id} — ${ticket.title}${ticket.days ? ` (${ticket.days} d)` : ""}`,
    "",
  ];
  if (ticket.criteria.length === 0) {
    lines.push("No acceptance criteria — nothing to verify.", "");
    return lines;
  }
  lines.push("| Acceptance criterion | Verified by | Runs |", "|---|---|---|");
  for (const c of ticket.criteria) {
    const runs =
      c.status === "withdrawn"
        ? STATUS.withdrawn
        : c.cadences.length === 0
          ? STATUS.gap
          : c.cadences.map((x) => CADENCE[x]).join(" + ");
    lines.push(`| ${c.text}<br><sub>${c.source}</sub> | ${evidenceCell(c)} | ${runs} |`);
  }
  lines.push("");
  for (const c of ticket.criteria) {
    if (c.gapNote) lines.push(`> **${c.text}** — ${c.gapNote}`, "");
  }
  return lines;
}

const md = [
  `# ${spec.sprint} — acceptance matrix`,
  "",
  "<!-- Generated by scripts/acceptance-matrix.mjs from sprint3-acceptance.json. Do not edit by hand. -->",
  "",
  `**Scope source:** ${spec.scopeSource}`,
  "",
  `**Definition of done:** ${spec.definitionOfDone}`,
  "",
  `**Coverage of ${allCriteria.length} criteria:** ${counts.pr ?? 0} have a check that runs on every PR · ${deepOnly.length} are covered only at a deeper level that does not run per PR · ${counts.gap ?? 0} have no evidence at all${counts.withdrawn ? ` · ${counts.withdrawn} withdrawn: no longer in the product` : ""}.`,
  "",
  ...(deepOnly.length > 0
    ? [
        "Covered only outside the PR build — a green CI does not speak for these:",
        "",
        ...deepOnly.map((c) => `- ${c.text} (${c.cadences.map((x) => CADENCE[x]).join(" + ")})`),
        "",
      ]
    : []),
  ...(counts.gap
    ? [
        "No evidence at all:",
        "",
        ...allCriteria.filter((c) => c.status === "gap").map((c) => `- ${c.text}`),
        "",
      ]
    : []),
  ...(counts.withdrawn
    ? [
        "Withdrawn — kept as the record of what was accepted; the product no longer has them:",
        "",
        ...allCriteria.filter((c) => c.status === "withdrawn").map((c) => `- ${c.text}`),
        "",
      ]
    : []),
  "## How each level runs",
  "",
  "| Level | Command | Runs |",
  "|---|---|---|",
  ...Object.entries(spec.levels).map(
    ([, l]) => `| ${l.label} | ${l.command ? `\`${l.command}\`` : "—"} | ${STATUS[l.runs]} |`,
  ),
  "",
  "All commands are run from `implementation_layer/solution_wizard_v2`.",
  "",
  "## Sprint 3 scope (7 Sep plan)",
  "",
  ...tickets.flatMap(ticketSection),
  "## Also shipped in Sprint 3 (not in the 7 Sep plan)",
  "",
  ...extras.flatMap(ticketSection),
  "## Use-case acceptance (the customer's own measure)",
  "",
  "Fixtures live in the customer use-case bundle outside this repo. A use case counts as",
  "verified when a run of the wizard against its fixture produces a PoC package and the",
  "run artifacts are stored beside the fixture.",
  "",
  "| Use case | Fixtures | Run recorded |",
  "|---|---|---|",
  ...(spec.useCases ?? []).map(
    (u) => `| **${u.id}** — ${u.title} | \`${u.fixtures}\` | ${u.run ? `\`${u.run}\`` : "❌ not run"} |`,
  ),
  "",
  `**${(spec.useCases ?? []).filter((u) => u.run).length} of ${(spec.useCases ?? []).length}** use cases have a recorded run.`,
  "",
].join("\n");

if (problems.length > 0) {
  console.error("Acceptance matrix has broken references:\n");
  for (const p of problems) console.error(`  - ${p}`);
  console.error("\nFix the reference or update docs/sprint3-acceptance.json.");
}

if (!checkOnly) {
  fs.writeFileSync(outPath, md);
  console.log(`wrote ${path.relative(appRoot, outPath)}`);
}
console.log(
  `${allCriteria.length} criteria: ${counts.pr ?? 0} checked per PR, ${deepOnly.length} deeper-level only, ${counts.gap ?? 0} unverified, ${counts.withdrawn ?? 0} withdrawn`,
);
process.exit(problems.length > 0 ? 1 : 0);
