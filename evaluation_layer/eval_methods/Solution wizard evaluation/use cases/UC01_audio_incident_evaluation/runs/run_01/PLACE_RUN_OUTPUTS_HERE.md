# Run 01 input locations

1. Select this run's `generated_package/` folder when the wizard asks where to write its output.
2. If the wizard uses another workspace, copy its complete, unmodified output into `generated_package/`.
3. Send `initial_prompt.txt` when it asks for the use-case description.
4. Use only the fixed answers in `scripted_answers.md`; answer every routine confirmation “Yes” without changes.
5. Save the complete wizard conversation as `conversation.txt` in this directory.
6. Normally leave `run_metadata.json` unchanged. Edit only its `poc` commands if the generated PoC does not use the documented defaults.
7. Run `scripts/run_poc_evaluation.py --run-dir runs/run_01 --attempt 0`.
8. If it fails, follow `refinement/README.md` for up to three ordered refinement attempts.
9. Run `scripts/collect_evidence.py --run run_01` or `--run all`.

Do not edit the original wizard-generated files. EQ4 always uses attempt 0.
