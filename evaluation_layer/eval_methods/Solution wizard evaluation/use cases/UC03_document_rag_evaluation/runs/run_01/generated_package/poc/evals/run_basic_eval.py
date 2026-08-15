"""Basic evaluation script for Manufacturing Knowledge Assistant.

Evaluation framework: RAG_eval (deterministic acceptance test)
Rewritten by the wizard agent for this use case's specific 4-query acceptance
criteria (see evaluation_requirements in the blueprint's technical_spec) --
the generic scaffolded eval script does not know about role-based access
control or the required-fact / forbidden-fact / citation checks below.

Usage:
    python evals/run_basic_eval.py

Checks output/answer_records.json (written by run_poc.py) against
evals/ground_truth/expected_results.json for each query:
  - access_decision matches exactly (allowed | denied)
  - every required_fact appears (case-insensitive) in the answer text
  - no forbidden_fact appears anywhere in the answer text (denied queries only)
  - every required_citation is present in the record's citations list
  - a denied record has an empty citations list
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def _citation_key(c) -> tuple:
    return (c[0], c[1])


def evaluate_record(record: dict, expected: dict) -> list[str]:
    """Return a list of failure messages (empty list = pass)."""
    failures = []

    if record.get("access_decision") != expected["access_decision"]:
        failures.append(
            f"access_decision: expected '{expected['access_decision']}', "
            f"got '{record.get('access_decision')}'"
        )

    answer_text = (record.get("answer") or "").lower()

    for fact in expected.get("required_facts", []):
        if fact.lower() not in answer_text:
            failures.append(f"missing required fact: '{fact}'")

    for fact in expected.get("forbidden_facts", []):
        if fact.lower() in answer_text:
            failures.append(f"leaked forbidden fact: '{fact}'")

    actual_citations = {_citation_key(c) for c in record.get("citations", [])}
    required_citations = {_citation_key(c) for c in expected.get("required_citations", [])}
    missing_citations = required_citations - actual_citations
    if missing_citations:
        failures.append(f"missing required citation(s): {sorted(missing_citations)}")

    if expected["access_decision"] == "denied" and record.get("citations"):
        failures.append(f"denied record must have empty citations, got: {record.get('citations')}")

    return failures


def run_evaluation(output_path: Path, ground_truth_path: Path) -> bool:
    if not output_path.exists():
        print(f"No output file found at {output_path}")
        print("Run run_poc.py first to generate output.")
        return False

    if not ground_truth_path.exists():
        print(f"No ground truth file found at {ground_truth_path}")
        return False

    records = {r["query_id"]: r for r in json.loads(output_path.read_text(encoding="utf-8"))}
    expected_results = json.loads(ground_truth_path.read_text(encoding="utf-8"))["expected_results"]

    print(f"Evaluation framework: RAG_eval (deterministic acceptance test, {len(expected_results)} queries)\n")

    all_passed = True
    for expected in expected_results:
        query_id = expected["query_id"]
        record = records.get(query_id)
        if record is None:
            print(f"[FAIL] {query_id}: no output record found")
            all_passed = False
            continue

        failures = evaluate_record(record, expected)
        if failures:
            all_passed = False
            print(f"[FAIL] {query_id} (role={expected['role']}):")
            for f in failures:
                print(f"         - {f}")
        else:
            print(f"[PASS] {query_id} (role={expected['role']}): access_decision={record['access_decision']}")

    print()
    print("ALL CHECKS PASSED" if all_passed else "SOME CHECKS FAILED -- see details above")
    return all_passed


if __name__ == "__main__":
    root = Path(__file__).parent.parent
    output_path = root / "output" / "answer_records.json"
    ground_truth_path = root / "evals" / "ground_truth" / "expected_results.json"
    passed = run_evaluation(output_path, ground_truth_path)
    sys.exit(0 if passed else 1)
