#!/usr/bin/env python3
"""Collect and align evidence without assigning the evaluator's Yes/No verdict."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_json(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def flatten(value, prefix=""):
    found = {}
    if isinstance(value, dict):
        for key, child in value.items():
            found.update(flatten(child, f"{prefix}.{key}" if prefix else key))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.update(flatten(child, f"{prefix}[{index}]"))
    else:
        found[prefix] = value
    return found


def choose_blueprint(package: Path) -> Path | None:
    preferred = package / "use_case.blueprint.json"
    if preferred.exists():
        return preferred
    candidates = [p for p in package.rglob("*.json") if "blueprint" in p.name.lower()]
    return candidates[0] if candidates else None


def evidence_corpus(run_dir: Path, package: Path, blueprint) -> str:
    parts = []
    conversation = run_dir / "conversation.txt"
    if conversation.exists():
        parts.append(f"FILE: {conversation.name}\n{conversation.read_text(encoding='utf-8', errors='replace')}")
    if blueprint is not None:
        parts.append("FILE: use_case.blueprint.json\n" + json.dumps(blueprint, ensure_ascii=False, indent=2))
    allowed = {".md", ".txt", ".json", ".yaml", ".yml", ".py", ".mmd", ".bpmn"}
    for path in sorted(package.rglob("*")):
        if path.is_file() and path.suffix.lower() in allowed and path.name != "use_case.blueprint.json":
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            parts.append(f"FILE: {path.relative_to(package)}\n{text[:12000]}")
    return "\n\n".join(parts)[:160000]


def find_value(check, blueprint_flat, corpus: str):
    for path in check.get("blueprint_paths", []):
        if path in blueprint_flat:
            value = blueprint_flat[path]
            return json.dumps(value, ensure_ascii=False), f"use_case.blueprint.json path: {path}"
        matches = [(key, value) for key, value in blueprint_flat.items() if key.endswith(path)]
        if matches:
            key, value = matches[0]
            return json.dumps(value, ensure_ascii=False), f"use_case.blueprint.json path: {key}"
    terms = [term.lower() for term in re.findall(r"[A-Za-z][A-Za-z0-9_-]{3,}", check.get("parameter", ""))]
    for line in corpus.splitlines():
        if terms and sum(term in line.lower() for term in terms) >= max(1, min(2, len(terms))):
            return line.strip()[:1000], "Keyword-aligned excerpt; human review required."
    return "NOT FOUND", "No deterministic evidence match was found."


def discover_validator(metadata, blueprint_path: Path | None):
    if blueprint_path is None:
        return None
    configured = metadata.get("commands", {}).get("blueprint_validator", [])
    if configured:
        return [str(token).replace("{blueprint}", str(blueprint_path)) for token in configured], ROOT
    roots = []
    if os.environ.get("GAIK_SOLUTION_WIZARD_ROOT"):
        roots.append(Path(os.environ["GAIK_SOLUTION_WIZARD_ROOT"]))
    roots.extend([Path.home() / "gaik-toolkit", ROOT.parent / "gaik-toolkit"])
    for candidate_root in roots:
        candidates = [
            candidate_root / "implementation_layer" / "solution_wizard" / "scripts" / "validate_blueprint.py",
            candidate_root / "scripts" / "validate_blueprint.py",
        ]
        for script in candidates:
            if script.exists():
                return [sys.executable, str(script), "--blueprint", str(blueprint_path)], script.parents[1]
    return None


def package_checks(run_dir: Path, package: Path, metadata, blueprint_path, blueprint):
    results = {}
    results["EQ3-P01"] = (
        "Blueprint exists and parses." if blueprint_path and blueprint is not None else "Blueprint missing or invalid.",
        str(blueprint_path) if blueprint_path else "No blueprint file found.",
        "pass" if blueprint_path and blueprint is not None else "fail",
    )
    validator = discover_validator(metadata, blueprint_path)
    if validator:
        command, cwd = validator
        result = subprocess.run(command, cwd=cwd, text=True, capture_output=True, errors="replace")
        excerpt = (result.stdout + "\n" + result.stderr).strip()[:5000]
        results["EQ3-P02"] = (
            f"Validator exit code {result.returncode}.",
            f"command: {command}; cwd: {cwd}; output: {excerpt}",
            "pass" if result.returncode == 0 else "fail",
        )
    else:
        results["EQ3-P02"] = (
            "Official validator not executed.",
            "No official validator was auto-discovered. Set GAIK_SOLUTION_WIZARD_ROOT or commands.blueprint_validator, then rerun evidence collection.",
            "needs_review",
        )
    bpmn = list(package.rglob("*.bpmn"))
    mermaid = list(package.rglob("*.mmd"))
    results["EQ3-P03"] = (
        f"BPMN files={len(bpmn)}; Mermaid files={len(mermaid)}.",
        "; ".join(str(p.relative_to(package)) for p in bpmn + mermaid) or "No workflow views found.",
        "pass" if bpmn and mermaid else "needs_review",
    )
    files = [p for p in package.rglob("*") if p.is_file()]
    has_poc = (package / "poc").is_dir()
    has_docs = any(p.suffix.lower() == ".md" for p in files)
    results["EQ3-P04"] = (
        f"Package files={len(files)}; PoC directory={'present' if has_poc else 'missing'}; documentation={'present' if has_docs else 'missing'}.",
        "; ".join(str(p.relative_to(package)) for p in files[:80]),
        "pass" if has_poc and has_docs else "needs_review",
    )
    return results


def execution_checks(run_dir: Path):
    execution = load_json(run_dir / "poc_execution.json", {})
    commands = execution.get("commands", [])
    setup = commands[0] if len(commands) > 1 else None
    run = commands[-1] if commands else None
    outputs = execution.get("outputs", [])
    results = {
        "EQ4-E01": ("Setup succeeded." if setup is None or setup.get("exit_code") == 0 else "Setup failed.", json.dumps(setup, ensure_ascii=False) if setup else "No separate setup command.", "pass" if setup is None or setup.get("exit_code") == 0 else "fail"),
        "EQ4-E02": ("Execution succeeded." if run and run.get("exit_code") == 0 else "Execution failed or was not run.", json.dumps(run, ensure_ascii=False)[:5000] if run else "No run record.", "pass" if run and run.get("exit_code") == 0 else "fail"),
        "EQ4-E03": (f"Generated outputs={len(outputs)}.", json.dumps(outputs, ensure_ascii=False)[:5000], "pass" if outputs and all(item.get("size_bytes", 0) > 0 and item.get("parseable_json") is not False for item in outputs) else "fail"),
        "EQ4-E04": ("Semantic output comparison requires human review.", "Compare generated outputs with fixtures/expected_output.json. A forced-unsuccessful reason, if present, is: " + str(execution.get("forced_unsuccessful_reason")), "needs_review"),
    }
    return results


def align_with_llm(checks, corpus: str, model: str):
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise SystemExit("Install requirements-optional.txt before using --use-llm.") from exc
    request = [{"check_id": c["check_id"], "parameter": c["parameter"], "oracle_value": c["expected_value"]} for c in checks if c["check_id"].startswith(("EQ1-", "EQ2-"))]
    prompt = f"""Align evidence for an evaluation. Do not assign Yes or No. For every check, return a JSON array with check_id, generated_value, and evidence. Use NOT FOUND when no evidence exists. Evidence must name a file or quote a short excerpt.\n\nCHECKS:\n{json.dumps(request, ensure_ascii=False)}\n\nSOURCE CORPUS:\n{corpus}"""
    response = OpenAI().responses.create(model=model, input=prompt)
    text = response.output_text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.S)
    values = json.loads(text)
    return {item["check_id"]: item for item in values}


def collect_run(run_name: str, oracle, use_llm: bool, model: str):
    run_dir = ROOT / "runs" / run_name
    package = run_dir / "generated_package"
    metadata = load_json(run_dir / "run_metadata.json", {})
    blueprint_path = choose_blueprint(package)
    blueprint = load_json(blueprint_path) if blueprint_path else None
    flat = flatten(blueprint or {})
    corpus = evidence_corpus(run_dir, package, blueprint)
    pchecks = package_checks(run_dir, package, metadata, blueprint_path, blueprint)
    echecks = execution_checks(run_dir)
    oracle_checks = [item for key in ("requirements", "diagnostics", "configuration_constraints", "package_checks", "execution_checks") for item in oracle.get(key, [])]
    llm_values = align_with_llm(oracle_checks, corpus, model) if use_llm else {}
    rows = []
    for check in oracle_checks:
        check_id = check["check_id"]
        if check_id in pchecks:
            value, evidence, automatic = pchecks[check_id]
        elif check_id in echecks:
            value, evidence, automatic = echecks[check_id]
        elif check_id in llm_values:
            value = llm_values[check_id].get("generated_value", "NOT FOUND")
            evidence = llm_values[check_id].get("evidence", "")
            automatic = "needs_review"
        else:
            value, evidence = find_value(check, flat, corpus)
            automatic = "needs_review" if value != "NOT FOUND" else "not_assessed"
        rows.append({
            "check_id": check_id,
            "parameter": check["parameter"],
            "oracle_value": check["expected_value"],
            "oracle_source": check.get("source") or check.get("evidence_source", ""),
            "scored": check.get("scored", True),
            "generated_value": value,
            "evidence": evidence,
            "automatic_result": automatic,
            "human_verdict": None,
            "evaluator_notes": "",
        })
    result = {"$schema": str(ROOT / "schemas" / "evaluation_results.schema.json"), "schema_version": "1.0.0", "scenario_id": oracle["scenario_id"], "run_id": metadata.get("run_id", run_name), "checks": rows, "poc_recovery": load_json(run_dir / "poc_recovery.json", {})}
    write_json(run_dir / "evaluation_results.json", result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", choices=["run_01", "run_02", "all"], default="all")
    parser.add_argument("--use-llm", action="store_true")
    parser.add_argument("--model", default="gpt-5-mini")
    args = parser.parse_args()
    oracle = load_json(ROOT / "scenario_oracle.json")
    names = ["run_01", "run_02"] if args.run == "all" else [args.run]
    results = {name: collect_run(name, oracle, args.use_llm, args.model) for name in names}
    if args.run == "all":
        comparison = {"schema_version": "1.0.0", "scenario_id": oracle["scenario_id"], "runs": results}
        write_json(ROOT / "results" / "comparison_data.json", comparison)
    print("Evidence collection completed for: " + ", ".join(names))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
