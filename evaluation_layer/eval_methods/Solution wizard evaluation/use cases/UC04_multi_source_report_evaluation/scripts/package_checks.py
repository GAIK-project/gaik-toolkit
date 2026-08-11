#!/usr/bin/env python3
"""Deterministic EQ3 checks for a generated GAIK solution package."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any


def _record(check_id: str, value: str, evidence: str, automatic_result: str) -> dict[str, str]:
    return {
        "check_id": check_id,
        "generated_value": value,
        "evidence": evidence,
        "automatic_result": automatic_result,
    }


def _find_blueprint(package_dir: Path) -> Path | None:
    preferred = package_dir / "use_case.blueprint.json"
    if preferred.is_file():
        return preferred
    candidates = sorted(package_dir.glob("*.blueprint.json"))
    return candidates[0] if candidates else None


def _load_blueprint(package_dir: Path) -> tuple[Path | None, dict[str, Any] | None, str]:
    path = _find_blueprint(package_dir)
    if not path:
        return None, None, "No use_case.blueprint.json or *.blueprint.json file found."
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # exact parser evidence belongs in the result
        return path, None, f"{type(exc).__name__}: {exc}"
    return path, data, "JSON parsed successfully."


def _workflow_steps(blueprint: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not blueprint:
        return []
    steps = blueprint.get("workflow", {}).get("steps", [])
    return [step for step in steps if isinstance(step, dict)]


def _artifact_flow_evidence(blueprint: dict[str, Any] | None) -> tuple[bool, str]:
    if not blueprint:
        return False, "Blueprint unavailable; artifact flow could not be checked."
    artifacts = blueprint.get("artifacts", {})
    steps = _workflow_steps(blueprint)
    if not isinstance(artifacts, dict) or not steps:
        return False, f"artifacts={type(artifacts).__name__}; workflow step count={len(steps)}."

    step_ids = {str(step.get("id", "")) for step in steps}
    missing_refs: list[str] = []
    bad_dependencies: list[str] = []
    producer_mismatches: list[str] = []

    for step in steps:
        sid = str(step.get("id", ""))
        for key in ("inputs", "outputs"):
            for artifact_id in step.get(key, []) or []:
                if artifact_id not in artifacts:
                    missing_refs.append(f"{sid}.{key}->{artifact_id}")
        for dependency in step.get("depends_on", []) or []:
            if dependency not in step_ids:
                bad_dependencies.append(f"{sid}.depends_on->{dependency}")

    for artifact_id, artifact in artifacts.items():
        if not isinstance(artifact, dict):
            continue
        if artifact.get("source") == "generated":
            producer = artifact.get("produced_by")
            if not producer or producer not in step_ids:
                producer_mismatches.append(f"{artifact_id}.produced_by={producer!r}")
                continue
            producer_step = next(step for step in steps if str(step.get("id", "")) == producer)
            if artifact_id not in (producer_step.get("outputs", []) or []):
                producer_mismatches.append(f"{artifact_id} absent from {producer}.outputs")

    ok = not (missing_refs or bad_dependencies or producer_mismatches)
    evidence = (
        f"Checked {len(steps)} workflow steps and {len(artifacts)} artifacts. "
        f"Undeclared references: {missing_refs or 'none'}; "
        f"invalid dependencies: {bad_dependencies or 'none'}; "
        f"producer mismatches: {producer_mismatches or 'none'}."
    )
    return ok, evidence


def _run_official_validator(
    run_dir: Path, blueprint_path: Path | None, run_metadata: dict[str, Any]
) -> tuple[str, str, str]:
    configured = run_metadata.get("commands", {}).get("blueprint_validator")
    command: list[str] | None = configured if isinstance(configured, list) and configured else None
    cwd = run_dir
    source = "run_metadata.json override"

    if command is None and blueprint_path:
        candidate_roots: list[Path] = []
        wizard_root = os.getenv("GAIK_SOLUTION_WIZARD_ROOT")
        if wizard_root:
            candidate_roots.append(Path(wizard_root))
        for starting_point in (
            Path(__file__).resolve().parent.parent,
            run_dir,
            Path.cwd(),
        ):
            candidate_roots.extend([starting_point, *starting_point.parents[:4]])

        relative_candidates = (
            Path("scripts/validate_blueprint.py"),
            Path("implementation_layer/solution_wizard/scripts/validate_blueprint.py"),
            Path("solution_wizard/scripts/validate_blueprint.py"),
        )
        seen: set[Path] = set()
        for root in candidate_roots:
            resolved_root = root.resolve()
            if resolved_root in seen:
                continue
            seen.add(resolved_root)
            for relative in relative_candidates:
                script = resolved_root / relative
                if script.is_file() and script.resolve() != Path(__file__).resolve():
                    command = [
                        sys.executable,
                        str(script.resolve()),
                        "--blueprint",
                        str(blueprint_path.resolve()),
                    ]
                    cwd = script.parent.parent
                    source = f"auto-discovered at {script.resolve()}"
                    break
            if command is not None:
                break

    if command is None and blueprint_path:
        executable = shutil.which("gaik-validate-blueprint")
        if executable:
            command = [executable, "--blueprint", str(blueprint_path.resolve())]
            cwd = run_dir
            source = f"auto-discovered executable {executable}"

    if command is None:
        log_candidates = [
            run_dir / "blueprint_validation.log",
            run_dir / "generated_package" / "blueprint_validation.log",
        ]
        for log_path in log_candidates:
            if log_path.is_file():
                text = log_path.read_text(encoding="utf-8", errors="replace")
                return (
                    "Recorded validator log; evaluator must confirm pass/fail.",
                    f"{log_path}: {text[:1200]}",
                    "needs_review",
                )
        return (
            "Official validator not executed.",
            "No official validator was auto-discovered. Other EQ3 checks were still executed. "
            "Optionally set GAIK_SOLUTION_WIZARD_ROOT or add commands.blueprint_validator "
            "to run_metadata.json, then rerun collect_evidence.py.",
            "needs_review",
        )

    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
        output = (result.stdout + "\n" + result.stderr).strip()
        status = "pass" if result.returncode == 0 else "fail"
        return (
            f"Validator exit code {result.returncode}.",
            f"Resolution: {source}; command: {command!r}; cwd: {cwd}; output: {output[:1800]}",
            status,
        )
    except Exception as exc:
        return (
            "Validator execution did not complete.",
            f"Command: {command!r}; {type(exc).__name__}: {exc}",
            "needs_review",
        )


def evaluate_package(run_dir: Path, run_metadata: dict[str, Any]) -> list[dict[str, str]]:
    package_dir = run_dir / "generated_package"
    blueprint_path, blueprint, parse_evidence = _load_blueprint(package_dir)
    results: list[dict[str, str]] = []

    if blueprint_path and blueprint is not None:
        size = blueprint_path.stat().st_size
        results.append(
            _record(
                "EQ3-P01",
                f"Blueprint parsed; {size} bytes.",
                f"{blueprint_path}: {parse_evidence}",
                "pass" if size > 0 else "fail",
            )
        )
    else:
        results.append(
            _record(
                "EQ3-P01",
                "Blueprint missing or invalid.",
                f"{blueprint_path or package_dir}: {parse_evidence}",
                "fail",
            )
        )

    value, evidence, status = _run_official_validator(run_dir, blueprint_path, run_metadata)
    results.append(_record("EQ3-P02", value, evidence, status))

    flow_ok, flow_evidence = _artifact_flow_evidence(blueprint)
    results.append(
        _record(
            "EQ3-P03",
            "Artifact flow is internally consistent." if flow_ok else "Artifact-flow issues detected.",
            flow_evidence,
            "pass" if flow_ok else "fail",
        )
    )

    steps = _workflow_steps(blueprint)
    mmd_path = package_dir / "workflow.mmd"
    if mmd_path.is_file():
        mmd = mmd_path.read_text(encoding="utf-8", errors="replace")
        matched = [
            str(step.get("id") or step.get("name"))
            for step in steps
            if str(step.get("id", "")) in mmd or str(step.get("name", "")) in mmd
        ]
        ok = bool(mmd.strip()) and (not steps or len(matched) == len(steps))
        evidence = f"{mmd_path}; {mmd_path.stat().st_size} bytes; matched {len(matched)}/{len(steps)} steps: {matched}."
    else:
        ok = False
        evidence = f"{mmd_path} not found."
    results.append(
        _record(
            "EQ3-P04",
            "Mermaid workflow present and covers steps." if ok else "Mermaid workflow incomplete or missing.",
            evidence,
            "pass" if ok else "fail",
        )
    )

    bpmn_path = package_dir / "workflow.bpmn"
    bpmn_ok = False
    bpmn_evidence = f"{bpmn_path} not found."
    if bpmn_path.is_file():
        try:
            root = ET.parse(bpmn_path).getroot()
            xml_ids = {element.attrib.get("id", "") for element in root.iter()}
            xml_names = {element.attrib.get("name", "") for element in root.iter()}
            mapping = (blueprint or {}).get("visualizations", {}).get("bpmn_mapping", {})
            mapping_text = json.dumps(mapping, ensure_ascii=False)
            matched = [
                str(step.get("id") or step.get("name"))
                for step in steps
                if (
                    str(step.get("id", "")) in xml_ids
                    or str(step.get("name", "")) in xml_names
                    or str(step.get("id", "")) in mapping_text
                )
            ]
            bpmn_ok = not steps or len(matched) == len(steps)
            bpmn_evidence = (
                f"{bpmn_path}; XML parsed; {len(xml_ids)} element ids; "
                f"matched {len(matched)}/{len(steps)} blueprint steps through BPMN ids/names/mapping."
            )
        except Exception as exc:
            bpmn_evidence = f"{bpmn_path}; {type(exc).__name__}: {exc}"
    results.append(
        _record(
            "EQ3-P05",
            "BPMN parsed and maps workflow steps." if bpmn_ok else "BPMN missing, invalid, or not fully mapped.",
            bpmn_evidence,
            "pass" if bpmn_ok else "fail",
        )
    )

    poc_dir = package_dir / "poc"
    categories = {
        "entrypoint": ["run_poc.py", "main.py"],
        "dependencies": ["requirements.txt", "pyproject.toml"],
        "configuration": ["config.yaml", "config.yml", "config.json", ".env.example"],
    }
    matched_files: dict[str, list[str]] = {}
    for category, names in categories.items():
        matched_files[category] = [
            str(path.relative_to(poc_dir))
            for name in names
            for path in poc_dir.rglob(name)
            if path.is_file() and path.stat().st_size > 0
        ]
    matched_files["prompts"] = [
        str(path.relative_to(poc_dir))
        for path in poc_dir.glob("prompts/*")
        if path.is_file() and path.stat().st_size > 0
    ]
    matched_files["schemas"] = [
        str(path.relative_to(poc_dir))
        for path in poc_dir.glob("schemas/*")
        if path.is_file() and path.stat().st_size > 0
    ]
    scaffold_ok = poc_dir.is_dir() and all(matched_files.values())
    results.append(
        _record(
            "EQ3-P06",
            "PoC scaffold contains all required file categories." if scaffold_ok else "PoC scaffold is missing one or more file categories.",
            f"{poc_dir}; matched files by category: {json.dumps(matched_files, ensure_ascii=False)}",
            "pass" if scaffold_ok else "fail",
        )
    )

    docs_dir = package_dir / "docs"
    docs = [
        path
        for path in docs_dir.rglob("*")
        if path.is_file() and path.stat().st_size > 0
    ] if docs_dir.is_dir() else []
    poc_readmes = [
        path for path in poc_dir.rglob("README*") if path.is_file() and path.stat().st_size > 0
    ] if poc_dir.is_dir() else []
    docs_ok = bool(docs) and bool(poc_readmes)
    doc_evidence = [f"{path.relative_to(package_dir)} ({path.stat().st_size} bytes)" for path in docs + poc_readmes]
    results.append(
        _record(
            "EQ3-P07",
            "Documentation and PoC usage instructions are present." if docs_ok else "Documentation or PoC usage instructions are missing.",
            f"Non-empty documents: {doc_evidence or 'none'}.",
            "pass" if docs_ok else "fail",
        )
    )

    traceability = (blueprint or {}).get("traceability", [])
    selected = (blueprint or {}).get("components", {})
    selected_names = [
        item.get("name") for item in selected.get("selected_modules", []) if isinstance(item, dict)
    ] + list(selected.get("selected_building_blocks", []) or [])
    trace_text = json.dumps(traceability, ensure_ascii=False)
    covered = [name for name in selected_names if name and name in trace_text]
    trace_ok = bool(traceability) and bool(selected_names) and len(covered) >= 1
    results.append(
        _record(
            "EQ3-P08",
            "Traceability entries connect selected GAIK assets to requirements." if trace_ok else "Traceability is missing or does not mention selected assets.",
            f"Traceability entries={len(traceability) if isinstance(traceability, list) else 0}; selected assets={selected_names}; mentioned assets={covered}.",
            "pass" if trace_ok else "fail",
        )
    )
    return results
