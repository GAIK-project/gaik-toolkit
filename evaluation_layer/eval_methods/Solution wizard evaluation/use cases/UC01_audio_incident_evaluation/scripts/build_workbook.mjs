#!/usr/bin/env node
/**
 * Build the side-by-side UC01 review workbook with @oai/artifact-tool.
 *
 * Usage:
 *   node scripts/build_workbook.mjs
 *   node scripts/build_workbook.mjs results/comparison_data.json results/UC01_comparison.xlsx
 */

import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const packageRoot = path.resolve(scriptDir, "..");
const positionalArgs = process.argv.slice(2).filter((argument) => !argument.startsWith("--"));
const comparisonPath = path.resolve(
  positionalArgs[0] || path.join(packageRoot, "results", "comparison_data.json"),
);
const outputPath = path.resolve(
  positionalArgs[1] || path.join(packageRoot, "results", "UC01_comparison.xlsx"),
);
const templateMode = process.argv.includes("--template");
const previewArgument = process.argv.find((argument) => argument.startsWith("--preview-dir="));
const previewDir = previewArgument
  ? path.resolve(previewArgument.slice("--preview-dir=".length))
  : null;

const oracle = JSON.parse(
  await fs.readFile(path.join(packageRoot, "scenario_oracle.json"), "utf8"),
);
let comparison = { runs: {} };
try {
  comparison = JSON.parse(await fs.readFile(comparisonPath, "utf8"));
} catch {
  comparison = { runs: {} };
}

const workbook = Workbook.create();
workbook.worksheets.add("Instructions");
workbook.worksheets.add("Summary");
workbook.worksheets.add("EQ1 Requirements");
workbook.worksheets.add("EQ1 Diagnostics");
workbook.worksheets.add("EQ2 Configuration");
workbook.worksheets.add("EQ3 Package");
workbook.worksheets.add("EQ4 Execution");
workbook.worksheets.add("PoC Recovery");

const colors = {
  navy: "#17365D",
  blue: "#D9EAF7",
  paleBlue: "#EEF5FB",
  green: "#E2F0D9",
  red: "#FCE4D6",
  amber: "#FFF2CC",
  gray: "#E7E6E6",
  darkGray: "#595959",
  white: "#FFFFFF",
};

function titleBand(sheet, title, subtitle) {
  sheet.getRange("A1:N1").merge();
  sheet.getRange("A1").values = [[title]];
  sheet.getRange("A1:N1").format = {
    fill: colors.navy,
    font: { bold: true, color: colors.white, size: 16 },
    verticalAlignment: "center",
  };
  sheet.getRange("A1:N1").format.rowHeight = 28;
  sheet.getRange("A2:N2").merge();
  sheet.getRange("A2").values = [[subtitle]];
  sheet.getRange("A2:N2").format = {
    fill: colors.paleBlue,
    font: { italic: true, color: colors.darkGray, size: 10 },
    wrapText: true,
    verticalAlignment: "center",
  };
  sheet.getRange("A2:N2").format.rowHeight = 40;
  sheet.showGridLines = false;
}

function resultRows(group) {
  const run1 = comparison?.runs?.run_01?.results?.[group] || [];
  const run2 = comparison?.runs?.run_02?.results?.[group] || [];
  return {
    run1: new Map(run1.map((row) => [row.check_id, row])),
    run2: new Map(run2.map((row) => [row.check_id, row])),
  };
}

