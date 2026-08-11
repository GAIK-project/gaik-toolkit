#!/usr/bin/env python3
"""Execute a baseline or refinement PoC and capture reproducible evidence.

Attempt 0 is the original, unmodified PoC and is the only execution used for
EQ4. Attempts 1-3 are an unscored recovery diagnostic.
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import shlex
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_POC_CONFIG = {
    "setup_command": ["python", "-m", "pip", "install", "-r", "requirements.txt"],
    "run_command": ["python", "run_poc.py", "--input", "{fixture}"],
    "output_globs": ["output/**/*.json", "output/*.json"],
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _run(command: list[str], cwd: Path, timeout: int) -> dict[str, Any]:
    started = time.time()
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            env=os.environ.copy(),
        )
        return {
            "command": command,
            "cwd": str(cwd),
            "exit_code": result.returncode,
            "duration_seconds": round(time.time() - started, 3),
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
    except Exception as exc:
        return {
            "command": command,
            "cwd": str(cwd),
            "exit_code": null_exit_code(),
            "duration_seconds": round(time.time() - started, 3),
            "stdout": "",
            "stderr": f"{type(exc).__name__}: {exc}",
        }


def null_exit_code() -> None:
    return None


def _command(value: Any, fixture: Path) -> list[str] | None:
    if not value:
        return None
    parts = value if isinstance(value, list) else shlex.split(str(value))
    command = [str(part).replace("{fixture}", str(fixture)) for part in parts]
    if command and command[0] in {"python", "python3"}:
        command[0] = sys.executable
    elif command and os.sep not in command[0]:
        command[0] = shutil.which(command[0]) or command[0]
    return command


def _load_json(path: Path, default: Any = None) -> Any:
    if not path.is_file():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _execution_path(run_dir: Path, attempt: int) -> Path:
    if attempt == 0:
        return run_dir / "poc_execution.json"
    return run_dir / "refinement" / f"attempt_{attempt:02d}" / "poc_execution.json"


def _automatic_success(record: dict[str, Any]) -> bool:
    checks = record.get("automatic_checks", {})
    return all(checks.get(check_id) is True for check_id in ("EQ4-X01", "EQ4-X02", "EQ4-X03"))


def _update_recovery_summary(run_dir: Path, metadata: dict[str, Any]) -> dict[str, Any]:
    maximum = int(metadata.get("maximum_refinement_attempts", 3))
    baseline_path = _execution_path(run_dir, 0)
    baseline = _load_json(baseline_path, {})
    attempts: list[dict[str, Any]] = []
    for attempt in range(1, maximum + 1):
        attempt_dir = run_dir / "refinement" / f"attempt_{attempt:02d}"
        record_path = _execution_path(run_dir, attempt)
        record = _load_json(record_path, {})
        if not record:
            continue
        attempts.append(
            {
                "attempt": attempt,
                "successful": _automatic_success(record),
                "feedback_file": str(attempt_dir / "feedback_to_wizard.txt"),
                "conversation_file": str(attempt_dir / "conversation.txt"),
                "execution_file": str(record_path),
                "generated_package": str(attempt_dir / "generated_package"),
            }
        )

    baseline_successful = _automatic_success(baseline) if baseline else None
    first_success = next(
        (item["attempt"] for item in attempts if item["successful"]),
        None,
    )
    attempted_numbers = {item["attempt"] for item in attempts}
    if baseline_successful is True:
        status = "successful_original"
        attempts_to_success: int | str | None = 0
        final_successful: bool | None = True
    elif first_success is not None:
        status = "recovered"
        attempts_to_success = first_success
        final_successful = True
    elif set(range(1, maximum + 1)).issubset(attempted_numbers):
        status = "unsuccessful_after_maximum_refinements"
        attempts_to_success = "N/A"
        final_successful = False
    elif baseline:
        status = "awaiting_refinement"
        attempts_to_success = None
        final_successful = False
    else:
        status = "not_started"
        attempts_to_success = None
        final_successful = None

    summary = {
        "schema_version": "1.0.0",
        "run_id": metadata.get("run_id", run_dir.name),
        "maximum_refinement_attempts": maximum,
        "baseline_execution_file": str(baseline_path),
        "initial_execution_successful": baseline_successful,
        "refinement_attempts_to_success": attempts_to_success,
        "final_execution_successful": final_successful,
        "status": status,
        "attempts": attempts,
        "eq4_uses_baseline_only": True,
        "interpretation": "0=original success; 1-3=success after that many refinements; N/A=never successful after three refinements.",
    }
    summary_path = run_dir / "poc_recovery.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument(
        "--attempt",
        type=int,
        choices=range(0, 4),
        default=0,
        help="0 evaluates the original PoC; 1-3 evaluate recovery refinements.",
    )
    parser.add_argument("--timeout", type=int, default=900)
    args = parser.parse_args()

    run_dir = args.run_dir.resolve()
    attempt = args.attempt
    package_root = Path(__file__).resolve().parent.parent
    fixture = package_root / "fixtures" / "poc_input_bundle.json"
    metadata_path = run_dir / "run_metadata.json"
    metadata = _load_json(
        metadata_path,
        {
            "schema_version": "1.1.0",
            "scenario_id": "UC03",
            "run_id": run_dir.name,
            "maximum_refinement_attempts": 3,
            "poc": DEFAULT_POC_CONFIG,
        },
    )
    maximum = int(metadata.get("maximum_refinement_attempts", 3))
    if maximum != 3:
        raise SystemExit("run_metadata.json must set maximum_refinement_attempts to 3.")

    if attempt == 0:
        execution_dir = run_dir
        generated_package = run_dir / "generated_package"
        attempt_metadata = {}
    else:
        execution_dir = run_dir / "refinement" / f"attempt_{attempt:02d}"
        generated_package = execution_dir / "generated_package"
        attempt_metadata = _load_json(execution_dir / "attempt_metadata.json", {})
        previous = _load_json(_execution_path(run_dir, attempt - 1), {})
        if not previous:
            raise SystemExit(
                f"Attempt {attempt - 1} evidence is missing. Execute attempts in order."
            )
        if _automatic_success(previous):
            raise SystemExit(
                f"Attempt {attempt - 1} already succeeded. The recovery protocol must stop."
            )

    poc_dir = generated_package / "poc"
    if not poc_dir.is_dir():
        raise SystemExit(f"PoC directory does not exist: {poc_dir}")
    poc_config = {
        **DEFAULT_POC_CONFIG,
        **metadata.get("poc", {}),
        **attempt_metadata.get("poc", {}),
    }

    setup_command = _command(poc_config.get("setup_command"), fixture)
    run_command = _command(poc_config.get("run_command"), fixture)
    output_globs = poc_config.get("output_globs", ["output/*.json"])
    if not run_command:
        raise SystemExit("No PoC run command could be resolved.")

    before = {
        str(path.resolve()): path.stat().st_mtime_ns
        for pattern in output_globs
        for path_string in glob.glob(str(poc_dir / pattern), recursive=True)
        if (path := Path(path_string)).is_file()
    }

    setup_result = (
        _run(setup_command, poc_dir, args.timeout)
        if setup_command
        else {
            "command": [],
            "cwd": str(poc_dir),
            "exit_code": 0,
            "duration_seconds": 0.0,
            "stdout": "No setup command configured; treated as not required.",
            "stderr": "",
        }
    )
    run_result = (
        _run(run_command, poc_dir, args.timeout)
        if setup_result.get("exit_code") == 0
        else {
            "command": run_command,
            "cwd": str(poc_dir),
            "exit_code": None,
            "duration_seconds": 0.0,
            "stdout": "",
            "stderr": "Run skipped because setup failed.",
        }
    )

    outputs: list[dict[str, Any]] = []
    for pattern in output_globs:
        for path_string in glob.glob(str(poc_dir / pattern), recursive=True):
            path = Path(path_string)
            if not path.is_file():
                continue
            changed = (
                str(path.resolve()) not in before
                or path.stat().st_mtime_ns > before[str(path.resolve())]
            )
            item: dict[str, Any] = {
                "path": str(path),
                "relative_path": str(path.relative_to(poc_dir)),
                "size_bytes": path.stat().st_size,
                "new_or_modified": changed,
                "sha256": _sha256(path),
                "json_parsed": False,
            }
            if path.suffix.lower() == ".json":
                try:
                    item["json_value"] = json.loads(path.read_text(encoding="utf-8"))
                    item["json_parsed"] = True
                except Exception as exc:
                    item["json_error"] = f"{type(exc).__name__}: {exc}"
            outputs.append(item)

    record = {
        "schema_version": "1.1.0",
        "run_id": metadata.get("run_id", run_dir.name),
        "attempt_number": attempt,
        "attempt_type": "original" if attempt == 0 else "refinement",
        "eq4_baseline": attempt == 0,
        "generated_package": str(generated_package),
        "configuration": {
            "source": str(
                execution_dir / "attempt_metadata.json"
                if attempt > 0 and attempt_metadata.get("poc")
                else metadata_path
            ),
            "uses_default_values": poc_config == DEFAULT_POC_CONFIG,
            "resolved_setup_command": setup_command or [],
            "resolved_run_command": run_command,
            "resolved_output_globs": output_globs,
        },
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "fixture": {
            "path": str(fixture),
            "sha256": _sha256(fixture),
            "size_bytes": fixture.stat().st_size,
        },
        "setup": setup_result,
        "execution": run_result,
        "outputs": outputs,
        "automatic_checks": {
            "EQ4-X01": setup_result.get("exit_code") == 0,
            "EQ4-X02": run_result.get("exit_code") == 0,
            "EQ4-X03": any(
                output["new_or_modified"]
                and output["size_bytes"] > 0
                and output["json_parsed"]
                for output in outputs
            ),
            "EQ4-X04": None
        },
        "automatic_execution_successful": False,
        "notes": "EQ4-X04 requires semantic comparison with fixtures/expected_rag_results.json, including citations and access-control behavior. Only attempt 0 is scored under EQ4; attempts 1-3 are a recovery diagnostic."
    }
    record["automatic_execution_successful"] = _automatic_success(record)

    json_path = execution_dir / "poc_execution.json"
    log_path = execution_dir / "poc_execution.log"
    execution_dir.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
    log_lines = [
        f"Run: {record['run_id']}",
        f"Attempt: {attempt} ({record['attempt_type']})",
        f"EQ4 baseline: {record['eq4_baseline']}",
        f"Fixture: {record['fixture']}",
        f"Setup command: {setup_result['command']}",
        f"Setup exit code: {setup_result['exit_code']}",
        "--- setup stdout ---",
        setup_result.get("stdout", ""),
        "--- setup stderr ---",
        setup_result.get("stderr", ""),
        f"Run command: {run_result['command']}",
        f"Run exit code: {run_result['exit_code']}",
        "--- run stdout ---",
        run_result.get("stdout", ""),
        "--- run stderr ---",
        run_result.get("stderr", ""),
        "--- outputs ---",
        json.dumps(outputs, indent=2, ensure_ascii=False),
    ]
    log_path.write_text("\n".join(log_lines), encoding="utf-8")
    print(f"Wrote {json_path}")
    print(f"Wrote {log_path}")
    recovery = _update_recovery_summary(run_dir, metadata)
    print(f"Updated {run_dir / 'poc_recovery.json'}: {recovery['status']}")
    return 0 if all(record["automatic_checks"][key] for key in ("EQ4-X01", "EQ4-X02", "EQ4-X03")) else 1


if __name__ == "__main__":
    raise SystemExit(main())
