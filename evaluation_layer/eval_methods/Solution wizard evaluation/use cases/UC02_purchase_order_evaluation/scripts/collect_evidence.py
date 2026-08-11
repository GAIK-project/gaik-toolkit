#!/usr/bin/env python3
"""Collect side-by-side oracle and wizard evidence for EQ1-EQ4.

The script deliberately leaves `human_verdict` empty. An LLM may be used to
align semantically equivalent wording and locate evidence, but the evaluator
enters the final Yes/No verdict in the Excel workbook.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from package_checks import evaluate_package


STOPWORDS = {
    "a", "an", "and", "as", "at", "be", "before", "by", "for", "from", "in",
    "is", "it", "of", "on", "or", "the", "to", "with", "must", "may", "no",
    "not", "required", "output", "value", "field", "system", "solution"
}


def _json(path: Path, default: Any = None) -> Any:
    if not path.is_file():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _find_blueprint(run_dir: Path) -> tuple[Path | None, dict[str, Any]]:
    package_dir = run_dir / "generated_package"
    candidates = [package_dir / "use_case.blueprint.json", *sorted(package_dir.glob("*.blueprint.json"))]
    for path in candidates:
        if path.is_file():
            try:
                return path, json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                return path, {}
    return None, {}


def _walk_hint(value: Any, tokens: list[str], prefix: str = "$") -> list[tuple[str, Any]]:
    if not tokens:
        return [(prefix, value)]
    token = tokens[0]
    rest = tokens[1:]
    results: list[tuple[str, Any]] = []
    if isinstance(value, dict):
        if token in value:
            results.extend(_walk_hint(value[token], rest, f"{prefix}.{token}"))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            results.extend(_walk_hint(item, tokens, f"{prefix}[{index}]"))
    return results


def _hint_values(blueprint: dict[str, Any], hints: list[str]) -> list[tuple[str, Any]]:
    found: list[tuple[str, Any]] = []
    for hint in hints:
        found.extend(_walk_hint(blueprint, hint.split(".")))
    unique: dict[str, Any] = {}
    for path, value in found:
        unique[path] = value
    return list(unique.items())


def _conversation_excerpt(text: str, check: dict[str, Any]) -> str:
    terms = re.findall(
        r"[A-Za-zÀ-ÖØ-öø-ÿ0-9_-]{3,}",
        f"{check.get('parameter', '')} {check.get('oracle_value', '')}".lower(),
    )
    terms = [term for term in terms if term not in STOPWORDS]
    lines = text.splitlines()
    scored: list[tuple[int, int, str]] = []
    for number, line in enumerate(lines, 1):
        line_lower = line.lower()
        score = sum(term in line_lower for term in terms)
        if score:
            scored.append((score, number, line.strip()))
    scored.sort(key=lambda item: (-item[0], item[1]))
    selected = sorted(scored[:4], key=lambda item: item[1])
    return " | ".join(f"L{number}: {line}" for _, number, line in selected)


def _poc_snippets(run_dir: Path) -> str:
    poc_dir = run_dir / "generated_package" / "poc"
    candidates = [
        poc_dir / "run_poc.py",
        poc_dir / "config.yaml",
        poc_dir / "config.yml",
        poc_dir / "prompts" / "extraction_requirements.md",
    ]
    blocks: list[str] = []
    for path in candidates:
        if path.is_file():
            text = path.read_text(encoding="utf-8", errors="replace")
            blocks.append(f"FILE {path.relative_to(run_dir)}\n{text[:16000]}")
    return "\n\n".join(blocks)


def _deterministic_alignment(
    checks: list[dict[str, Any]],
    blueprint: dict[str, Any],
    blueprint_path: Path | None,
    conversation: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for check in checks:
        hints = check.get("blueprint_hints", [])
        values = _hint_values(blueprint, hints)
        excerpt = _conversation_excerpt(conversation, check)
        if values:
            generated = "; ".join(
                f"{path}={json.dumps(value, ensure_ascii=False)}" for path, value in values
            )
        else:
            generated = "NOT FOUND BY DETERMINISTIC PATH HINTS"
        evidence_parts = []
        if values:
            evidence_parts.append(
                f"{blueprint_path}: " + "; ".join(path for path, _ in values)
            )
        if excerpt:
            evidence_parts.append(f"conversation.txt: {excerpt}")
        if not evidence_parts:
            evidence_parts.append(
                f"Searched blueprint hints {hints or 'none'} and conversation.txt; no candidate evidence found."
            )
        rows.append(
            {
                "check_id": check["id"],
                "generated_value": generated,
                "evidence": " || ".join(evidence_parts),
                "automatic_result": "needs_review",
                "human_verdict": None,
                "evaluator_notes": "",
            }
        )
    return rows


def _extract_json_text(text: str) -> Any:
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    first = min((index for index in (cleaned.find("["), cleaned.find("{")) if index >= 0), default=0)
    return json.loads(cleaned[first:])


def _llm_alignment(
    checks: list[dict[str, Any]],
    conversation: str,
    blueprint: dict[str, Any],
    poc_snippets: str,
    model: str,
) -> list[dict[str, Any]]:
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise SystemExit("Install the optional dependency with: python -m pip install openai") from exc

    compact_checks = [
        {
            "id": check["id"],
            "parameter": check["parameter"],
            "oracle_value": check["oracle_value"],
            "accepted_semantics": check.get("accepted_semantics", ""),
            "blueprint_hints": check.get("blueprint_hints", []),
        }
        for check in checks
    ]
    numbered_conversation = "\n".join(
        f"L{number:04d}: {line}" for number, line in enumerate(conversation.splitlines(), 1)
    )
    prompt = f"""
