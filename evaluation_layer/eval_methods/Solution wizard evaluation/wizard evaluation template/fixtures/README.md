# Fixtures

Place frozen evaluation inputs under `fixtures/input/` and the evaluator-controlled expected output in `fixtures/expected_output.json`. Give the wizard only the fixture files required to generate and run the PoC. Do not provide the expected output or scenario oracle.

Use stable filenames and avoid absolute paths inside fixture manifests. If several documents or files are required, add a bundle or manifest containing paths relative to the package root. Verify every referenced file before freezing the package.
