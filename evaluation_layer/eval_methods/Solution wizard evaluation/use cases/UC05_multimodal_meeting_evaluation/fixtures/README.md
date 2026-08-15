# Fixtures

The frozen runtime bundle is `poc_input_bundle.json`. It references the meeting WAV, agenda PDF, and participant JSON in `input/`. Give these four runtime files to the wizard when it needs the PoC fixture. Keep `expected_meeting_record.json`, its schema, `reference_transcript.json`, and the scenario oracle evaluator-only.

The files under `source_material/` reproduce the synthetic audio and agenda. They are not runtime inputs and should not be regenerated during an evaluation.

Use stable filenames and avoid absolute paths inside fixture manifests. If several documents or files are required, add a bundle or manifest containing paths relative to the package root. Verify every referenced file before freezing the package.
