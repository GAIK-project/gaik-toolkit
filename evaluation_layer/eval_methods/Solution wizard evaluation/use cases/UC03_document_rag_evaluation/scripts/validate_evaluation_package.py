#!/usr/bin/env python3
"""Self-check the static UC03 evaluation package."""

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
        root / "requirements-workbook.txt",
        root / "fixtures" / "rag_test_bundle.json",
        root / "fixtures" / "rag_fixture_facts.txt",
        root / "fixtures" / "expected_rag_results.json",
        root / "fixtures" / "poc_input_bundle.json",
        root / "fixtures" / "poc_input" / "access_manifest.json",
        root / "fixtures" / "poc_input" / "query_set.json",
        root / "fixtures" / "poc_input" / "documents" / "employee_travel_policy.pdf",
        root / "fixtures" / "poc_input" / "documents" / "mx200_maintenance_manual.pdf",
        root / "fixtures" / "poc_input" / "documents" / "project_aurora_pricing_strategy.pdf",
        root / "templates" / "UC03_comparison_template.xlsx",
        root / "schemas" / "poc_recovery.schema.json",
        root / "schemas" / "refinement_attempt_metadata.schema.json",
        root / "runs" / "run_01" / "run_metadata.json",
        root / "runs" / "run_02" / "run_metadata.json",
        root / "runs" / "run_01" / "poc_recovery.json",
        root / "runs" / "run_02" / "poc_recovery.json",
        root / "runs" / "run_01" / "refinement" / "README.md",
        root / "runs" / "run_02" / "refinement" / "README.md",
    ]
    for run_number in (1, 2):
        wizard_input = root / "runs" / f"run_{run_number:02d}" / "wizard_input"
        required.extend(
            [
                wizard_input / "README.md",
                wizard_input / "poc_input_bundle.json",
                wizard_input / "poc_input" / "access_manifest.json",
                wizard_input / "poc_input" / "query_set.json",
                wizard_input
                / "poc_input"
                / "documents"
                / "employee_travel_policy.pdf",
                wizard_input
                / "poc_input"
                / "documents"
                / "mx200_maintenance_manual.pdf",
                wizard_input
                / "poc_input"
                / "documents"
                / "project_aurora_pricing_strategy.pdf",
            ]
        )
    missing = [str(path.relative_to(root)) for path in required if not path.is_file()]
    if missing:
        print(f"Missing required files: {missing}")
        return 1

    oracle = json.loads((root / "scenario_oracle.json").read_text(encoding="utf-8"))
    answers = json.loads((root / "scripted_answers.json").read_text(encoding="utf-8"))
    coverage = json.loads((root / "wizard_requirement_coverage.json").read_text(encoding="utf-8"))
    if any(document.get("scenario_id") != "UC03" for document in (oracle, answers, coverage)):
        print("Scenario identifiers are inconsistent.")
        return 1
    if oracle.get("oracle_version") != "1.4.0" or answers.get("version") != "1.4.0":
        print("Oracle and scripted-answer versions must both be 1.4.0.")
        return 1

    searchable_files = [
        root / "README.md",
        root / "initial_prompt.txt",
        root / "scenario_oracle.json",
        root / "scripted_answers.json",
        root / "scripted_answers.md",
        root / "wizard_requirement_coverage.json",
        root / "wizard_requirement_coverage.md",
    ]
    forbidden_phrases = (
        "groundedness_or_" + "confidence",
        "report an incorrect or unsupported answer to the " + "knowledge owner",
    )
    for path in searchable_files:
        content = path.read_text(encoding="utf-8").lower()
        for phrase in forbidden_phrases:
            if phrase in content:
                print(f"Excluded UC03 requirement found in {path.relative_to(root)}: {phrase}")
                return 1

    expected_results = json.loads(
        (root / "fixtures" / "expected_rag_results.json").read_text(encoding="utf-8")
    )
    if (
        expected_results.get("acceptance_policy", {}).get("citation_format")
        != "[file_name, page_number]"
    ):
        print("Expected RAG results must use [file_name, page_number] citations.")
        return 1
    expected_citations = {
        "Q01": [["employee_travel_policy.pdf", 3]],
        "Q02": [
            ["mx200_maintenance_manual.pdf", 3],
            ["mx200_maintenance_manual.pdf", 4],
        ],
        "Q03": [],
        "Q04": [["project_aurora_pricing_strategy.pdf", 3]],
    }
    actual_citations = {
        item.get("query_id"): item.get("required_citations")
        for item in expected_results.get("expected_results", [])
    }
    if actual_citations != expected_citations:
        print(f"Expected citation pairs are incorrect: {actual_citations}")
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
        expected_command = ["python", "run_poc.py", "--input", "{fixture}"]
        if run_metadata.get("poc", {}).get("run_command") != expected_command:
            print(f"{run_name} must use the fixed --input PoC command.")
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

        canonical = root / "fixtures"
        wizard_input = run_dir / "wizard_input"
        copy_pairs = (
            (canonical / "poc_input_bundle.json", wizard_input / "poc_input_bundle.json"),
            (
                canonical / "poc_input" / "access_manifest.json",
                wizard_input / "poc_input" / "access_manifest.json",
            ),
            (
                canonical / "poc_input" / "query_set.json",
                wizard_input / "poc_input" / "query_set.json",
            ),
            *(
                (
                    canonical / "poc_input" / "documents" / filename,
                    wizard_input / "poc_input" / "documents" / filename,
                )
                for filename in (
                    "employee_travel_policy.pdf",
                    "mx200_maintenance_manual.pdf",
                    "project_aurora_pricing_strategy.pdf",
                )
            ),
        )
        mismatches = [
            str(destination.relative_to(root))
            for source, destination in copy_pairs
            if source.read_bytes() != destination.read_bytes()
        ]
        if mismatches:
            print(f"{run_name} wizard-input copies differ from canonical fixtures: {mismatches}")
            return 1

    for script in (root / "scripts").glob("*.py"):
        py_compile.compile(str(script), doraise=True)

    manifest_path = root / "fixtures" / "fixture_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for filename in (
        "rag_test_bundle.json",
        "rag_fixture_facts.txt",
        "expected_rag_results.json",
        "poc_input_bundle.json",
        "poc_input/access_manifest.json",
        "poc_input/query_set.json",
        "poc_input/documents/employee_travel_policy.pdf",
        "poc_input/documents/mx200_maintenance_manual.pdf",
        "poc_input/documents/project_aurora_pricing_strategy.pdf",
    ):
        actual_hash = _sha256(root / "fixtures" / filename)
        recorded_hash = manifest.get("sha256", {}).get(filename)
        if recorded_hash != actual_hash:
            print(
                f"Fixture hash mismatch for {filename}: "
                f"recorded={recorded_hash!r}, actual={actual_hash}"
            )
            return 1

    print(
        "Package validation passed. "
        f"Checks={len(all_check_ids)}; EQ1 requirements={len(oracle['checks']['EQ1'])}; "
        "wizard fields covered; global confirmation policy and three-attempt recovery enforced; "
        "Python scripts compiled."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
