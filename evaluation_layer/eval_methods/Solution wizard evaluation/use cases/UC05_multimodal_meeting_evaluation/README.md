# UC05 Multimodal Meeting-to-Action Register Evaluation

This package evaluates whether the GAIK Solution Configuration Wizard can turn a plain-language meeting-record use case into a correct, traceable, valid, and executable solution package. The scenario combines an English meeting recording, a detailed agenda PDF, and a participant JSON file. The required output is a structured meeting record with decisions, actions, unresolved issues, conflicts, and source citations.

Run the wizard twice in independent sessions. Both runs use the same frozen prompt, scripted answers, fixture, oracle, and confirmation policy. The original unmodified PoC is attempt 0 and permanently determines EQ4. If it fails, the separate recovery diagnostic permits at most three wizard refinements.

## Evaluation questions

| Question | What is assessed | Scored checks |
|---|---|---:|
| EQ1 | Requirement capture recall | 42 per run |
| EQ2 | GAIK configuration constraint satisfaction | 9 per run |
| EQ3 | Validity and completeness of the generated solution package | 8 per run |
| EQ4 | Successful execution and semantic correctness of the original PoC | 4 per run |

Three unscored EQ1 diagnostics check whether unspecified provider, retention, deployment, SLA, and scale values are kept unknown or clearly labelled as assumptions. PoC recovery is also unscored.

## Package structure

```text
UC05_multimodal_meeting_evaluation/
├── README.md
├── initial_prompt.txt
├── scripted_answers.json
├── scripted_answers.md
├── scenario_oracle.json
├── wizard_requirement_coverage.json
├── wizard_requirement_coverage.md
├── package_manifest.json
├── fixtures/
│   ├── poc_input_bundle.json
│   ├── expected_meeting_record.json
│   ├── expected_meeting_record.schema.json
│   ├── reference_transcript.json
│   ├── input/
│   │   ├── project_nimbus_meeting.wav
│   │   ├── project_nimbus_agenda.pdf
│   │   └── project_nimbus_participants.json
│   └── source_material/
├── runs/
│   ├── run_01/
│   └── run_02/
├── scripts/
├── schemas/
├── templates/comparison_template.xlsx
└── results/
```

## What each component does

### `initial_prompt.txt`

The frozen use-case description given to the wizard at the beginning of each run. Do not expand it with information from the oracle.

### `scripted_answers.json` and `scripted_answers.md`

The controlled answers used only when the wizard asks a matching question. They standardize both runs without volunteering information the wizard did not elicit. The sheet covers users and process, objectives, inputs, output schema, provenance, human review, employee interaction, boundaries, operational expectations, and the PoC goal.

For an unexpected question, answer exactly:

> Not specified for this evaluation. If a value is required, record it as an explicit assumption for user confirmation.

At every routine confirmation gate, answer exactly:

> Yes. Proceed without changes.

This prevents evaluator corrections from improving the original wizard output before attempt 0.

### `scenario_oracle.json`

The frozen evaluator-only reference. It defines the expected requirements, acceptable configuration constraints, package checks, execution checks, scoring rules, and recovery policy. Never give it to the wizard.

### `wizard_requirement_coverage.json` and `.md`

These files map required wizard topics to scripted answers and oracle checks. They help verify that the scripted sheet is complete. They are evaluator-only.

### `fixtures/`

The frozen PoC test material:

- `poc_input_bundle.json` gives relative paths to the three runtime inputs.
- `project_nimbus_meeting.wav` is a synthetic 4-minute-10-second meeting. It begins with a natural introduction round in which each participant states their name, role, and responsibility once. The five voices use strongly differentiated base voices, pitch, formant, spectral, and cadence profiles to support diarization. Later discussion uses ordinary first-person statements and first-name references.
- `project_nimbus_agenda.pdf` is a detailed three-page agenda containing planned items, including proposals later changed during the meeting.
- `project_nimbus_participants.json` contains the authorized participant names and roles.
- `expected_meeting_record.json` is the semantic reference output.
- `expected_meeting_record.schema.json` describes the required output structure.
- `reference_transcript.json` documents the frozen audio content and timestamps for evaluator verification.

The source-material scripts make the fixtures reproducible. Do not regenerate them during a run.

### `runs/run_01/` and `runs/run_02/`

Each run folder stores one independent wizard conversation, the complete original generated package, attempt-0 execution evidence, and any refinement snapshots. `run_metadata.json` contains only the PoC execution configuration and normally requires no editing.

Attempt directories preserve each refined package separately:

```text
runs/run_0X/refinement/attempt_01/generated_package/
runs/run_0X/refinement/attempt_02/generated_package/
runs/run_0X/refinement/attempt_03/generated_package/
```

### `scripts/`

- `validate_evaluation_package.py` checks package structure and frozen-policy consistency.
- `run_poc_evaluation.py` executes attempt 0 or a refinement, saves logs and JSON evidence, and maintains `poc_recovery.json`.
- `collect_evidence.py` aligns oracle checks with conversation, blueprint, generated files, validator output, and execution records. It does not assign human verdicts.
- `build_workbook.py` populates the comparison workbook from `results/comparison_data.json`.
- `score_workbook.py` reads the human Yes/No verdicts, writes `results/UC05_scores.json`, and updates the Summary sheet.

### `templates/comparison_template.xlsx`

