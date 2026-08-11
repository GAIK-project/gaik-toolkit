# UC03 evaluation package: Document collection to a role-aware RAG assistant

This package evaluates two independent runs of the GAIK Solution Configuration Wizard for one frozen knowledge-access scenario. It tests requirement capture, RAG configuration, package validity, original-PoC execution, grounded page citations, and role-based access behaviour.

## Frozen scenario

Employees query three synthetic internal PDFs. Two documents are available to employee and manager roles; one management-confidential pricing document is manager-only. The assistant must answer from authorised evidence, cite each source using `[file_name, page_number]`, abstain when evidence is missing, and refuse restricted requests without leaking facts or citations.

## Run procedure

Run every command from the extracted package root in PowerShell.

1. Validate the empty package:

   `python .\scripts\validate_evaluation_package.py`

2. Conduct Wizard Run 1 with `runs/run_01/` as the wizard workspace. This gives the wizard access to `runs/run_01/wizard_input/` but not to the package-level oracle, expected results, workbook, or scoring files. Give the wizard `initial_prompt.txt`, use the matching entries in `scripted_answers.md`, and use the fixed confirmation response `Yes. Proceed without changes.` Direct the wizard to write its complete output to `runs/run_01/generated_package/`. Save the complete interaction as `runs/run_01/conversation.txt`.

3. Repeat independently with `runs/run_02/` as the wizard workspace. Use its separate `wizard_input/` copy and write the output to `runs/run_02/generated_package/`.

4. Confirm that each generated PoC supports the required interface stated in SA07:

   `python run_poc.py --input <path-to-poc_input_bundle.json>`

   The input bundle contains only input locations. It does not expose expected results. The evaluation harness replaces `{fixture}` with the absolute path to `fixtures/poc_input_bundle.json`. The default command in both `run_metadata.json` files is therefore:

   `python run_poc.py --input {fixture}`

5. Execute the original PoCs:

   `python .\scripts\run_poc_evaluation.py --run-dir .\runs\run_01 --attempt 0`

   `python .\scripts\run_poc_evaluation.py --run-dir .\runs\run_02 --attempt 0`

   The wizard was explicitly given the required `--input` interface. A PoC that does not implement it is therefore a genuine baseline failure, not a harness configuration error.

6. If an original PoC fails, return only its execution evidence to the wizard. Save each complete refined package under the corresponding `refinement/attempt_0X/generated_package/` directory and execute attempts 1, 2, and 3 sequentially. Stop after success. Recovery does not change EQ4.

7. Collect evidence:

   `python .\scripts\collect_evidence.py --run all`

   Optional semantic alignment: install `requirements-optional.txt`, set `OPENAI_API_KEY`, and add `--use-llm --model gpt-5-mini`. The LLM locates evidence but never enters verdicts.

8. Install the workbook dependency once, then build the workbook:

   `python -m pip install -r requirements-workbook.txt`

   `python .\scripts\build_workbook.py`

9. Open `results/UC03_comparison.xlsx`. Complete only the `Run 1 verdict` and `Run 2 verdict` columns for scored EQ1-EQ4 rows, entering `Yes` or `No`. Evaluator notes are optional. Save under the same filename.

10. Score:

    `python .\scripts\score_workbook.py`

## Citation contract

Every authorised citation is a JSON two-element list:

```json
["file_name.pdf", 3]
```

The first element is the exact PDF filename. The second is the 1-based PDF page number. Section names are not part of the citation metadata. A denied result must contain an empty citations list.

The fixed expected citation pairs are:

| Query | Role | Expected citations |
|---|---|---|
| Q01 | employee | `["employee_travel_policy.pdf", 3]` |
| Q02 | employee | `["mx200_maintenance_manual.pdf", 3]`, `["mx200_maintenance_manual.pdf", 4]` |
| Q03 | employee | Empty list; access denied without restricted leakage |
| Q04 | manager | `["project_aurora_pricing_strategy.pdf", 3]` |

## Measures

| Measure | Checks per run | Meaning |
|---|---:|---|
| EQ1 | 42 | Requirement capture recall |
| EQ2 | 9 | RAG configuration constraint satisfaction |
| EQ3 | 8 | Complete and valid generated solution package |
| EQ4 | 4 | Original PoC setup, execution, JSON output, grounded page citations, and access behaviour |

EQ3-P02 requires the official validator. If it is not auto-discovered, set `GAIK_SOLUTION_WIZARD_ROOT` and rerun evidence collection before deciding the verdict. Exit code 0 with validation passed is a Yes even when non-blocking warnings are present.

The PoC recovery sheet is diagnostic only: 0 means original success, 1-3 means recovery after that many refinements, and N/A means all three refinements failed.

## Main outputs

- `runs/run_01/evaluation_results.json`
- `runs/run_02/evaluation_results.json`
- `results/comparison_data.json`
- `results/UC03_comparison.xlsx`
- `results/UC03_scores.json`
