# Workbook template

`UC01_comparison_template.xlsx` contains the frozen oracle rows, blank Run 1/Run 2 evidence and verdict columns, and an unscored PoC Recovery sheet. After the two runs, use `scripts/collect_evidence.py --run all`, then `scripts/build_workbook.mjs` to create a populated workbook in `results/`.

Do not delete rows for missing wizard requirements. `NOT FOUND` is valid generated-side evidence and receives a human `No` verdict.
