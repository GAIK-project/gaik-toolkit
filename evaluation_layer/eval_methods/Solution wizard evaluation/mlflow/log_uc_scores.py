# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "mlflow-skinny==3.17.*",
#   "openpyxl>=3.1",
# ]
# ///
"""Log the UC01–UC05 wizard evaluation scores to MLflow.

For each use case and wizard run (run_01, run_02) this logs:

- one MLflow **run**, named ``UC02 run_01``, with the four headline scores as
  metrics (EQ1–EQ4, from ``results/UCxx_scores.json``) and the number of
  failed checks per question;
- **assessments** on that run's ``uc.replay UCxx run_0x`` trace (sent by
  ``replay_uc_runs.py`` in the WP5 demo): the four headline scores, and one
  assessment per scored check the evaluator marked *No*, naming what was
  expected and what the wizard produced. The trace is linked to the run.

The verdicts are the human evaluators' Yes/No cells in
``results/UCxx_comparison.xlsx``; the headline scores in the JSON are checked
against them, and a mismatch stops the script. Without a replay trace the run
is still logged and the assessments are skipped.

This is for the synthetic UC test data only, never customer data: the check
assessments carry expected and produced values in plain text.

Run ``uv run log_uc_scores.py`` with ``MLFLOW_TRACKING_URI`` set
(default ``http://127.0.0.1:5000``). A use case already logged is skipped,
except that its assessments are added if its replay trace has arrived since.
``--replace`` logs it again in place of the old run and its assessments. A
run that fails half-way is deleted, so the next run logs it again.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

USE_CASES = Path(__file__).resolve().parent.parent / "use cases"
EXPERIMENT = "wizard-v2-api"  # where the uc.replay traces are
SOURCE_ID = "uc-comparison-workbook"
RUNS = ("run_01", "run_02")

#: question -> (sheet, metric name, all checks must pass)
QUESTIONS = {
    "EQ1": ("EQ1 Requirements", "eq1_requirement_recall", False),
    "EQ2": ("EQ2 Configuration", "eq2_constraint_satisfaction", False),
    "EQ3": ("EQ3 Package", "eq3_valid_package", True),
    "EQ4": ("EQ4 Execution", "eq4_poc_execution", True),
}
LABELS = {
    "EQ1": "EQ1 requirement recall",
    "EQ2": "EQ2 constraint satisfaction",
    "EQ3": "EQ3 valid package",
    "EQ4": "EQ4 PoC execution",
}
MAX_TEXT = 300


@dataclass
class Check:
    check_id: str
    question: str
    parameter: str
    expected: str
    produced: str
    passed: bool


@dataclass
class RunScores:
    uc: str
    run: str
    scores: dict[str, float]
    checks_per_question: dict[str, int]
    failed: list[Check] = field(default_factory=list)
    recovery: dict[str, str] = field(default_factory=dict)

    @property
    def key(self) -> str:
        return f"{self.uc}/{self.run}"


def _text(value: object) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= MAX_TEXT else text[: MAX_TEXT - 1] + "…"


def read_checks(workbook_path: Path) -> dict[str, dict[str, list[Check]]]:
    """Scored checks per question and run, from the evaluator-completed workbook."""
    from openpyxl import load_workbook

    wb = load_workbook(workbook_path, read_only=True, data_only=True)
    result: dict[str, dict[str, list[Check]]] = {}
    for question, (sheet, _, _) in QUESTIONS.items():
        rows = list(wb[sheet].iter_rows(values_only=True))
        header_at = next((i for i, row in enumerate(rows) if "Check ID" in row), None)
        if header_at is None:
            raise ValueError(f"{workbook_path.name} {sheet}: no header row with 'Check ID'")
        col = {name: i for i, name in enumerate(rows[header_at]) if name}
        # UC05's workbook is the older layout: no "Scored?" column (every row
        # is scored) and shorter names for the oracle columns.
        for new, old in (
            ("Oracle parameter", "Parameter"),
            ("Oracle expected value", "Oracle value"),
        ):
            if new not in col and old in col:
                col[new] = col[old]
        needed = ["Oracle parameter", "Oracle expected value"]
        needed += [
            f"Run {n} {what}"
            for n in range(1, len(RUNS) + 1)
            for what in ("verdict", "generated value")
        ]
        missing = [name for name in needed if name not in col]
        if missing:
            raise ValueError(f"{workbook_path.name} {sheet}: missing columns {missing}")
        per_run: dict[str, list[Check]] = {run: [] for run in RUNS}
        for row in rows[header_at + 1 :]:
            if not row[col["Check ID"]]:
                continue
            if "Scored?" in col and str(row[col["Scored?"]] or "").strip().lower() != "yes":
                continue
            for n, run in enumerate(RUNS, start=1):
                verdict = str(row[col[f"Run {n} verdict"]] or "").strip().capitalize()
                if verdict not in ("Yes", "No"):
                    raise ValueError(
                        f"{workbook_path.name} {sheet} {row[col['Check ID']]}: verdict for {run} "
                        f"is {row[col[f'Run {n} verdict']]!r}, not Yes or No"
                    )
                per_run[run].append(
                    Check(
                        check_id=str(row[col["Check ID"]]),
                        question=question,
                        parameter=_text(row[col["Oracle parameter"]]),
                        expected=_text(row[col["Oracle expected value"]]),
                        produced=_text(row[col[f"Run {n} generated value"]]),
                        passed=verdict == "Yes",
                    )
                )
        result[question] = per_run
    return result


def load_use_case(folder: Path) -> list[RunScores]:
    uc = folder.name[:4]
    scores = json.loads((folder / "results" / f"{uc}_scores.json").read_text(encoding="utf-8"))
    if not scores.get("complete"):
        raise ValueError(f"{uc}: scores are not complete")
    checks = read_checks(folder / "results" / f"{uc}_comparison.xlsx")
    recovery = scores.get("diagnostics", {}).get("poc_recovery", {})
    loaded = []
    for run in RUNS:
        run_scores, counts, failed = {}, {}, []
        for question, (_, _, all_must_pass) in QUESTIONS.items():
            run_checks = checks[question][run]
            if not run_checks:
                raise ValueError(f"{uc} {run} {question}: no scored checks in the workbook")
            passed = sum(c.passed for c in run_checks)
            computed = (
                float(passed == len(run_checks)) if all_must_pass else passed / len(run_checks)
            )
            reported = float(scores["metrics"][question][run])
            if abs(computed - reported) > 1e-9:
                raise ValueError(
                    f"{uc} {run} {question}: workbook gives {computed}, scores.json {reported}"
                )
            run_scores[question] = reported
            counts[question] = len(run_checks)
            failed += [c for c in run_checks if not c.passed]
        loaded.append(
            RunScores(
                uc=uc,
                run=run,
                scores=run_scores,
                checks_per_question=counts,
                failed=failed,
                recovery={k: str(v) for k, v in (recovery.get(run) or {}).items() if v is not None},
            )
        )
    return loaded


def find_replay_trace(client, experiment_id: str, uc: str, run: str) -> str | None:
    """The newest ``uc.replay`` trace of this use case and run, if one was sent."""
    traces = client.search_traces(
        locations=[experiment_id],
        filter_string=f"span.name = 'uc.replay {uc} {run}'",
        order_by=["timestamp_ms DESC"],
        max_results=1,
        include_spans=False,
    )
    return traces[0].info.trace_id if traces else None


def existing_run(client, experiment_id: str, key: str):
    runs = client.search_runs(
        [experiment_id],
        filter_string=f"tags.`gaik.eval.key` = '{key}' and attributes.status = 'FINISHED'",
        max_results=1,
    )
    return runs[0] if runs else None


def our_assessments(client, trace_id: str) -> list:
    return [
        a
        for a in client.get_trace(trace_id).info.assessments
        if a.source and a.source.source_id == SOURCE_ID
    ]


def remove_previous(client, experiment_id: str, run, trace_id: str | None) -> None:
    """Delete an earlier run and this script's assessments on its traces.

    The traces linked to the run are cleaned as well as the newest replay
    trace: a replay sent again since then is a new trace, and the old one
    would otherwise keep assessments that point at a deleted run.
    """
    import mlflow

    linked = client.search_traces(
        locations=[experiment_id], run_id=run.info.run_id, include_spans=False
    )
    trace_ids = {t.info.trace_id for t in linked} | ({trace_id} if trace_id else set())
    for tid in trace_ids:
        for assessment in our_assessments(client, tid):
            mlflow.delete_assessment(trace_id=tid, assessment_id=assessment.assessment_id)
    client.delete_run(run.info.run_id)


def add_assessments(client, run_id: str, scores: RunScores, trace_id: str) -> None:
    """Link the replay trace to the run and put the scores and failed checks on it."""
    import mlflow
    from mlflow.entities import AssessmentSource

    client.link_traces_to_run([trace_id], run_id)
    source = AssessmentSource(source_type="HUMAN", source_id=SOURCE_ID)
    for question, value in scores.scores.items():
        mlflow.log_feedback(
            trace_id=trace_id,
            name=LABELS[question],
            value=value,
            source=source,
            metadata={"gaik.uc": scores.uc, "gaik.uc.run": scores.run, "mlflow.run_id": run_id},
        )
    for check in scores.failed:
        mlflow.log_feedback(
            trace_id=trace_id,
            name=check.check_id,
            value=False,
            source=source,
            rationale=f"{check.parameter}: expected {check.expected!r}, got {check.produced!r}",
            metadata={"gaik.eval.question": check.question, "mlflow.run_id": run_id},
        )


def remove_partial_assessments(client, run_id: str, scores: RunScores, trace_id: str) -> None:
    """Take back the assessments this run put on the trace; report, do not raise."""
    try:
        import mlflow

        for assessment in our_assessments(client, trace_id):
            if (assessment.metadata or {}).get("mlflow.run_id") == run_id:
                mlflow.delete_assessment(trace_id=trace_id, assessment_id=assessment.assessment_id)
    except Exception as cleanup:  # noqa: BLE001 - the original error is the one raised
        print(f"{scores.key}: could not remove partial assessments: {cleanup}", file=sys.stderr)


def add_assessments_to_logged(client, run_id: str, scores: RunScores, trace_id: str) -> None:
    """Assessments for a run logged before its replay trace arrived, all or none.

    A half-added set would be taken for a complete one next time (the trace
    already has this script's assessments) and never be finished.
    """
    try:
        add_assessments(client, run_id, scores, trace_id)
    except BaseException:
        remove_partial_assessments(client, run_id, scores, trace_id)
        raise


def log(client, experiment_id: str, scores: RunScores, trace_id: str | None) -> str:
    tags = {
        "gaik.event.class": "evaluation",
        "gaik.eval.key": scores.key,
        "gaik.eval.source": SOURCE_ID,
        "gaik.uc": scores.uc,
        "gaik.uc.run": scores.run,
    }
    run = client.create_run(experiment_id, run_name=f"{scores.uc} {scores.run}", tags=tags)
    run_id = run.info.run_id
    try:
        for question, (_, metric, _) in QUESTIONS.items():
            client.log_metric(run_id, metric, scores.scores[question])
            client.log_metric(
                run_id,
                f"{question.lower()}_failed_checks",
                sum(c.question == question for c in scores.failed),
            )
            client.log_param(
                run_id, f"{question.lower()}_scored_checks", scores.checks_per_question[question]
            )
        for name, value in scores.recovery.items():
            client.log_param(run_id, f"recovery_{name}", value)
        if trace_id:
            add_assessments(client, run_id, scores, trace_id)
        client.set_terminated(run_id)
    except BaseException:
        # A half-logged run would be skipped as "already logged" next time.
        # The run is deleted even when its assessments cannot be cleaned up.
        try:
            if trace_id:
                remove_partial_assessments(client, run_id, scores, trace_id)
        finally:
            client.delete_run(run_id)
        raise
    return run_id


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--experiment", default=EXPERIMENT, help=f"default {EXPERIMENT}")
    parser.add_argument("--only", nargs="*", metavar="UC", help="e.g. UC02 UC04")
    parser.add_argument("--replace", action="store_true", help="log again over an earlier run")
    parser.add_argument("--dry-run", action="store_true", help="read and check, log nothing")
    args = parser.parse_args()

    folders = sorted(p for p in USE_CASES.iterdir() if p.is_dir() and p.name[:2] == "UC")
    if args.only:
        wanted = {uc.upper() for uc in args.only}
        folders = [p for p in folders if p.name[:4] in wanted]
        unknown = wanted - {p.name[:4] for p in folders}
        if unknown:
            print(f"no use case folder for {sorted(unknown)}", file=sys.stderr)
            return 1
    all_scores = [s for folder in folders for s in load_use_case(folder)]

    if args.dry_run:
        for s in all_scores:
            scores = ", ".join(f"{q} {v:.3f}" for q, v in s.scores.items())
            print(f"{s.key}: {scores}; failed: {[c.check_id for c in s.failed]}")
        return 0

    os.environ.setdefault("MLFLOW_TRACKING_URI", "http://127.0.0.1:5000")
    from mlflow import MlflowClient

    client = MlflowClient()
    experiment = client.get_experiment_by_name(args.experiment)
    if experiment is None:
        print(f"no MLflow experiment named {args.experiment!r}", file=sys.stderr)
        return 1
    for s in all_scores:
        trace_id = find_replay_trace(client, experiment.experiment_id, s.uc, s.run)
        previous = existing_run(client, experiment.experiment_id, s.key)
        if previous and not args.replace:
            if trace_id and not our_assessments(client, trace_id):
                # Logged before the replay trace was sent: add what was skipped then.
                add_assessments_to_logged(client, previous.info.run_id, s, trace_id)
                print(f"{s.key}: already logged, assessments added on trace {trace_id}")
            else:
                print(f"{s.key}: already logged (run {previous.info.run_id}), skipped")
            continue
        if previous:
            remove_previous(client, experiment.experiment_id, previous, trace_id)
        run_id = log(client, experiment.experiment_id, s, trace_id)
        note = f"trace {trace_id}" if trace_id else "no replay trace, assessments skipped"
        print(f"{s.key}: run {run_id}, {len(s.failed)} failed checks, {note}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
