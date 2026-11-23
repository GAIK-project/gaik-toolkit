# UC evaluation scores in MLflow

`log_uc_scores.py` puts the evaluators' scores for UC01–UC05 into MLflow, next to the
`uc.replay` traces of the same wizard runs (WP5 AIOps, "UC evaluations → MLflow").

For each use case and run (`run_01`, `run_02`), in experiment `wizard-v2-api`:

| In MLflow | What |
|---|---|
| Run `UC02 run_01` | Metrics `eq1_requirement_recall`, `eq2_constraint_satisfaction`, `eq3_valid_package`, `eq4_poc_execution`, and `eqN_failed_checks`; the PoC recovery result as params |
| Assessments on the `uc.replay UC02 run_01` trace | The four headline scores, and one per check the evaluator marked *No*, with what was expected and what the wizard produced |
| Trace ↔ run | The trace is linked to the run, so the run's **Traces** tab shows it |

The runs are under **Evaluation runs** in the experiment's sidebar.

The scores come from `results/UCxx_scores.json`, the per-check verdicts from
`results/UCxx_comparison.xlsx`. The script checks that the two agree before logging anything.

Synthetic UC test data only: the check assessments carry expected and produced values as plain
text, so never point this at customer data.

## Run

Needs the gaik-aiops stack running. The `uc.replay` traces come from the WP5 demo's
`replay_uc_runs.py`; without them the runs are logged and the assessments skipped.

```bash
uv run log_uc_scores.py --dry-run
```

```bash
uv run log_uc_scores.py
```

`MLFLOW_TRACKING_URI` defaults to `http://127.0.0.1:5000`.

- A use case already logged is skipped. If its replay trace has arrived since, its assessments
  are added to that trace.
- `--replace` logs it again in place of the old run and its assessments, also on an older replay
  trace of the same run.
- A run that fails half-way is deleted, so the next run logs it again.
- `--only UC02 UC04` limits the run to those use cases.
