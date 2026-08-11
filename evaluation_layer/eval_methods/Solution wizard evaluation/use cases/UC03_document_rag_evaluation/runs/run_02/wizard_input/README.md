# UC03 wizard input bundle

This directory contains the only evaluation inputs that should be made visible to the wizard.

- `poc_input_bundle.json` is the command-line input file.
- Its paths resolve relative to this directory.
- `poc_input/documents/` contains the three PDF documents.
- `poc_input/access_manifest.json` defines document classifications and allowed roles.
- `poc_input/query_set.json` defines the four role-tagged questions.

The generated PoC must support:

```text
python run_poc.py --input <path-to-poc_input_bundle.json>
```

Do not provide the wizard with `scenario_oracle.json`, `expected_rag_results.json`, the comparison workbook, or scoring scripts.