function writeEvaluationSheet(sheetName, group, checks, subtitle) {
  const sheet = workbook.worksheets.getItem(sheetName);
  titleBand(sheet, sheetName, subtitle);
  const headers = [
    "Scored?",
    "Check ID",
    "Oracle parameter",
    "Oracle expected value",
    "Oracle evidence/source",
    "Run 1 generated value",
    "Run 1 evidence",
    "Run 1 auto aid",
    "Run 1 verdict",
    "Run 2 generated value",
    "Run 2 evidence",
    "Run 2 auto aid",
    "Run 2 verdict",
    "Evaluator notes",
  ];
  sheet.getRange("A3:N3").values = [headers];
  sheet.getRange("A3:N3").format = {
    fill: colors.blue,
    font: { bold: true, color: colors.navy },
    wrapText: true,
    verticalAlignment: "center",
    borders: { preset: "all", style: "thin", color: "#B4C6E7" },
  };
  sheet.getRange("A3:N3").format.rowHeight = 34;

  const { run1, run2 } = resultRows(group);
  const rows = checks.map((check) => {
    const r1 = run1.get(check.id) || {};
    const r2 = run2.get(check.id) || {};
    const source = Array.isArray(check.source)
      ? check.source.join("; ")
      : Array.isArray(check.evidence_required)
        ? check.evidence_required.join("; ")
        : "";
    return [
      check.scored === false ? "No" : "Yes",
      check.id,
      check.parameter,
      typeof check.oracle_value === "string"
        ? check.oracle_value
        : JSON.stringify(check.oracle_value),
      source,
      r1.generated_value || "",
      r1.evidence || "",
      r1.automatic_result || "",
      r1.human_verdict || "",
      r2.generated_value || "",
      r2.evidence || "",
      r2.automatic_result || "",
      r2.human_verdict || "",
      [r1.evaluator_notes, r2.evaluator_notes].filter(Boolean).join(" | "),
    ];
  });
  const lastRow = 3 + rows.length;
  if (rows.length) {
    sheet.getRange(`A4:N${lastRow}`).values = rows;
    sheet.getRange(`A4:N${lastRow}`).format = {
      wrapText: true,
      verticalAlignment: "top",
      borders: { preset: "all", style: "thin", color: "#D9E1F2" },
    };
    sheet.getRange(`A4:N${lastRow}`).format.rowHeight = 72;
    sheet.getRange(`I4:I${lastRow}`).dataValidation = {
      rule: { type: "list", values: ["Yes", "No"] },
    };
    sheet.getRange(`M4:M${lastRow}`).dataValidation = {
      rule: { type: "list", values: ["Yes", "No"] },
    };
    for (const verdictRange of [`I4:I${lastRow}`, `M4:M${lastRow}`]) {
      sheet.getRange(verdictRange).conditionalFormats.add("cellIs", {
        operator: "equalTo",
        formula: '"Yes"',
        format: { fill: colors.green, font: { bold: true, color: "#375623" } },
      });
      sheet.getRange(verdictRange).conditionalFormats.add("cellIs", {
        operator: "equalTo",
        formula: '"No"',
        format: { fill: colors.red, font: { bold: true, color: "#9C0006" } },
      });
    }
    sheet.getRange(`H4:H${lastRow}`).format.fill = colors.gray;
    sheet.getRange(`L4:L${lastRow}`).format.fill = colors.gray;
  }
  const widths = [9, 13, 24, 34, 26, 34, 46, 13, 13, 34, 46, 13, 13, 28];
  widths.forEach((width, index) => {
    sheet.getRangeByIndexes(0, index, lastRow, 1).format.columnWidth = width;
  });
  sheet.freezePanes.freezeRows(3);
  sheet.freezePanes.freezeColumns(2);
  sheet.getRange(`A3:N${lastRow}`).format.autofitRows();
  return { firstRow: 4, lastRow };
}

const ranges = {};
ranges.eq1 = writeEvaluationSheet(
  "EQ1 Requirements",
  "EQ1",
  oracle.checks.EQ1,
  "Requirement capture recall. Review semantically equivalent values; an omitted oracle requirement remains a row and receives No.",
);
ranges.diag = writeEvaluationSheet(
  "EQ1 Diagnostics",
  "EQ1_diagnostics",
  oracle.checks.EQ1_diagnostics,
  "Unscored transparency diagnostic for unsupported commitments. Evidence is still mandatory.",
);
ranges.eq2 = writeEvaluationSheet(
  "EQ2 Configuration",
  "EQ2",
  oracle.checks.EQ2,
  "GAIK module/component constraints and behavior-changing options.",
);
ranges.eq3 = writeEvaluationSheet(
  "EQ3 Package",
  "EQ3",
  oracle.checks.EQ3,
  "A run is a valid solution package only when every mandatory EQ3 check receives Yes.",
);
ranges.eq4 = writeEvaluationSheet(
  "EQ4 Execution",
  "EQ4",
  oracle.checks.EQ4,
  "A run is a successful PoC only when every mandatory EQ4 check for the original unmodified PoC receives Yes.",
);

