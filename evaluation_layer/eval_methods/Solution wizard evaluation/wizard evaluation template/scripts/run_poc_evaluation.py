#!/usr/bin/env python3
"""Execute the original or refined PoC and preserve reproducible evidence."""

from __future__ import annotations

import argparse
import datetime as dt
import glob
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def resolve_command(command: list[str], fixture: Path, package_root: Path, generated_package: Path) -> list[str]:
    resolved = []
    for index, token in enumerate(command):
        token = token.replace("{fixture}", str(fixture)).replace("{package_root}", str(package_root)).replace("{generated_package}", str(generated_package))
        if index == 0 and token.lower() in {"python", "python3", "python.exe"}:
            token = sys.executable
        resolved.append(token)
    return resolved


def execute(command: list[str], cwd: Path, env: dict[str, str]) -> dict:
    started = now()
    try:
        result = subprocess.run(command, cwd=cwd, env=env, text=True, capture_output=True, errors="replace")
        return {"command": command, "started_at": started, "completed_at": now(), "exit_code": result.returncode, "stdout": result.stdout, "stderr": result.stderr}
    except Exception as exc:
        return {"command": command, "started_at": started, "completed_at": now(), "exit_code": 127, "stdout": "", "stderr": repr(exc)}


def attempt_paths(run_dir: Path, attempt: int) -> tuple[Path, Path]:
    if attempt == 0:
        return run_dir / "generated_package", run_dir
    attempt_dir = run_dir / "refinement" / f"attempt_{attempt:02d}"
    return attempt_dir / "generated_package", attempt_dir


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--attempt", required=True, type=int, choices=range(0, 4))
    parser.add_argument("--force-unsuccessful", metavar="REASON", help="Record the attempt as unsuccessful even if commands succeed, for example when semantic output is incorrect.")
    args = parser.parse_args()

    run_dir = (ROOT / args.run_dir).resolve() if not Path(args.run_dir).is_absolute() else Path(args.run_dir).resolve()
    if ROOT not in run_dir.parents:
        raise SystemExit("Run directory must be inside this evaluation package.")
    metadata_path = run_dir / "run_metadata.json"
    if not metadata_path.exists():
        raise SystemExit(f"Missing metadata: {metadata_path}")
    metadata = read_json(metadata_path)
    poc = metadata["poc"]
    generated_package, evidence_dir = attempt_paths(run_dir, args.attempt)
    if not generated_package.exists():
        raise SystemExit(f"Missing generated package: {generated_package}")

    recovery_path = run_dir / "poc_recovery.json"
    recovery = read_json(recovery_path)
    baseline_path = run_dir / "poc_execution.json"
    if args.attempt > 0:
        if not baseline_path.exists() or read_json(baseline_path).get("successful") is not False:
            raise SystemExit("A refinement can run only after attempt 0 is recorded as unsuccessful.")
        if recovery.get("status") in {"successful_original", "recovered"}:
            raise SystemExit("Recovery has already succeeded; no further refinement is allowed.")
        for preceding in range(1, args.attempt):
            preceding_file = run_dir / "refinement" / f"attempt_{preceding:02d}" / "poc_execution.json"
            if not preceding_file.exists():
                raise SystemExit(f"Attempt {preceding} must be executed first.")

    fixture_text = poc.get("fixture", "")
    fixture = (ROOT / fixture_text).resolve()
    if "[REPLACE" in fixture_text or not fixture.exists():
        raise SystemExit(f"Fixture does not exist or remains a placeholder: {fixture}")

    working_dir = generated_package / poc.get("working_directory", "poc")
    if not working_dir.exists():
        raise SystemExit(f"PoC working directory does not exist: {working_dir}")

    env = os.environ.copy()
    env.setdefault("PYTHONUTF8", "1")
    env.setdefault("PYTHONIOENCODING", "utf-8")
    setup_command = resolve_command(poc.get("setup_command", []), fixture, ROOT, generated_package)
    run_command = resolve_command(poc["run_command"], fixture, ROOT, generated_package)
    started_at = now()
    setup_result = execute(setup_command, working_dir, env) if setup_command else None
    setup_ok = setup_result is None or setup_result["exit_code"] == 0
    run_result = execute(run_command, working_dir, env) if setup_ok else None

    outputs: list[dict] = []
    for pattern in poc.get("output_globs", []):
        for name in glob.glob(str(working_dir / pattern), recursive=True):
            path = Path(name)
            if not path.is_file():
                continue
            record = {"path": str(path), "size_bytes": path.stat().st_size, "parseable_json": None}
            if path.suffix.lower() == ".json":
                try:
                    json.loads(path.read_text(encoding="utf-8"))
                    record["parseable_json"] = True
                except Exception:
                    record["parseable_json"] = False
            outputs.append(record)
    outputs = list({item["path"]: item for item in outputs}.values())
    output_ok = bool(outputs) and all(item["size_bytes"] > 0 and item["parseable_json"] is not False for item in outputs)
    automatic_success = setup_ok and run_result is not None and run_result["exit_code"] == 0 and output_ok
    successful = automatic_success and not args.force_unsuccessful

    record = {
        "$schema": str(ROOT / "schemas" / "poc_execution.schema.json"),
        "schema_version": "1.0.0",
        "run_id": metadata["run_id"],
        "attempt": args.attempt,
        "attempt_type": "original" if args.attempt == 0 else "refinement",
        "started_at": started_at,
        "completed_at": now(),
        "generated_package": str(generated_package),
        "working_directory": str(working_dir),
        "fixture": str(fixture),
        "commands": [item for item in [setup_result, run_result] if item is not None],
        "outputs": outputs,
        "automatic_execution_successful": automatic_success,
        "successful": successful,
        "forced_unsuccessful_reason": args.force_unsuccessful,
        "error": None if successful else (args.force_unsuccessful or "Setup, execution, or output validation failed.")
    }
    execution_path = evidence_dir / "poc_execution.json"
    log_path = evidence_dir / "poc_execution.log"
    write_json(execution_path, record)
    log_parts = []
    for label, item in (("setup", setup_result), ("run", run_result)):
        if item:
            log_parts.extend([f"--- {label} command ---\n{shlex.join(item['command'])}", f"exit code: {item['exit_code']}", f"--- {label} stdout ---\n{item['stdout']}", f"--- {label} stderr ---\n{item['stderr']}"])
    log_parts.append("--- outputs ---\n" + json.dumps(outputs, indent=2))
    if args.force_unsuccessful:
        log_parts.append("--- evaluator override ---\n" + args.force_unsuccessful)
    log_path.write_text("\n\n".join(log_parts) + "\n", encoding="utf-8")

    if args.attempt == 0:
        recovery.update({
            "baseline_execution_file": str(execution_path),
            "initial_execution_successful": successful,
            "refinement_attempts_to_success": 0 if successful else None,
            "final_execution_successful": successful,
            "status": "successful_original" if successful else "pending_refinement",
            "attempts": []
        })
    else:
        recovery.setdefault("attempts", []).append({
            "attempt": args.attempt,
            "successful": successful,
            "feedback_file": str(evidence_dir / "feedback_to_wizard.txt"),
            "conversation_file": str(evidence_dir / "conversation.txt"),
            "execution_file": str(execution_path),
            "generated_package": str(generated_package)
        })
        if successful:
            recovery.update({"refinement_attempts_to_success": args.attempt, "final_execution_successful": True, "status": "recovered"})
        elif args.attempt == 3:
            recovery.update({"refinement_attempts_to_success": "N/A", "final_execution_successful": False, "status": "unsuccessful_after_maximum_refinements"})
        else:
            recovery.update({"final_execution_successful": False, "status": "pending_refinement"})
    write_json(recovery_path, recovery)
    print(f"Attempt {args.attempt} {'succeeded' if successful else 'failed'}. Evidence: {execution_path}")
    return 0 if successful else 1


if __name__ == "__main__":
    raise SystemExit(main())
