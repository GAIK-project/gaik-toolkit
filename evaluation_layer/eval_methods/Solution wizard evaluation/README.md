# GAIK Solution Configuration Wizard Evaluation

## Purpose

The package in the folder `wizard evaluation template` is a reusable skeleton for evaluating the GAIK Solution Configuration Wizard on one use case. It supports two independent wizard runs, four scored evaluation questions, human Yes/No judgments, original-PoC execution, and a separate recovery diagnostic with a maximum of three refinement attempts.

The template is intentionally use-case neutral. Replace every `UCXX` and `[REPLACE ...]` placeholder before conducting an evaluation. Freeze the adapted package before starting either wizard run. Both runs must use the same initial prompt, scripted answers, fixtures, oracle, and evaluator policy.

**The folder `use cases' contains the evaluation of 4 GenAI use cases using the same evaluation package.**

## Evaluation Model

The package separates controlled input, evaluator-only assessment material, generated evidence, and human judgment.

| Element | Purpose | Shown to the wizard? |
|---|---|---|
| Initial prompt | Starts the use-case conversation | Yes |
| Scripted answers | Standardizes answers to follow-up questions | Only when the corresponding question is asked |
| Input fixtures | Provide the concrete material needed to build or execute the PoC | Only the files required by the PoC |
| Scenario oracle | Defines expected requirements, configurations, package checks, and execution checks | No |
| Expected output | Supports semantic assessment of PoC results | No |
| Coverage mapping | Checks that required wizard fields have a controlled source | No |
| Comparison workbook | Presents oracle values, generated values, evidence, and human verdict cells | No |

The evaluator does not volunteer a scripted answer if the wizard never asks for it. If the wizard asks about an uncovered issue, the evaluator responds: **Not specified for this evaluation. If a value is required, record it as an explicit assumption for user confirmation.** At routine confirmation gates, the evaluator answers: **Yes. Proceed without changes.** This prevents evaluator corrections from improving the wizard output before attempt 0 and keeps the two runs comparable.

## Evaluation Questions

| Evaluation question | Meaning | Calculation |
|---|---|---|
| EQ1 | Requirement capture recall | Yes verdicts divided by all scored EQ1 requirement checks |
| EQ2 | Configuration constraint satisfaction | Yes verdicts divided by all scored EQ2 constraints |
| EQ3 | Valid solution package rate | A run passes only when every mandatory EQ3 package check is Yes |
| EQ4 | Original PoC execution success rate | A run passes only when every mandatory attempt-0 execution check is Yes |

Unsupported assumptions and PoC recovery are diagnostics. They are reported separately and are not included in the four headline scores. A refined PoC never replaces or improves the original EQ4 result.

## Directory Structure

```text
GAIK_wizard_evaluation_template/
├── README.md
├── package_manifest.json
├── initial_prompt.txt
├── scripted_answers.json
├── scripted_answers.md
├── scenario_oracle.json
├── wizard_requirement_coverage.json
├── wizard_requirement_coverage.md
├── requirements.txt
├── requirements-optional.txt
├── fixtures/
│   ├── README.md
│   ├── expected_output.json
│   └── input/
├── schemas/
├── scripts/
├── templates/
│   └── comparison_template.xlsx
├── runs/
│   ├── run_01/
│   └── run_02/
└── results/
```

## Component Reference

### `initial_prompt.txt`

Contains the frozen plain-language use-case description given at the beginning of each wizard run. It should describe the problem and intended outcome without revealing the expected GAIK configuration, evaluation checks, or expected PoC output.

### `scripted_answers.json` and `scripted_answers.md`

Contain the same controlled answers in machine-readable and reviewer-friendly forms. Each answer has an identifier, trigger, response, and covered oracle checks. The template includes explicit placeholders for employee interaction, human review and return handling, and the PoC goal, interface, fixtures, and acceptance criteria. These topics should be retained only when relevant to the use case.

Keep the JSON and Markdown versions synchronized. The JSON file is the machine-readable source. Use stable answer identifiers such as `SA01`, `SA02`, and so on.

### `scenario_oracle.json`

Defines the evaluator-controlled reference for the use case. It contains:

- EQ1 requirement facts derived from the initial prompt and scripted answers;
- unscored unsupported-assumption diagnostics;
- EQ2 GAIK configuration constraints;
- EQ3 package-validity checks;
- EQ4 attempt-0 execution checks; and
- the PoC recovery policy.

Each check should have a unique identifier, clear parameter name, expected meaning, evidence source, and scored status. EQ1 checks may also include acceptable equivalents and possible blueprint paths. EQ2 checks may include acceptable architectures, prohibited combinations, required options, and workflow-order constraints.

Set `frozen_before_runs` to `true` only after the oracle, scripted answers, fixtures, and coverage mapping have been reviewed. Do not change the oracle after seeing wizard output unless the original oracle contains a documented error. Any such correction must be applied consistently to both runs and reported.

### `wizard_requirement_coverage.json` and `.md`

Map required wizard fields to the controlled information sources and oracle checks. Use these files to identify gaps in the scripted answer sheet before starting the runs. For example:

```text
technical_spec.runtime_interface → SA04 → EQ1-R04
```

Update both files whenever scripted answers or oracle checks change. Validation ensures that mapped answer and check identifiers exist.

### `fixtures/`

Contains frozen PoC inputs and evaluator-only expected outputs. Put execution inputs under `fixtures/input/`. Store the semantic reference under `fixtures/expected_output.json`.

When a use case needs several documents, create a relative-path manifest or bundle. Verify that every referenced file exists. Do not embed absolute paths from the evaluator's computer. The wizard may receive the input documents and their runtime manifest when needed, but it must not receive `expected_output.json`.

### `runs/run_01/` and `runs/run_02/`

Store independent wizard sessions. Each run contains:

- `conversation.txt`: complete wizard interaction;
- `run_metadata.json`: PoC execution configuration;
- `generated_package/`: original wizard output used for attempt 0;
- `poc_execution.json` and `.log`: generated baseline execution evidence;
- `poc_recovery.json`: generated recovery status;
- `evaluation_results.json`: aligned run evidence; and
- `refinement/`: up to three refined package snapshots.

The second run must start in a new wizard session. Do not reuse the first conversation or expose its output.

### `run_metadata.json`

This file contains only execution settings. It normally requires changes only after inspecting the PoC interface generated by the wizard.

```json
{
  "poc": {
    "working_directory": "poc",
    "setup_command": ["python", "-m", "pip", "install", "-r", "requirements.txt"],
    "run_command": ["python", "run_poc.py", "--input", "{fixture}"],
    "fixture": "fixtures/input/sample.pdf",
    "output_globs": ["output/**/*.json", "output/*.json"]
  }
}
```

`{fixture}`, `{package_root}`, and `{generated_package}` are resolved automatically. The first `python` token is replaced with the interpreter executing the evaluation script. Do not add an `--input` argument unless the generated `run_poc.py` actually accepts it.

If the PoC reads from a fixed `sample_input` directory, use a command without `--input` and copy only the required frozen fixture files into that directory before execution:

```json
"run_command": ["python", "run_poc.py"]
```

The same execution configuration is used for refined attempts unless the wizard explicitly changes the documented PoC interface. Preserve such interface changes within the refined package and document them in the refinement conversation.

### `refinement/attempt_01` to `attempt_03`

Each refinement folder preserves one feedback cycle. Store the preceding execution error in `feedback_to_wizard.txt`, the complete interaction in `conversation.txt`, and the complete refined package in `generated_package/`. Attempts must run sequentially and stop after the first successful execution.

### `scripts/validate_evaluation_package.py`

Checks required files, JSON syntax, unique check identifiers, coverage references, run configuration, confirmation policy, recovery policy, and Python syntax. Use `--strict` after replacing all template placeholders.

### `scripts/run_poc_evaluation.py`

Runs setup and PoC commands, captures standard output and errors, verifies output files, and updates recovery status. It also sets UTF-8 environment variables to reduce Windows console failures caused by Unicode arrows or box-drawing characters.

The script automatically determines which package to execute:

| Attempt | Executed package |
|---|---|
| 0 | `runs/run_0X/generated_package/` |
| 1 | `runs/run_0X/refinement/attempt_01/generated_package/` |
| 2 | `runs/run_0X/refinement/attempt_02/generated_package/` |
| 3 | `runs/run_0X/refinement/attempt_03/generated_package/` |

Technical success does not guarantee semantic correctness. If a PoC exits successfully and produces parseable output but the output is incorrect, record the attempt as unsuccessful when executing it:

```powershell
python .\scripts\run_poc_evaluation.py --run-dir .\runs\run_01 --attempt 0 --force-unsuccessful "Generated output did not satisfy the frozen expected facts."
```

This preserves the reason in `poc_execution.json` and permits refinement without manually editing evidence files.

### `scripts/collect_evidence.py`

Combines the scenario oracle, conversations, blueprint fields, package files, validator output, PoC execution evidence, and recovery records. It generates one `evaluation_results.json` per run and `results/comparison_data.json` across both runs. The script aligns evidence but does not assign human Yes/No verdicts.

Deterministic collection is the default. Optional LLM-assisted alignment is available for semantically equivalent information stored in free-text fields or unexpected paths. The LLM receives the oracle checks and collected source corpus only to identify generated values and evidence. It must not decide the final verdict.

### `templates/comparison_template.xlsx`

Shows the workbook structure and formatting. The generated workbook contains eight sheets:

1. Instructions
2. Summary
3. EQ1 Requirements
4. EQ1 Diagnostics
5. EQ2 Configuration
6. EQ3 Package
7. EQ4 Execution
8. PoC Recovery

Only `Run 1 verdict` and `Run 2 verdict` are mandatory human inputs. Enter `Yes` or `No`. Evaluator notes are optional. The yellow verdict cells contain data validation.

### `scripts/build_workbook.py`

Builds the populated comparison workbook from `results/comparison_data.json`. It uses the public `openpyxl` package declared in `requirements.txt`; no Node.js or private package is required.

### `scripts/score_workbook.py`

Reads the completed verdict columns, calculates EQ1–EQ4, writes `results/UCXX_scores.json`, and updates the workbook's Summary sheet with the same values. It reports missing verdicts rather than treating blanks as zero performance.

## Adapting the Template to a New Use Case

1. Copy the template folder and rename it for the use case.
2. Replace `UCXX` consistently in JSON files and run identifiers.
3. Write and freeze `initial_prompt.txt`.
4. Replace the scripted-answer placeholders. Add, remove, or split answers as needed.
5. Define all EQ1–EQ4 checks in `scenario_oracle.json`.
6. Update both coverage-mapping files.
7. Add realistic frozen fixtures and expected semantic output.
8. Configure the default PoC interface in both `run_metadata.json` files. The configuration may be adjusted after generation only to match the PoC's documented interface; do not repair the PoC itself before attempt 0.
9. Set `frozen_before_runs` to `true`.
10. Validate with `--strict` before beginning Run 1.

## Installation

Python 3.10 or newer is recommended. From the package root, run:

```powershell
python -m pip install -r .\requirements.txt
```

For optional LLM-assisted evidence alignment:

```powershell
python -m pip install -r .\requirements-optional.txt
$env:OPENAI_API_KEY = "your-key"
```

Keep credentials in environment variables. Do not store keys in the evaluation package.

## Complete Run Procedure

### 1. Validate the frozen package

```powershell
python .\scripts\validate_evaluation_package.py --strict
```

### 2. Conduct Run 1

Start a new wizard session, provide `initial_prompt.txt`, and answer follow-up questions only from the scripted sheet. Provide input fixtures when the wizard needs them to generate or configure the PoC. Do not provide the scenario oracle, expected output, coverage mapping, scoring rules, or the other run.

At every routine confirmation gate, answer:

```text
Yes. Proceed without changes.
```

Save the complete conversation in `runs/run_01/conversation.txt` and the complete original package under `runs/run_01/generated_package/`.

### 3. Conduct Run 2

Repeat the same process in a new wizard session and use the `runs/run_02/` folder. Use the same frozen prompt, scripted answers, fixtures, and confirmation policy.

### 4. Check the generated PoC interfaces

Run:

```powershell
python .\runs\run_01\generated_package\poc\run_poc.py --help
python .\runs\run_02\generated_package\poc\run_poc.py --help
```

Compare the documented arguments with each `run_metadata.json`. Update only `working_directory`, commands, fixture reference, and output globs when required. If the PoC uses `sample_input`, copy the required fixtures there and omit `--input` from the command.

### 5. Execute the original PoCs

```powershell
python .\scripts\run_poc_evaluation.py --run-dir .\runs\run_01 --attempt 0
python .\scripts\run_poc_evaluation.py --run-dir .\runs\run_02 --attempt 0
```

Attempt 0 permanently determines EQ4. If its output is technically successful but semantically wrong, rerun the same attempt with `--force-unsuccessful` and a precise reason before starting a refinement.

### 6. Refine only failed PoCs

Give the wizard the preceding execution error and relevant log evidence. Do not provide corrective code or introduce new requirements. Save the complete refined package and conversation in the next attempt folder, then run the corresponding command:

```powershell
python .\scripts\run_poc_evaluation.py --run-dir .\runs\run_01 --attempt 1
```

Use attempts 2 and 3 only if the preceding attempt fails. Stop after the first successful execution. After three failed refinements, the script records `N/A` automatically.

### 7. Collect evidence

Set the API key:

```powershell
[System.Environment]::SetEnvironmentVariable("OPENAI_API_KEY", "sk-...", "User")
```

Run the evidence collection script:

```powershell
python .\scripts\collect_evidence.py --run all --use-llm --model gpt-5.5
```

If the official validator is not found, set the toolkit root before rerunning:

```powershell
$env:GAIK_SOLUTION_WIZARD_ROOT = "C:\path\to\gaik-toolkit"
```

Alternatively, specify `commands.blueprint_validator` in each `run_metadata.json`, using `{blueprint}` as the blueprint-path placeholder.

### 8. Build the comparison workbook

```powershell
python .\scripts\build_workbook.py
```

This script creates `results/UCXX_comparison.xlsx`.

### 9. Enter human verdicts

Open `results/UCXX_comparison.xlsx`. Review the oracle value, generated value, and evidence for every row. Enter only `Yes` or `No` in both verdict columns. Use `No` when a result is missing, contradictory, incomplete, invalid, or unsupported. A `NOT FOUND` value normally receives `No`. Save the workbook without changing its filename.

### 10. Calculate scores and populate the Summary sheet

```powershell
python .\scripts\score_workbook.py
```
The script creates `results/UCXX_scores.json` and writes the calculated statistics into the workbook's Summary sheet.

## Generated Outputs

For each run:

```text
poc_execution.json
poc_execution.log
poc_recovery.json
evaluation_results.json
```

Across both runs:

```text
results/comparison_data.json
results/UCXX_comparison.xlsx
results/UCXX_scores.json
```

## Interpretation of Recovery

| Value | Meaning |
|---|---|
| 0 | The original PoC succeeds |
| 1 | Success after one refinement |
| 2 | Success after two refinements |
| 3 | Success after three refinements |
| N/A | No successful execution after three refinements |

Report the number of originally successful runs, the number recovered within three refinements, and the number remaining unsuccessful. Do not use refined success to revise EQ4.

## Common Problems

### `unrecognized arguments: --input ...`

The generated PoC does not accept the template's default interface. Run `run_poc.py --help`, remove `--input` from `run_metadata.json`, and follow the PoC's documented input convention.

### `No input file found in sample_input`

The PoC expects fixtures inside its own `sample_input` directory. Copy only the frozen files required for the test into that directory and keep the run command as `python run_poc.py`.

### `FileNotFoundError` for a fixture document

Check the fixture manifest and use package-relative paths. Ensure the referenced filename exactly matches the file under `fixtures/input/`. Avoid evaluator-specific absolute paths.

### `UnicodeEncodeError` on Windows

The runner sets `PYTHONUTF8=1` and `PYTHONIOENCODING=utf-8`. If the PoC still fails, replace decorative console characters in the refined PoC, such as arrows or box-drawing lines, with ASCII equivalents. This counts as a refinement when the original PoC has already failed.

### Official validator not executed

This is unavailable evidence, not proof that the blueprint is invalid. Configure `GAIK_SOLUTION_WIZARD_ROOT` or an explicit validator command and rerun evidence collection before assigning the EQ3 validator verdict.

### Workbook Summary remains blank

Enter all required Yes/No verdicts and run `score_workbook.py`. The script both generates the score JSON and updates the Summary sheet.

## Research Integrity

Preserve the original conversations, packages, execution logs, and refinement snapshots. Do not overwrite attempt 0 with a refined package. Do not expose evaluator-only material to the wizard. Record any deviation from the protocol, environment failure, manual intervention, or oracle correction. These controls are necessary for reproducibility and for distinguishing wizard performance from evaluator assistance.