const recoverySheet = workbook.worksheets.getItem("PoC Recovery");
titleBand(
  recoverySheet,
  "PoC recovery diagnostic",
  "Unscored diagnostic. EQ4 remains based on the original unmodified PoC; recovery permits at most three wizard refinement attempts.",
);
recoverySheet.getRange("A3:H3").values = [[
  "Diagnostic",
  "Run 1 value",
  "Run 1 evidence",
  "Run 2 value",
  "Run 2 evidence",
  "Protocol value",
  "Scored?",
  "Interpretation",
]];
recoverySheet.getRange("A3:H3").format = {
  fill: colors.blue,
  font: { bold: true, color: colors.navy },
  wrapText: true,
  verticalAlignment: "center",
  borders: { preset: "all", style: "thin", color: "#B4C6E7" },
};
const recovery1 = comparison?.runs?.run_01?.recovery_diagnostic || {};
const recovery2 = comparison?.runs?.run_02?.recovery_diagnostic || {};
const displayValue = (value) => {
  if (value === true) return "Yes";
  if (value === false) return "No";
  if (value === null || value === undefined) return "";
  return String(value);
};
recoverySheet.getRange("A4:H7").values = [
  [
    "Original execution successful",
    displayValue(recovery1.initial_execution_successful),
    recovery1.evidence || "",
    displayValue(recovery2.initial_execution_successful),
    recovery2.evidence || "",
    "Yes or No",
    "No",
    "The original execution remains the EQ4 evidence source.",
  ],
  [
    "Refinement attempts to success",
    displayValue(recovery1.refinement_attempts_to_success),
    recovery1.evidence || "",
    displayValue(recovery2.refinement_attempts_to_success),
    recovery2.evidence || "",
    "0, 1, 2, 3, or N/A",
    "No",
    "0 means original success; N/A means never successful after three refinements.",
  ],
  [
    "Final execution successful",
    displayValue(recovery1.final_execution_successful),
    recovery1.evidence || "",
    displayValue(recovery2.final_execution_successful),
    recovery2.evidence || "",
    "Yes, No, or blank",
    "No",
    "Shows whether recovery ultimately produced an executable PoC.",
  ],
  [
    "Recovery status",
    displayValue(recovery1.status),
    recovery1.evidence || "",
    displayValue(recovery2.status),
    recovery2.evidence || "",
    "Protocol-controlled status",
    "No",
    "Stop after first success or after refinement attempt 3.",
  ],
];
recoverySheet.getRange("A4:H7").format = {
  wrapText: true,
  verticalAlignment: "top",
  borders: { preset: "all", style: "thin", color: "#D9E1F2" },
};
recoverySheet.getRange("A4:H7").format.rowHeight = 76;
[30, 18, 56, 18, 56, 25, 12, 48].forEach((width, index) => {
  recoverySheet.getRangeByIndexes(0, index, 7, 1).format.columnWidth = width;
});
recoverySheet.getRange("G4:G7").format.fill = colors.gray;
recoverySheet.freezePanes.freezeRows(3);
recoverySheet.showGridLines = false;

const instructions = workbook.worksheets.getItem("Instructions");
titleBand(
  instructions,
  "UC01 evaluation review workbook",
  "The workbook displays oracle and wizard evidence side by side. Automated aids never replace the evaluator's Yes/No verdict.",
);
instructions.getRange("A4:B19").values = [
  ["Step", "Action"],
  ["1", "For each run, select its generated_package folder; then send initial_prompt.txt and use scripted_answers.md. No path or provenance metadata needs to be entered. At every routine confirmation, answer Yes and proceed without changes."],
  ["2", "Save each conversation and complete generated package under runs/run_01 and runs/run_02."],
  ["3", "Run run_poc_evaluation.py with attempt 0. This original, unmodified execution is the only execution used for EQ4."],
  ["4", "If attempt 0 fails, return its execution evidence to the wizard and run refinement attempts 1-3 in order. Stop at first success."],
  ["5", "If all three refinements fail, poc_recovery.json records N/A. Refined success never overwrites EQ4."],
  ["6", "Run collect_evidence.py --run all. Use --use-llm only to locate/align evidence; the LLM does not decide verdicts."],
  ["7", "Rebuild this workbook with build_workbook.mjs so the Run 1 and Run 2 value/evidence columns are populated."],
  ["8", "For every scored row, compare the oracle value with the generated value and inspect the adjacent evidence."],
  ["9", "Enter Yes only when the generated result satisfies the accepted meaning. Enter No when it does not or when it is missing."],
  ["10", "For missing requirements, keep NOT FOUND and its search evidence; do not remove the row. It remains in the denominator."],
  ["11", "The Auto aid column reports deterministic pass/fail/needs_review evidence. It is not the final verdict."],
  ["12", "Run score_workbook.mjs after every scored row in both runs has a Yes or No verdict."],
  ["Evidence rule", "Every verdict must be supported by an adjacent JSON path/value, conversation line, file check, command/exit code, log excerpt, or output comparison."],
  ["EQ1", "Requirement capture recall = pooled Yes verdicts / pooled scored requirement checks across two runs."],
  ["EQ2", "Configuration constraint satisfaction = pooled Yes verdicts / pooled configuration checks across two runs."],
];
instructions.getRange("A4:B19").format = {
  wrapText: true,
  verticalAlignment: "top",
  borders: { preset: "all", style: "thin", color: "#D9E1F2" },
};
instructions.getRange("A4:B4").format = {
  fill: colors.blue,
  font: { bold: true, color: colors.navy },
};
instructions.getRange("A4:A19").format.columnWidth = 18;
instructions.getRange("B4:B19").format.columnWidth = 110;
instructions.getRange("A4:B19").format.autofitRows();
instructions.freezePanes.freezeRows(3);

