#!/usr/bin/env python3
"""Validate the static UC04 evaluation package."""

from __future__ import annotations

import hashlib
import json
import py_compile
from pathlib import Path


SCENARIO = "UC04"
VERSION = "1.0.0"
SOURCE_FILES = (
    "supplier_kpis_q2_2026.xlsx",
    "nordic_components_quality_audit.pdf",
    "procurement_meeting_notes_q2_2026.md",
    "delivery_incidents_q2_2026.csv",
)


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    required = [
        root / "README.md",
        root / "scenario_oracle.json",
        root / "initial_prompt.txt",
        root / "scripted_answers.json",
        root / "scripted_answers.md",
        root / "wizard_requirement_coverage.json",
        root / "wizard_requirement_coverage.md",
        root / "requirements-workbook.txt",
        root / "fixtures" / "report_test_bundle.json",
        root / "fixtures" / "report_fixture_facts.txt",
        root / "fixtures" / "expected_report_results.json",
        root / "fixtures" / "poc_input_bundle.json",
        root / "fixtures" / "poc_input" / "report_spec.json",
        root / "fixtures" / "poc_input" / "report_template.md",
        root / "fixtures" / "fixture_manifest.json",
        root / "templates" / "UC04_comparison_template.xlsx",
        root / "schemas" / "poc_recovery.schema.json",
        root / "schemas" / "refinement_attempt_metadata.schema.json",
    ]
    required.extend(root / "fixtures" / "poc_input" / "sources" / name for name in SOURCE_FILES)
    for run_number in (1, 2):
        run_name = f"run_{run_number:02d}"
        run_dir = root / "runs" / run_name
        required.extend([
            run_dir / "run_metadata.json",
            run_dir / "poc_recovery.json",
            run_dir / "refinement" / "README.md",
            run_dir / "wizard_input" / "README.md",
            run_dir / "wizard_input" / "poc_input_bundle.json",
            run_dir / "wizard_input" / "poc_input" / "report_spec.json",
            run_dir / "wizard_input" / "poc_input" / "report_template.md",
        ])
        required.extend(run_dir / "wizard_input" / "poc_input" / "sources" / name for name in SOURCE_FILES)
        for attempt in range(1, 4):
            attempt_dir = run_dir / "refinement" / f"attempt_{attempt:02d}"
            required.extend([
                attempt_dir / "attempt_metadata.json",
                attempt_dir / "feedback_to_wizard.txt",
                attempt_dir / "generated_package" / "PLACE_REFINED_PACKAGE_HERE.md",
            ])
    missing = [str(path.relative_to(root)) for path in required if not path.is_file()]
    if missing:
        print(f"Missing required files: {missing}")
        return 1

    oracle = _json(root / "scenario_oracle.json")
    answers = _json(root / "scripted_answers.json")
    coverage = _json(root / "wizard_requirement_coverage.json")
    if any(item.get("scenario_id") != SCENARIO for item in (oracle, answers, coverage)):
        print("Scenario identifiers are inconsistent.")
        return 1
    if oracle.get("oracle_version") != VERSION or answers.get("version") != VERSION:
        print("Oracle and scripted-answer versions are inconsistent.")
        return 1

    expected_counts = {"EQ1": 42, "EQ1_diagnostics": 3, "EQ2": 9, "EQ3": 8, "EQ4": 4}
    actual_counts = {group: len(oracle.get("checks", {}).get(group, [])) for group in expected_counts}
    if actual_counts != expected_counts:
        print(f"Unexpected oracle check counts: {actual_counts}")
        return 1
    check_ids = [check["id"] for checks in oracle["checks"].values() for check in checks]
    if len(check_ids) != len(set(check_ids)):
        print("Oracle check identifiers are not unique.")
        return 1

    answer_ids = [answer["id"] for answer in answers.get("answers", [])]
    if len(answer_ids) != len(set(answer_ids)):
        print("Scripted-answer identifiers are not unique.")
        return 1
    unknown = sorted({
        check_id
        for answer in answers.get("answers", [])
        for check_id in answer.get("supports", [])
        if check_id not in set(check_ids)
    })
    if unknown:
        print(f"Scripted answers reference unknown checks: {unknown}")
        return 1
    if answers.get("confirmation_policy", {}).get("response") != "Yes. Proceed without changes.":
        print("Global confirmation response is incorrect.")
        return 1
    if answers.get("recovery_policy", {}).get("maximum_refinement_attempts") != 3:
        print("Scripted recovery policy must allow exactly three attempts.")
        return 1
    confirmation = coverage.get("confirmation_policy", {})
    if confirmation.get("status") != "covered" or len(confirmation.get("covered_questions", [])) != 7:
        print("Coverage must document seven routine confirmation points.")
        return 1

    expected_fields = {
        "business_spec": {"current_process", "pain_points", "proposed_solution", "intended_users", "reviewers", "stakeholders", "input_artifacts", "target_outputs", "success_criteria", "expected_value", "risks", "poc_goal"},
        "technical_spec": {"input_types", "input_formats", "output_types", "language", "domain_vocabulary", "data_sources", "model_provider", "model_preferences", "security_constraints", "integration_targets", "human_review", "evaluation_requirements", "runtime_interface", "formatted_pdf_question"},
        "target_output_spec": {"schema_name", "fields", "field_types", "required_fields", "optional_fields", "field_descriptions", "allowed_values", "confidence_required", "missing_value_policy", "validation_rules"},
        "business_process": {"participants", "external_parties", "manual_steps", "exceptions", "decision_points"},
    }
    for group, expected in expected_fields.items():
        entries = coverage.get(group, [])
        actual = {entry.get("field") for entry in entries}
        if actual != expected or any(entry.get("status") != "covered" for entry in entries):
            print(f"Coverage mismatch in {group}: missing={sorted(expected-actual)}, extra={sorted(actual-expected)}")
            return 1
        if any("scripted_answers.md" in str(entry.get("source", "")) for entry in entries):
            print(f"{group} must cite scripted_answers.json, not scripted_answers.md.")
            return 1

    expected = _json(root / "fixtures" / "expected_report_results.json")
    if expected.get("required_sections") != [
        "Executive Summary", "KPI Overview", "Supplier Findings",
        "Quality and Delivery Risks", "Actions and Owners", "Source References",
    ]:
        print("Expected report sections are incorrect.")
        return 1
    if set(expected.get("required_source_references", [])) != set(SOURCE_FILES):
        print("Expected source references are incorrect.")
        return 1
    if len(expected.get("required_facts", [])) != 10:
        print("Expected report must contain ten fact groups.")
        return 1

    canonical = root / "fixtures"
    for run_number in (1, 2):
        run_name = f"run_{run_number:02d}"
        run_dir = root / "runs" / run_name
        metadata = _json(run_dir / "run_metadata.json")
        recovery = _json(run_dir / "poc_recovery.json")
        if metadata.get("schema_version") != "1.1.0" or metadata.get("scenario_id") != SCENARIO:
            print(f"{run_name} metadata is invalid.")
            return 1
        if metadata.get("maximum_refinement_attempts") != 3:
            print(f"{run_name} metadata must enforce three attempts.")
            return 1
        if metadata.get("poc", {}).get("run_command") != ["python", "run_poc.py", "--input", "{fixture}"]:
            print(f"{run_name} must use the fixed --input command.")
            return 1
        if metadata.get("poc", {}).get("output_globs") != ["output/report.md", "output/evidence_index.json"]:
            print(f"{run_name} output globs are incorrect.")
            return 1
        if recovery.get("status") != "not_started" or recovery.get("attempts") != []:
            print(f"{run_name} recovery file is not fresh.")
            return 1
        if recovery.get("maximum_refinement_attempts") != 3 or not recovery.get("eq4_uses_baseline_only"):
            print(f"{run_name} recovery policy is inconsistent.")
            return 1
        wizard_input = run_dir / "wizard_input"
        pairs = [
            (canonical / "poc_input_bundle.json", wizard_input / "poc_input_bundle.json"),
            (canonical / "poc_input" / "report_spec.json", wizard_input / "poc_input" / "report_spec.json"),
            (canonical / "poc_input" / "report_template.md", wizard_input / "poc_input" / "report_template.md"),
        ] + [
            (canonical / "poc_input" / "sources" / name, wizard_input / "poc_input" / "sources" / name)
            for name in SOURCE_FILES
        ]
        mismatches = [str(dst.relative_to(root)) for src, dst in pairs if src.read_bytes() != dst.read_bytes()]
        if mismatches:
            print(f"{run_name} wizard-input fixtures differ from canonical copies: {mismatches}")
            return 1
        for attempt in range(1, 4):
            item = _json(run_dir / "refinement" / f"attempt_{attempt:02d}" / "attempt_metadata.json")
            if item.get("attempt_number") != attempt:
                print(f"Wrong attempt number for {run_name} attempt {attempt}.")
                return 1

    manifest = _json(root / "fixtures" / "fixture_manifest.json")
    for relative, recorded in manifest.get("sha256", {}).items():
        path = root / "fixtures" / relative
        if not path.is_file() or _sha256(path) != recorded:
            print(f"Fixture hash mismatch: {relative}")
            return 1

    for script in (root / "scripts").glob("*.py"):
        py_compile.compile(str(script), doraise=True)

    print(
        "Package validation passed. Checks=66; EQ1 requirements=42; "
        "wizard fields covered; report fixtures verified; global confirmation policy and "
        "three-attempt recovery enforced; Python scripts compiled."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
