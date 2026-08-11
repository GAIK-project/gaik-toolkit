#!/usr/bin/env node
/**
 * Read human Yes/No verdicts from the UC01 workbook and calculate final metrics.
 */

import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const packageRoot = path.resolve(scriptDir, "..");
const workbookPath = path.resolve(
  process.argv[2] || path.join(packageRoot, "results", "UC01_comparison.xlsx"),
);
const outputPath = path.resolve(
  process.argv[3] || path.join(packageRoot, "results", "UC01_scores.json"),
);

const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(workbookPath));
const configurations = [
  { eq: "EQ1", sheet: "EQ1 Requirements", binary: false },
  { eq: "EQ2", sheet: "EQ2 Configuration", binary: false },
  { eq: "EQ3", sheet: "EQ3 Package", binary: true },
  { eq: "EQ4", sheet: "EQ4 Execution", binary: true },
];

function normalized(value) {
  return String(value ?? "").trim().toLowerCase();
}

function readRows(sheetName) {
  const sheet = workbook.worksheets.getItem(sheetName);
  const values = sheet.getUsedRange(true).values;
  const rows = [];
  for (let index = 3; index < values.length; index += 1) {
    const row = values[index];
    if (!row?.[1]) continue;
    if (normalized(row[0]) !== "yes") continue;
    rows.push({
      check_id: row[1],
      run_01: normalized(row[8]),
      run_02: normalized(row[12]),
    });
  }
  return rows;
}

const results = {
  schema_version: "1.0.0",
  scenario_id: "UC01",
  source_workbook: workbookPath,
  complete: true,
  metrics: {},
  diagnostics: {},
};

for (const configuration of configurations) {
  const rows = readRows(configuration.sheet);
  const missing = [];
  for (const row of rows) {
    for (const run of ["run_01", "run_02"]) {
      if (!["yes", "no"].includes(row[run])) missing.push(`${row.check_id}:${run}`);
    }
  }
  if (missing.length) {
    results.complete = false;
    results.metrics[configuration.eq] = {
      complete: false,
      missing_verdicts: missing,
    };
    continue;
  }

  const runScores = {};
  for (const run of ["run_01", "run_02"]) {
    const yes = rows.filter((row) => row[run] === "yes").length;
    runScores[run] = configuration.binary
      ? Number(yes === rows.length)
      : yes / rows.length;
  }
  const combined = configuration.binary
    ? (runScores.run_01 + runScores.run_02) / 2
    : rows.reduce(
        (total, row) =>
          total + Number(row.run_01 === "yes") + Number(row.run_02 === "yes"),
        0,
      ) /
      (rows.length * 2);
  results.metrics[configuration.eq] = {
    complete: true,
    scored_checks_per_run: rows.length,
    run_01: runScores.run_01,
    run_02: runScores.run_02,
    combined,
  };
}

const recoveryValues = workbook.worksheets
  .getItem("PoC Recovery")
  .getUsedRange(true)
  .values;
results.diagnostics.poc_recovery = {
  scored_under_EQ4: false,
  maximum_refinement_attempts: 3,
  run_01: {
    initial_execution_successful: recoveryValues?.[3]?.[1] ?? "",
    refinement_attempts_to_success: recoveryValues?.[4]?.[1] ?? "",
    final_execution_successful: recoveryValues?.[5]?.[1] ?? "",
    status: recoveryValues?.[6]?.[1] ?? "",
  },
  run_02: {
    initial_execution_successful: recoveryValues?.[3]?.[3] ?? "",
    refinement_attempts_to_success: recoveryValues?.[4]?.[3] ?? "",
    final_execution_successful: recoveryValues?.[5]?.[3] ?? "",
    status: recoveryValues?.[6]?.[3] ?? "",
  },
};

await fs.mkdir(path.dirname(outputPath), { recursive: true });
await fs.writeFile(outputPath, `${JSON.stringify(results, null, 2)}\n`, "utf8");
console.log(`Wrote ${outputPath}`);
if (!results.complete) {
  console.error("Scoring is incomplete because one or more human verdicts are blank.");
  process.exitCode = 2;
}