const summary = workbook.worksheets.getItem("Summary");
titleBand(
  summary,
  "UC01 evaluation summary",
  "Scores appear only after all required human verdicts are entered. EQ3 and EQ4 use an all-mandatory-checks pass rule per run.",
);
summary.getRange("A4:H4").values = [[
  "EQ",
  "Metric",
  "Run 1",
  "Run 2",
  "Combined score",
  "Completed verdicts",
  "Required verdicts",
  "Interpretation",
]];
summary.getRange("A5:H8").values = [
  ["EQ1", "Requirement capture recall", "", "", "", "", "", "Pooled row-level recall"],
  ["EQ2", "Configuration constraint satisfaction", "", "", "", "", "", "Pooled constraint satisfaction"],
  ["EQ3", "Valid solution package rate", "", "", "", "", "", "Run passes only if all EQ3 rows are Yes"],
  ["EQ4", "PoC execution success rate", "", "", "", "", "", "Run passes only if all EQ4 rows are Yes"],
];
summary.getRange("A4:H8").format = {
  wrapText: true,
  verticalAlignment: "center",
  borders: { preset: "all", style: "thin", color: "#B4C6E7" },
};
summary.getRange("A4:H4").format = {
  fill: colors.blue,
  font: { bold: true, color: colors.navy },
};

function eqRowFormula(summaryRow, sheetName, range, binary) {
  const r1 = `'${sheetName}'!I${range.firstRow}:I${range.lastRow}`;
  const r2 = `'${sheetName}'!M${range.firstRow}:M${range.lastRow}`;
  const count = range.lastRow - range.firstRow + 1;
  const completed1 = `COUNTIF(${r1},"Yes")+COUNTIF(${r1},"No")`;
  const completed2 = `COUNTIF(${r2},"Yes")+COUNTIF(${r2},"No")`;
  if (binary) {
    summary.getRange(`C${summaryRow}`).formulas = [[`=IF(${completed1}=${count},IF(COUNTIF(${r1},"No")=0,1,0),"")`]];
    summary.getRange(`D${summaryRow}`).formulas = [[`=IF(${completed2}=${count},IF(COUNTIF(${r2},"No")=0,1,0),"")`]];
    summary.getRange(`E${summaryRow}`).formulas = [[`=IF(AND(ISNUMBER(C${summaryRow}),ISNUMBER(D${summaryRow})),AVERAGE(C${summaryRow}:D${summaryRow}),"")`]];
  } else {
    summary.getRange(`C${summaryRow}`).formulas = [[`=IF(${completed1}=${count},COUNTIF(${r1},"Yes")/${count},"")`]];
    summary.getRange(`D${summaryRow}`).formulas = [[`=IF(${completed2}=${count},COUNTIF(${r2},"Yes")/${count},"")`]];
    summary.getRange(`E${summaryRow}`).formulas = [[`=IF(AND(ISNUMBER(C${summaryRow}),ISNUMBER(D${summaryRow})),(COUNTIF(${r1},"Yes")+COUNTIF(${r2},"Yes"))/${count * 2},"")`]];
  }
  summary.getRange(`F${summaryRow}`).formulas = [[`=${completed1}+${completed2}`]];
  summary.getRange(`G${summaryRow}`).values = [[count * 2]];
}