The eight-sheet evaluator workbook: Instructions, Summary, EQ1 Requirements, EQ1 Diagnostics, EQ2 Configuration, EQ3 Package, EQ4 Execution, and PoC Recovery.

## What the wizard receives and when

| Stage | Give to the wizard | Do not give |
|---|---|---|
| Start of each run | Contents of `initial_prompt.txt` | Oracle, expected output, coverage mapping |
| Follow-up questions | Only the matching answer from `scripted_answers.md` | Answers to questions not asked |
| PoC fixture discussion or generation | `fixtures/poc_input_bundle.json` and the three files it references | `expected_meeting_record.json`, schema, reference transcript |
| Routine confirmation | `Yes. Proceed without changes.` | Evaluator corrections or hints |
| Failed execution refinement | The preceding `poc_execution.log` and relevant error evidence | Corrective source code or new requirements |

If the wizard cannot access the evaluation directory, copy the bundle and its three referenced inputs into its workspace while preserving their relative layout. The wizard must receive the actual files, not only path names.

## Run procedure

Run all commands from the extracted package root. PowerShell commands are shown.

### 1. Validate the frozen package

```powershell
python .\scripts\validate_evaluation_package.py --strict
```

### 2. Conduct Run 1

Start a new wizard session. Give it `initial_prompt.txt`, answer matching questions from `scripted_answers.md`, and use the fixed confirmation answer. Save the full conversation as:

```text
runs/run_01/conversation.txt
```

Save the complete original wizard output under:

```text
runs/run_01/generated_package/
```

The expected top-level artifacts normally include a JSON blueprint, BPMN and Mermaid workflow views, `poc/`, schemas, prompts, evaluation assets, and documentation.

### 3. Conduct Run 2

Repeat the same procedure in a fresh session and save the material under `runs/run_02/`. Do not reuse the first conversation.

### 4. Check the PoC command configuration

Both run metadata files expect the generated PoC to support:

```powershell
python run_poc.py --input <absolute-path-to-poc_input_bundle.json>
```

The evaluator script substitutes `{fixture}` automatically. Edit only `poc.setup_command`, `poc.run_command`, `poc.fixture`, or `poc.output_globs` if the generated PoC documents a different interface. Do not change the PoC to make attempt 0 pass.

### 5. Execute both original PoCs

```powershell
python .\scripts\run_poc_evaluation.py --run-dir .\runs\run_01 --attempt 0
python .\scripts\run_poc_evaluation.py --run-dir .\runs\run_02 --attempt 0
```

The script resolves the package root and bundle path automatically. It records the resolved commands, exit codes, output files, and logs. Attempt 0 alone determines EQ4.

### 6. Refine only if attempt 0 is unsuccessful

An attempt is unsuccessful if it fails to execute, produces no non-empty parseable JSON, or produces semantically incorrect mandatory output. For a semantic failure, record the reason using the script's `--force-unsuccessful` option if available, or set `forced_unsuccessful_reason` in the attempt-0 execution evidence before beginning recovery.

Give only the failure evidence to the wizard. Save the complete refined package in the matching attempt folder, then run:

```powershell
python .\scripts\run_poc_evaluation.py --run-dir .\runs\run_01 --attempt 1
```

Use attempts 2 and 3 only if the previous refinement fails. Repeat independently for Run 2. Stop after the first successful refinement. The diagnostic records `0`, `1`, `2`, `3`, or `N/A`; it never changes EQ4.

### 7. Collect evidence

Deterministic collection:

```powershell
python .\scripts\collect_evidence.py --run all
```

Optional LLM-assisted semantic alignment:

```powershell
python -m pip install -r .\requirements-optional.txt
$env:OPENAI_API_KEY="your-key"
python .\scripts\collect_evidence.py --run all --use-llm --model gpt-5-mini
```

The LLM may locate evidence, but it does not assign Yes or No.

### 8. Build the comparison workbook

```powershell
python .\scripts\build_workbook.py
```

This creates `results/UC05_comparison.xlsx`.

### 9. Enter human verdicts

Open `results/UC05_comparison.xlsx`. For every scored EQ1-EQ4 row, compare the oracle value with each run's generated value and evidence. Enter only `Yes` or `No` in `Run 1 verdict` and `Run 2 verdict`. Evaluator notes are optional. Do not enter verdicts on the PoC Recovery sheet.

### 10. Calculate scores

```powershell
python .\scripts\score_workbook.py
```

This creates `results/UC05_scores.json` and writes the same statistics into the workbook Summary sheet. If a required verdict is blank, scoring is marked incomplete and the missing cells are reported.

## Scoring interpretation

- EQ1 is pooled row-level recall: Yes verdicts divided by 84 judgments across two runs.
- EQ2 is pooled constraint satisfaction: Yes verdicts divided by 18 judgments.
- EQ3 uses an all-mandatory-checks rule per run. A run passes only if all eight EQ3 verdicts are Yes.
- EQ4 uses the same all-mandatory-checks rule for attempt 0. A run passes only if all four EQ4 verdicts are Yes.
- Recovery reports whether an unsuccessful original PoC became successful within three refinements.

## Expected final outputs

```text
runs/run_01/evaluation_results.json
runs/run_02/evaluation_results.json
runs/run_01/poc_recovery.json
runs/run_02/poc_recovery.json
results/comparison_data.json
results/UC05_comparison.xlsx
results/UC05_scores.json
```

Keep the original conversations, generated packages, execution logs, human-completed workbook, and score JSON together as the auditable evaluation record.
