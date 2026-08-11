# UC02 evaluation package: Complex purchase orders to ERP data

This package evaluates two independent runs of the GAIK Solution Configuration Wizard for one frozen purchase-order scenario. It contains the scenario oracle, exact scripted interaction, a synthetic text-based two-page purchase-order PDF, expected ERP facts, two run workspaces, deterministic package and execution checks, optional LLM-assisted evidence alignment, a portable Excel review workflow, and a scoring script.

The four measures are:

- **EQ1:** requirement capture recall;
- **EQ2:** configuration constraint satisfaction;
- **EQ3:** valid solution package rate;
- **EQ4:** original, unmodified PoC execution success rate.

EQ4 always uses attempt 0. If attempt 0 does not execute successfully, a separate unscored recovery diagnostic permits at most three wizard refinement attempts and records `0`, `1`-`3`, or `N/A`.

## Frozen UC02 scenario

A manufacturing company receives customer purchase orders in varied PDF and scanned formats. The documents include complex tables, hierarchical or merged headers, and line items that may continue across pages. Employees currently enter relevant data manually into ERP. The target solution uses layout-aware extraction to create a consistent ERP-compatible JSON record, provides confidence or uncertainty evidence, and requires internal review before downstream ERP transfer.

The GAIK registry is frozen at commit `79586c93ea3286f68acf3ad3810a370c4295fa01`. For this accuracy-critical and layout-complex scenario, the expected primary component is `VisionExtractor`. The same registry states that such complex documents should use `VisionExtractor` rather than `DocumentsToStructuredData`.

## Run procedure

Run all commands from the extracted package root.

1. Validate the empty package:

   ```powershell
   python .\scripts\validate_evaluation_package.py
   ```

2. Start Wizard Run 1. Select `runs/run_01/generated_package/` as the output folder, send `initial_prompt.txt` verbatim, answer only with the matching content in `scripted_answers.md`, and answer every routine confirmation with:

   > Yes. Proceed without changes.

   Save the complete conversation as `runs/run_01/conversation.txt`. Do not correct the original specification, component choice, workflow, schema, prompt, or PoC.

3. Repeat independently for Run 2 using `runs/run_02/`.

4. Normally leave each `run_metadata.json` unchanged. Edit only `poc.setup_command`, `poc.run_command`, or `poc.output_globs` when the generated PoC documents a different interface.

5. Execute the original PoCs:

   ```powershell
   python .\scripts\run_poc_evaluation.py --run-dir .\runs\run_01 --attempt 0
   python .\scripts\run_poc_evaluation.py --run-dir .\runs\run_02 --attempt 0
   ```

6. If an original PoC fails to execute, return only its recorded error evidence to the wizard. Save each complete refined package in its corresponding `refinement/attempt_0X/generated_package/` folder and run attempts 1, 2, and 3 sequentially. Stop at the first success. Refinement never changes EQ4.

7. Make the official GAIK validator discoverable before evidence collection. In PowerShell, for example:

   ```powershell
   $env:GAIK_SOLUTION_WIZARD_ROOT = "C:\path\to\gaik-toolkit\implementation_layer\solution_wizard"
   ```

   Collect evidence:

   ```powershell
   python .\scripts\collect_evidence.py --run all
   ```

   Optional LLM-assisted evidence alignment:

   ```powershell
   python -m pip install -r .\requirements-optional.txt
   $env:OPENAI_API_KEY = "your-key"
   python .\scripts\collect_evidence.py --run all --use-llm --model gpt-5-mini
   ```

   The LLM may locate semantically equivalent evidence but never assigns the final verdict.

8. Build the comparison workbook without npm or third-party Python packages:

   ```powershell
   python .\scripts\build_workbook.py
   ```

9. Open `results/UC02_comparison.xlsx`. Complete only the `Run 1 verdict` and `Run 2 verdict` columns for scored EQ1-EQ4 rows, using `Yes` or `No`. Evaluator notes are optional. Save the workbook under the same filename.

10. Calculate scores:

    ```powershell
    python .\scripts\score_workbook.py
    ```

    This generates `results/UC02_scores.json`. Blank verdicts make the result incomplete.

## What the package compares

| Measure | Checks per run | Comparison |
|---|---:|---|
| EQ1 | 42 | Frozen business, document, output, review, integration, governance, and PoC requirements |
| EQ2 | 9 | Knowledge-capture classification, `VisionExtractor`, verification, nested schema, non-redundancy, review placement/evidence, and CLI/JSON scope |
| EQ3 | 8 | Blueprint, official validation, artifact flow, Mermaid, BPMN, PoC scaffold, documentation, and traceability |
| EQ4 | 4 | Setup, execution over the supplied PDF, parseable JSON output, and semantic fixture acceptance |

For EQ3-P02, inability to discover the validator is `needs_review`, not evidence that the blueprint is invalid. Run the official validator before assigning the human verdict. Warnings are non-blocking when the validator returns exit code 0 and reports validation passed.

## Main generated files

Per run:

```text
poc_execution.json
poc_execution.log
poc_recovery.json
evaluation_results.json
```

Across both runs:

```text
results/comparison_data.json
results/UC02_comparison.xlsx
results/UC02_scores.json
```

The workbook has eight sheets: Instructions, Summary, EQ1 Requirements, EQ1 Diagnostics, EQ2 Configuration, EQ3 Package, EQ4 Execution, and PoC Recovery. The PoC Recovery sheet is populated automatically and is not scored under EQ4.
