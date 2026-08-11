# Run 01 PoC recovery

Use this directory only when the original PoC fails. Attempt directories must be used in order. For each attempt:

1. Copy the failed execution evidence into `feedback_to_wizard.txt`.
2. Ask the wizard to diagnose and refine the PoC without adding requirements or receiving corrective code.
3. Save the complete refinement exchange as `conversation.txt`.
4. Save a complete snapshot of the refined wizard package in `generated_package/`.
5. Adjust only `attempt_metadata.json` when the refined package changes its documented command or output path.
6. Run `python scripts/run_poc_evaluation.py --run-dir runs/run_01 --attempt N`.

Stop after the first successful attempt or after attempt 3.
