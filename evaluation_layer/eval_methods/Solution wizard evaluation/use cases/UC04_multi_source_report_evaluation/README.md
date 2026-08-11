# UC04 Multi-Source Report Evaluation

This package evaluates two independent runs of the GAIK Solution Configuration Wizard for a knowledge-synthesis scenario. The wizard must turn mixed procurement evidence into a structured, evidence-grounded supplier-performance report.

## Evaluation design

- EQ1: 42 atomic requirement-capture checks.
- EQ2: 9 configuration constraints.
- EQ3: 8 package-validity checks.
- EQ4: 4 checks of the original unmodified PoC.
- PoC Recovery: unscored technical recovery diagnostic with at most three wizard refinements.

Only attempt 0 determines EQ4. A later recovery never changes EQ4.

## What the wizard receives

At the beginning of each run, use the corresponding run directory as the wizard workspace and expose only its `wizard_input` folder. The wizard receives:

- `poc_input_bundle.json`
- `poc_input/report_spec.json`
- `poc_input/report_template.md`
- `poc_input/sources/supplier_kpis_q2_2026.xlsx`
- `poc_input/sources/nordic_components_quality_audit.pdf`
- `poc_input/sources/procurement_meeting_notes_q2_2026.md`
- `poc_input/sources/delivery_incidents_q2_2026.csv`

Do not expose `scenario_oracle.json`, `expected_report_results.json`, evaluation results, or the comparison workbook.

## Steps

### 1. Validate the fresh package

```powershell
python .\scripts\validate_evaluation_package.py
```

### 2. Conduct Run 1

Use `runs\run_01` as the wizard workspace. Send `initial_prompt.txt` verbatim. Answer questions from `scripted_answers.md`; do not volunteer answers before the matching question. At every routine confirmation say:

> Yes. Proceed without changes.

Save the full conversation as `runs\run_01\conversation.txt`. Save the complete original wizard package under `runs\run_01\generated_package`.

### 3. Conduct Run 2

Repeat independently in a fresh wizard session with `runs\run_02` and save the conversation and package in the corresponding locations.

### 4. Check PoC commands

Normally leave `run_metadata.json` unchanged. The fixed command is:

```text
python run_poc.py --input {fixture}
```

The evaluator replaces `{fixture}` automatically with the absolute path to `fixtures\poc_input_bundle.json`. Edit only the `poc` command or output-glob fields when the generated PoC documents a different interface. Do not modify the PoC itself before attempt 0.

### 5. Execute original PoCs

```powershell
python .\scripts\run_poc_evaluation.py --run-dir .\runs\run_01 --attempt 0
python .\scripts\run_poc_evaluation.py --run-dir .\runs\run_02 --attempt 0
```

Expected outputs are a non-empty `output\report.md` and parseable `output\evidence_index.json`. The script records commands, exit codes, logs, hashes, and output excerpts.

### 6. Perform technical recovery only when original execution fails

Return only the preceding execution error to the wizard. Save each complete refined package under `runs\run_0X\refinement\attempt_0N\generated_package`, save the refinement conversation, and execute attempts sequentially:

```powershell
python .\scripts\run_poc_evaluation.py --run-dir .\runs\run_01 --attempt 1
python .\scripts\run_poc_evaluation.py --run-dir .\runs\run_01 --attempt 2
python .\scripts\run_poc_evaluation.py --run-dir .\runs\run_01 --attempt 3
```

Use the same commands for Run 2 when needed. Stop after the first technical success. Recovery measures execution only; semantic report correctness remains an EQ4-X04 human verdict for attempt 0.

### 7. Collect evidence

Deterministic extraction:

```powershell
python .\scripts\collect_evidence.py --run all
```

Optional LLM-assisted evidence alignment:

```powershell
python -m pip install -r .\requirements-optional.txt
python .\scripts\collect_evidence.py --run all --use-llm --model gpt-5-mini
```

The LLM aligns evidence only; it does not assign Yes or No.

### 8. Build the comparison workbook

```powershell
python -m pip install -r .\requirements-workbook.txt
python .\scripts\build_workbook.py
```

This creates `results\UC04_comparison.xlsx`.

### 9. Enter human verdicts

In EQ1 through EQ4 sheets, fill only `Run 1 verdict` and `Run 2 verdict` with `Yes` or `No`. Evaluator notes are optional. The PoC Recovery sheet is automatic.

### 10. Score the workbook

```powershell
python .\scripts\score_workbook.py
```

This creates `results\UC04_scores.json`. EQ1 and EQ2 are proportions of Yes verdicts. EQ3 and EQ4 are binary per run: a run passes only if every check is Yes.

## What EQ4 means

- X01: original setup succeeds.
- X02: original PoC processes the four-source bundle and exits successfully.
- X03: original PoC creates a new non-empty Markdown report and parseable evidence index.
- X04: original report contains the required structure, exact metrics, decisions, actions, discrepancy handling, source references, and no unsupported claims.

The expected-results file is an evaluator oracle and must never be given to the wizard.
