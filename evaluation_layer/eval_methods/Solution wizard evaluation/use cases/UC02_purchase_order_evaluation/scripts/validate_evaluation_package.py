#!/usr/bin/env python3
"""Self-check the static UC02 evaluation package."""

from __future__ import annotations

import hashlib
import json
import py_compile
from pathlib import Path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


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
        root / "fixtures" / "purchase_order_complex.pdf",
        root / "fixtures" / "purchase_order_fixture_facts.txt",
        root / "fixtures" / "expected_erp_record.json",
        root / "templates" / "UC02_comparison_template.xlsx",
        root / "schemas" / "poc_recovery.schema.json",
        root / "schemas" / "refinement_attempt_metadata.schema.json",
        root / "runs" / "run_01" / "run_metadata.json",
        root / "runs" / "run_02" / "run_metadata.json",
        root / "runs" / "run_01" / "poc_recovery.json",
        root / "runs" / "run_02" / "poc_recovery.json",
        root / "runs" / "run_01" / "refinement" / "README.md",
        root / "runs" / "run_02" / "refinement" / "README.md",
    ]
    missing = [str(path.relative_to(root)) for path in required if not path.is_file()]
    if missing:
        print(f"Missing required files: {missing}")
        return 1

    oracle = json.loads((root / "scenario_oracle.json").read_text(encoding="utf-8"))
    answers = json.loads((root / "scripted_answers.json").read_text(encoding="utf-8"))
    coverage = json.loads((root / "wizard_requirement_coverage.json").read_text(encoding="utf-8"))
    if any(document.get("scenario_id") != "UC02" for document in (oracle, answers, coverage)):
        print("Scenario identifiers are inconsistent.")
        return 1
    if oracle.get("oracle_version") != "1.3.0" or answers.get("version") != "1.3.0":
        print("Oracle and scripted-answer versions must both be 1.3.0.")
        return 1

    all_check_ids = [
        check["id"]
        for group in oracle["checks"].values()
        for check in group
    ]
    duplicates = sorted({check_id for check_id in all_check_ids if all_check_ids.count(check_id) > 1})
    if duplicates:
        print(f"Duplicate check IDs: {duplicates}")
        return 1
    check_id_set = set(all_check_ids)

    answer_ids = [answer["id"] for answer in answers.get("answers", [])]
    duplicate_answers = sorted(
        {answer_id for answer_id in answer_ids if answer_ids.count(answer_id) > 1}
    )
    if duplicate_answers:
        print(f"Duplicate scripted-answer IDs: {duplicate_answers}")
        return 1
    unsupported_references = sorted(
        {
            check_id
            for answer in answers.get("answers", [])
            for check_id in answer.get("supports", [])
            if check_id not in check_id_set
        }
    )
    if unsupported_references:
        print(f"Scripted answers reference unknown oracle checks: {unsupported_references}")
        return 1

    confirmation = answers.get("confirmation_policy", {})
    if confirmation.get("response") != "Yes. Proceed without changes.":
        print("The global confirmation policy must use the fixed Yes response.")
        return 1
    if "gate_responses" in answers:
        print("Per-gate responses must not be present; use one global confirmation policy.")
        return 1
    covered_confirmations = coverage.get("confirmation_policy", {}).get("covered_questions", [])
    if len(covered_confirmations) != 7 or coverage.get("confirmation_policy", {}).get("status") != "covered":
        print("Coverage must document seven routine confirmations under one global policy.")
        return 1

    expected_coverage = {
        "business_spec": {
            "current_process",
            "pain_points",
            "proposed_solution",
            "intended_users",
            "reviewers",
            "stakeholders",
            "input_artifacts",
            "target_outputs",
            "success_criteria",
            "expected_value",
            "risks",
            "poc_goal",
        },
        "technical_spec": {
            "input_types",
            "input_formats",
            "output_types",
            "language",
            "domain_vocabulary",
            "data_sources",
            "model_provider",
            "model_preferences",
            "security_constraints",
            "integration_targets",
            "human_review",
            "evaluation_requirements",
            "runtime_interface",
            "formatted_pdf_question",
        },
        "target_output_spec": {
            "schema_name",
            "fields",
            "field_types",
            "required_fields",
            "optional_fields",
            "field_descriptions",
            "allowed_values",
            "confidence_required",
            "missing_value_policy",
            "validation_rules",
        },
        "business_process": {
            "participants",
            "external_parties",
            "manual_steps",
            "exceptions",
            "decision_points",
        },
    }
    for section, expected_fields in expected_coverage.items():
        entries = coverage.get(section, [])
        actual_fields = {entry.get("field") for entry in entries}
        if actual_fields != expected_fields:
            print(
                f"Wizard coverage mismatch for {section}: "
                f"missing={sorted(expected_fields - actual_fields)}, "
                f"extra={sorted(actual_fields - expected_fields)}"
            )
            return 1
        uncovered = [entry["field"] for entry in entries if entry.get("status") != "covered"]
        if uncovered:
            print(f"Uncovered wizard fields in {section}: {uncovered}")
            return 1

    recovery_maxima = {
        oracle.get("protocol", {}).get("recovery_policy", {}).get("maximum_refinement_attempts"),
        answers.get("recovery_policy", {}).get("maximum_refinement_attempts"),
        coverage.get("recovery_policy", {}).get("maximum_refinement_attempts"),
    }
    if recovery_maxima != {3}:
        print(f"Recovery policies must all specify exactly three refinements: {recovery_maxima}")
        return 1

    for run_number in (1, 2):
        run_name = f"run_{run_number:02d}"
        run_dir = root / "runs" / run_name
        run_metadata = json.loads((run_dir / "run_metadata.json").read_text(encoding="utf-8"))
        recovery = json.loads((run_dir / "poc_recovery.json").read_text(encoding="utf-8"))
        if run_metadata.get("schema_version") != "1.1.0":
            print(f"{run_name} must use the simplified run-metadata schema 1.1.0.")
            return 1
        obsolete_fields = {
            "wizard_version",
            "wizard_model",
            "wizard_skill_commit",
            "wizard_skill_path",
            "wizard_output_directory",
            "wizard_workspace_preselected",
            "started_at",
            "completed_at",
            "accept_without_correction",
            "confirmation_policy_followed",
            "run_status",
            "notes",
        }
        present_obsolete = sorted(obsolete_fields & set(run_metadata))
        if present_obsolete:
            print(f"{run_name} contains obsolete manual fields: {present_obsolete}")
            return 1
        if run_metadata.get("maximum_refinement_attempts") != 3:
            print(f"{run_name} metadata does not enforce three refinement attempts.")
            return 1
        if recovery.get("maximum_refinement_attempts") != 3 or not recovery.get("eq4_uses_baseline_only"):
            print(f"{run_name} recovery template is inconsistent with the protocol.")
            return 1
        for attempt in range(1, 4):
            attempt_dir = run_dir / "refinement" / f"attempt_{attempt:02d}"
            attempt_metadata_path = attempt_dir / "attempt_metadata.json"
            feedback_path = attempt_dir / "feedback_to_wizard.txt"
            package_placeholder = attempt_dir / "generated_package" / "PLACE_REFINED_PACKAGE_HERE.md"
            for path in (attempt_metadata_path, feedback_path, package_placeholder):
                if not path.is_file():
                    print(f"Missing refinement template: {path.relative_to(root)}")
                    return 1
            attempt_metadata = json.loads(attempt_metadata_path.read_text(encoding="utf-8"))
            if attempt_metadata.get("attempt_number") != attempt:
                print(f"Wrong attempt number in {attempt_metadata_path.relative_to(root)}")
                return 1

    for script in (root / "scripts").glob("*.py"):
        py_compile.compile(str(script), doraise=True)

    manifest_path = root / "fixtures" / "fixture_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for filename in (
        "purchase_order_complex.pdf",
        "purchase_order_fixture_facts.txt",
        "expected_erp_record.json",
    ):
        manifest["sha256"][filename] = _sha256(root / "fixtures" / filename)
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    print(
        "Package validation passed. "
        f"Checks={len(all_check_ids)}; EQ1 requirements={len(oracle['checks']['EQ1'])}; "
        "wizard fields covered; global confirmation policy and three-attempt recovery enforced; "
        "Python scripts compiled."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