eqRowFormula(5, "EQ1 Requirements", ranges.eq1, false);
eqRowFormula(6, "EQ2 Configuration", ranges.eq2, false);
eqRowFormula(7, "EQ3 Package", ranges.eq3, true);
eqRowFormula(8, "EQ4 Execution", ranges.eq4, true);
summary.getRange("C5:E8").format.numberFormat = [["0%"]];
summary.getRange("C5:E8").format.fill = colors.paleBlue;
summary.getRange("A10:H14").values = [
  ["Diagnostic", "Run 1", "Run 2", "Reporting", "", "", "", "Not included in headline scores"],
  ["Unsupported assumptions", "", "", "Yes/No diagnostic verdict counts", "", "", "", "Review provider/model, retention, SLA/scale commitments"],
  ["Refinement attempts to success", displayValue(recovery1.refinement_attempts_to_success), displayValue(recovery2.refinement_attempts_to_success), "0, 1, 2, 3, or N/A", "", "", "", "Original EQ4 is unchanged"],
  ["Recovery status", displayValue(recovery1.status), displayValue(recovery2.status), "Initially successful, recovered, pending, or unsuccessful", "", "", "", "Maximum three refinement attempts"],
  ["Note", "", "", "", "", "", "", "Blank verdicts mean the evaluation is incomplete, not zero performance."],
];
summary.getRange("B11").formulas = [[`="Yes: "&COUNTIF('EQ1 Diagnostics'!I${ranges.diag.firstRow}:I${ranges.diag.lastRow},"Yes")&"; No: "&COUNTIF('EQ1 Diagnostics'!I${ranges.diag.firstRow}:I${ranges.diag.lastRow},"No")`]];
summary.getRange("C11").formulas = [[`="Yes: "&COUNTIF('EQ1 Diagnostics'!M${ranges.diag.firstRow}:M${ranges.diag.lastRow},"Yes")&"; No: "&COUNTIF('EQ1 Diagnostics'!M${ranges.diag.firstRow}:M${ranges.diag.lastRow},"No")`]];
summary.getRange("A10:H14").format = {
  wrapText: true,
  borders: { preset: "all", style: "thin", color: "#D9E1F2" },
};
summary.getRange("A10:H10").format = {
  fill: colors.amber,
  font: { bold: true, color: colors.navy },
};
[10, 28, 14, 14, 17, 17, 17, 52].forEach((width, index) => {
  summary.getRangeByIndexes(0, index, 14, 1).format.columnWidth = width;
});
summary.getRange("A4:H14").format.autofitRows();
summary.freezePanes.freezeRows(4);

const summaryInspection = await workbook.inspect({
  kind: "table",
  range: "Summary!A1:H14",
  include: "values,formulas",
  tableMaxRows: 14,
  tableMaxCols: 8,
});
console.log(summaryInspection.ndjson);

const formulaErrors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 300 },
  summary: "final formula error scan",
});
if (formulaErrors.ndjson && !formulaErrors.ndjson.includes('"matches":[]')) {
  console.log(formulaErrors.ndjson);
}

if (previewDir) {
  await fs.mkdir(previewDir, { recursive: true });
  for (const sheetName of [
    "Instructions",
    "Summary",
    "EQ1 Requirements",
    "EQ1 Diagnostics",
    "EQ2 Configuration",
    "EQ3 Package",
    "EQ4 Execution",
    "PoC Recovery",
  ]) {
    const preview = await workbook.render({
      sheetName,
      autoCrop: "all",
      scale: 1,
      format: "png",
    });
    const safeName = sheetName.toLowerCase().replaceAll(" ", "_");
    await fs.writeFile(
      path.join(previewDir, `${safeName}.png`),
      new Uint8Array(await preview.arrayBuffer()),
    );
  }
  console.log(`Rendered workbook sheets to ${previewDir}`);
}

await fs.mkdir(path.dirname(outputPath), { recursive: true });
const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);
console.log(`Wrote ${outputPath}${templateMode ? " (template mode)" : ""}`);