You are an evidence extractor for a software-engineering evaluation. Do not decide
whether a check passes. For every oracle check, locate the closest wizard-generated
value and concrete evidence. Semantically equivalent wording is acceptable.

Return a JSON array with exactly one object per check:
{{
  "check_id": "...",
  "generated_value": "concise value, or NOT FOUND",
  "evidence": "source file plus exact JSON path/value, conversation line, or PoC file excerpt"
}}

Rules:
- Never output a Yes/No/pass/fail verdict.
- If evidence is absent, write NOT FOUND and list what was searched.
- Cite exact JSON paths where possible.
- Conversation evidence must cite line numbers.
- Do not treat an LLM inference as wizard evidence.

ORACLE CHECKS
{json.dumps(compact_checks, ensure_ascii=False, indent=2)}

CONVERSATION
{numbered_conversation[:90000]}

GENERATED BLUEPRINT
{json.dumps(blueprint, ensure_ascii=False, indent=2)[:90000]}

RELEVANT PoC FILES
{poc_snippets[:40000]}
"""
    response = OpenAI().responses.create(model=model, input=prompt)
    payload = _extract_json_text(response.output_text)
    by_id = {item["check_id"]: item for item in payload}
    rows: list[dict[str, Any]] = []
    for check in checks:
        item = by_id.get(check["id"], {})
        rows.append(
            {
                "check_id": check["id"],
                "generated_value": item.get("generated_value", "NOT FOUND"),
                "evidence": item.get("evidence", "LLM returned no evidence for this check."),
                "automatic_result": "needs_review",
                "human_verdict": None,
                "evaluator_notes": "",
            }
        )
    return rows


def _eq4_rows(run_dir: Path, oracle: dict[str, Any]) -> list[dict[str, Any]]:
    record_path = run_dir / "poc_execution.json"
    record = _json(record_path, {})
    expected_path = (
        Path(__file__).resolve().parent.parent
        / "fixtures"
        / "expected_erp_record.json"
    )
    expected = _json(expected_path, {})

    if not record:
        return [
            {
                "check_id": check["id"],
                "generated_value": "NOT FOUND",
                "evidence": f"{record_path} does not exist. Run scripts/run_poc_evaluation.py first.",
                "automatic_result": "needs_review",
                "human_verdict": None,
                "evaluator_notes": "",
            }
            for check in oracle["checks"]["EQ4"]
        ]

    setup = record.get("setup", {})
    execution = record.get("execution", {})
    outputs = record.get("outputs", [])
    parsed_outputs = [item for item in outputs if item.get("json_parsed")]
    row_map = {
        "EQ4-X01": {
            "generated_value": f"setup exit code={setup.get('exit_code')}",
            "evidence": f"{record_path}; command={setup.get('command')}; stdout={str(setup.get('stdout', ''))[:800]}; stderr={str(setup.get('stderr', ''))[:800]}",
            "automatic_result": "pass" if setup.get("exit_code") == 0 else "fail",
        },
        "EQ4-X02": {
            "generated_value": f"run exit code={execution.get('exit_code')}",
            "evidence": f"{record_path}; fixture={record.get('fixture')}; command={execution.get('command')}; stdout={str(execution.get('stdout', ''))[:800]}; stderr={str(execution.get('stderr', ''))[:800]}",
            "automatic_result": "pass" if execution.get("exit_code") == 0 else "fail",
        },
        "EQ4-X03": {
            "generated_value": json.dumps(
                [
                    {
                        "path": item.get("relative_path"),
                        "size_bytes": item.get("size_bytes"),
                        "json_parsed": item.get("json_parsed"),
                    }
                    for item in outputs
                ],
                ensure_ascii=False,
            ),
            "evidence": f"{record_path}; parsed output paths={[item.get('path') for item in parsed_outputs]}",
            "automatic_result": "pass" if parsed_outputs else "fail",
        },
        "EQ4-X04": {
            "generated_value": json.dumps(
                [item.get("json_value") for item in parsed_outputs],
                ensure_ascii=False,
            ) if parsed_outputs else "NOT FOUND",
            "evidence": f"Oracle fixture: {expected_path}={json.dumps(expected, ensure_ascii=False)}; generated output evidence: {record_path} outputs.",
            "automatic_result": "needs_review",
        },
    }
    return [
        {
            "check_id": check["id"],
            **row_map[check["id"]],
            "human_verdict": None,
            "evaluator_notes": "",
        }
        for check in oracle["checks"]["EQ4"]
    ]


def _attach_oracle(rows: list[dict[str, Any]], checks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id = {check["id"]: check for check in checks}
    attached: list[dict[str, Any]] = []
    for row in rows:
        check = by_id[row["check_id"]]
        attached.append(
            {
                "check_id": check["id"],
                "parameter": check["parameter"],
                "oracle_value": check["oracle_value"],
                "oracle_source": "; ".join(check.get("source", check.get("evidence_required", []))),
                "scored": check.get("scored", True),
                **{key: value for key, value in row.items() if key != "check_id"},
            }
        )
    return attached


def _recovery_diagnostic(run_dir: Path) -> dict[str, Any]:
    summary_path = run_dir / "poc_recovery.json"
    summary = _json(summary_path, {})
    if not summary:
        return {
            "initial_execution_successful": None,
            "refinement_attempts_to_success": None,
            "final_execution_successful": None,
            "status": "not_started",
            "evidence": f"{summary_path} does not exist.",
        }
    attempt_evidence = [
        {
            "attempt": attempt.get("attempt"),
            "successful": attempt.get("successful"),
            "execution_file": attempt.get("execution_file"),
            "conversation_file": attempt.get("conversation_file"),
        }
        for attempt in summary.get("attempts", [])
    ]
    return {
        "initial_execution_successful": summary.get("initial_execution_successful"),
        "refinement_attempts_to_success": summary.get("refinement_attempts_to_success"),
        "final_execution_successful": summary.get("final_execution_successful"),
        "maximum_refinement_attempts": summary.get("maximum_refinement_attempts", 3),
        "status": summary.get("status", "not_started"),
        "evidence": (
            f"{summary_path}; baseline={summary.get('baseline_execution_file')}; "
            f"attempts={json.dumps(attempt_evidence, ensure_ascii=False)}"
        ),
        "eq4_uses_baseline_only": True,
    }


def collect_run(package_root: Path, run_name: str, use_llm: bool, model: str) -> dict[str, Any]:
    oracle = _json(package_root / "scenario_oracle.json")
    run_dir = package_root / "runs" / run_name
    metadata = _json(run_dir / "run_metadata.json", {"run_id": run_name})
    conversation_path = run_dir / "conversation.txt"
    conversation = conversation_path.read_text(encoding="utf-8", errors="replace") if conversation_path.is_file() else ""
    blueprint_path, blueprint = _find_blueprint(run_dir)
    poc_snippets = _poc_snippets(run_dir)

    def align(checks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if use_llm:
            return _llm_alignment(checks, conversation, blueprint, poc_snippets, model)
        return _deterministic_alignment(checks, blueprint, blueprint_path, conversation)

    eq1_checks = oracle["checks"]["EQ1"]
    diagnostic_checks = oracle["checks"]["EQ1_diagnostics"]
    eq2_checks = oracle["checks"]["EQ2"]
    eq3_checks = oracle["checks"]["EQ3"]
    eq4_checks = oracle["checks"]["EQ4"]

    eq3_rows = evaluate_package(run_dir, metadata)
    for row in eq3_rows:
        row.update({"human_verdict": None, "evaluator_notes": ""})

    result = {
        "schema_version": "1.0.0",
        "scenario_id": oracle["scenario_id"],
        "run_id": metadata.get("run_id", run_name),
        "inputs": {
            "conversation": str(conversation_path),
            "blueprint": str(blueprint_path) if blueprint_path else None,
            "poc_execution": str(run_dir / "poc_execution.json"),
        },
        "evidence_extraction": {
            "mode": "llm-assisted" if use_llm else "deterministic-path-hints",
            "model": model if use_llm else None,
            "final_verdict_automated": False,
        },
        "recovery_diagnostic": _recovery_diagnostic(run_dir),
        "results": {
            "EQ1": _attach_oracle(align(eq1_checks), eq1_checks),
            "EQ1_diagnostics": _attach_oracle(align(diagnostic_checks), diagnostic_checks),
            "EQ2": _attach_oracle(align(eq2_checks), eq2_checks),
            "EQ3": _attach_oracle(eq3_rows, eq3_checks),
            "EQ4": _attach_oracle(_eq4_rows(run_dir, oracle), eq4_checks),
        },
    }
    output_path = run_dir / "evaluation_results.json"
    output_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package-root", type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument("--run", choices=["run_01", "run_02", "all"], default="all")
    parser.add_argument("--use-llm", action="store_true")
    parser.add_argument("--model", default="gpt-5-mini")
    args = parser.parse_args()

    package_root = args.package_root.resolve()
    run_names = ["run_01", "run_02"] if args.run == "all" else [args.run]
    runs = {
        run_name: collect_run(package_root, run_name, args.use_llm, args.model)
        for run_name in run_names
    }
    comparison_path = package_root / "results" / "comparison_data.json"
    existing = _json(comparison_path, {"schema_version": "1.0.0", "scenario_id": "UC02", "runs": {}})
    existing["runs"].update(runs)
    comparison_path.write_text(json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {comparison_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
