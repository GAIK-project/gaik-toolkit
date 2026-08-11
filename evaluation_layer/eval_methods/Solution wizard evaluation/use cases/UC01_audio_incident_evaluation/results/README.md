# Generated evaluation results

`collect_evidence.py` writes `comparison_data.json` here, including the unscored PoC recovery diagnostic. `build_workbook.mjs` reads that file and writes a populated Excel review workbook. `score_workbook.mjs` reads the evaluator's Yes/No verdicts and writes `UC01_scores.json`, preserving recovery separately from EQ4.

Do not hand-edit `comparison_data.json`; regenerate it from the two run directories.
