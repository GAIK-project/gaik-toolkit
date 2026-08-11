#!/usr/bin/env python3
"""Validate the structure and internal references of an evaluation package."""

from __future__ import annotations

import argparse
import json
import py_compile
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REQUIRED = [
    "README.md",
    "initial_prompt.txt",
    "scripted_answers.json",
    "scripted_answers.md",
    "scenario_oracle.json",
    "wizard_requirement_coverage.json",
    "wizard_requirement_coverage.md",
    "fixtures/expected_output.json",
    "runs/run_01/run_metadata.json",
    "runs/run_02/run_metadata.json",
    "templates/comparison_template.xlsx",
]


def load_json(relative: str):
    path = ROOT / relative
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ValueError(f"Invalid JSON: {relative}: {exc}") from exc


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true", help="Reject unreplaced template placeholders.")
    args = parser.parse_args()
    errors: list[str] = []

    for relative in REQUIRED:
        if not (ROOT / relative).exists():
            errors.append(f"Missing required path: {relative}")

    if errors:
        print("Package validation failed:\n- " + "\n- ".join(errors), file=sys.stderr)
        return 1

    try:
        oracle = load_json("scenario_oracle.json")
        answers = load_json("scripted_answers.json")
        coverage = load_json("wizard_requirement_coverage.json")
        manifest = load_json("package_manifest.json")
        metadata = [load_json(f"runs/run_0{i}/run_metadata.json") for i in (1, 2)]
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 1

    sections = ["requirements", "diagnostics", "configuration_constraints", "package_checks", "execution_checks"]
    checks = [item for section in sections for item in oracle.get(section, [])]
    ids = [item.get("check_id") for item in checks]
    if len(ids) != len(set(ids)):
        errors.append("Scenario-oracle check identifiers are not unique.")
    if not oracle.get("requirements"):
        errors.append("The oracle must contain at least one EQ1 requirement.")
    if not oracle.get("configuration_constraints"):
        errors.append("The oracle must contain at least one EQ2 constraint.")
    if not oracle.get("package_checks"):
        errors.append("The oracle must contain at least one EQ3 package check.")
    if not oracle.get("execution_checks"):
        errors.append("The oracle must contain at least one EQ4 execution check.")

    policy = oracle.get("recovery_policy", {})
    if policy.get("baseline_attempt") != 0:
        errors.append("The baseline PoC must be attempt 0.")
    if policy.get("maximum_refinement_attempts") != 3:
        errors.append("The recovery limit must be three refinements.")
    if policy.get("eq4_uses_baseline_only") is not True:
        errors.append("EQ4 must use the original baseline only.")
    if manifest.get("confirmation_policy") != "Yes. Proceed without changes.":
        errors.append("The global confirmation policy is incorrect.")

    answer_ids = {item.get("answer_id") for item in answers.get("scripted_answers", [])}
    check_ids = set(ids)
    for mapping in coverage.get("mappings", []):
        for answer_id in mapping.get("scripted_answer_ids", []):
            if answer_id not in answer_ids:
                errors.append(f"Coverage mapping references unknown answer: {answer_id}")
        for check_id in mapping.get("oracle_check_ids", []):
            if check_id not in check_ids:
                errors.append(f"Coverage mapping references unknown check: {check_id}")

    for index, item in enumerate(metadata, start=1):
        if item.get("run_id", "").endswith(f"run_0{index}") is False:
            errors.append(f"Run {index} metadata has an inconsistent run_id.")
        poc = item.get("poc", {})
        if not isinstance(poc.get("run_command"), list) or not poc.get("run_command"):
            errors.append(f"Run {index} has no PoC run command.")
        if not isinstance(poc.get("output_globs"), list) or not poc.get("output_globs"):
            errors.append(f"Run {index} has no PoC output globs.")

    for path in (ROOT / "scripts").glob("*.py"):
        try:
            py_compile.compile(str(path), doraise=True)
        except py_compile.PyCompileError as exc:
            errors.append(f"Python compilation failed for {path.name}: {exc}")

    if args.strict:
        for path in ROOT.rglob("*"):
            if path.is_file() and path.suffix.lower() in {".json", ".md", ".txt"}:
                text = path.read_text(encoding="utf-8", errors="ignore")
                if "[REPLACE" in text or "UCXX" in text:
                    errors.append(f"Template placeholder remains: {path.relative_to(ROOT)}")

    if errors:
        print("Package validation failed:\n- " + "\n- ".join(errors), file=sys.stderr)
        return 1

    counts = {
        "EQ1": sum(c.get("scored", True) and c["check_id"].startswith("EQ1-") for c in checks),
        "EQ2": sum(c.get("scored", True) and c["check_id"].startswith("EQ2-") for c in checks),
        "EQ3": sum(c.get("scored", True) and c["check_id"].startswith("EQ3-") for c in checks),
        "EQ4": sum(c.get("scored", True) and c["check_id"].startswith("EQ4-") for c in checks),
    }
    print(f"Package validation passed. Checks={len(checks)}; scored={counts}; two-run and three-attempt policies enforced.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
