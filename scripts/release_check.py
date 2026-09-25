"""Reproducible local/CI release gate, including authenticated component tests.

Run from the repository: uv run python scripts/release_check.py --live --version 0.8.0
Configure RELEASE_PROVIDERS and explicit RELEASE_<PROVIDER>_MODEL values.
No missing credential, failed request, incomplete result, or empty matrix is a pass.
"""

from __future__ import annotations

import argparse
import email
import hashlib
import json
import os
import re
import signal
import subprocess
import sys
import tarfile
import tempfile
import time
import zipfile
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
SUPPORTED_PROVIDERS = {
    "azure",
    "openai",
    "google",
    "vertex",
    "aitta",
    "anthropic",
    "anthropic_foundry",
}
REQUIRED_CHECKS = {
    "chat",
    "stream",
    "schema_generator",
    "data_extractor",
    "answer_generator",
    "document_classifier",
}
MODEL_ENV_FALLBACKS = {
    "azure": "AZURE_DEPLOYMENT",
    "openai": "OPENAI_MODEL",
    "google": "GOOGLE_MODEL",
    "vertex": "GOOGLE_MODEL",
    "aitta": "AITTA_MODEL",
    "anthropic": "ANTHROPIC_MODEL",
    "anthropic_foundry": "ANTHROPIC_MODEL",
}
# The library is currently well below this. A larger artifact needs a deliberate
# packaging review before PyPI; accidentally bundling the monorepo must fail.
MAX_DISTRIBUTION_BYTES = 10 * 1024 * 1024


def select_targets(providers: str, environ: dict, required: list[str] = ()) -> list[dict]:
    names = list(dict.fromkeys([*required, *[p.strip().lower() for p in providers.split(",")]]))
    if not names or any(not name for name in names):
        raise ValueError("RELEASE_PROVIDERS must contain at least one explicit provider")
    targets = []
    for name in names:
        if name not in SUPPORTED_PROVIDERS:
            raise ValueError(f"Unsupported release provider: {name}")
        prefix = f"RELEASE_{name.upper()}"
        model = environ.get(prefix + "_MODEL") or environ.get(MODEL_ENV_FALLBACKS[name])
        if not model or not model.strip():
            raise ValueError(f"Set {prefix}_MODEL to the exact certified model/deployment ID")
        backends = environ.get(prefix + "_BACKENDS", "native").split(",")
        backends = list(
            dict.fromkeys(
                (["native"] if name in required else []) + [backend.strip() for backend in backends]
            )
        )
        if any(backend not in {"native", "litellm"} for backend in backends):
            raise ValueError(f"{prefix}_BACKENDS supports native,litellm")
        for backend in backends:
            targets.append(
                {
                    "provider": name,
                    "backend": backend,
                    "model": model.strip(),
                    "embedding_model": environ.get(prefix + "_EMBEDDING_MODEL", "").strip(),
                }
            )
    return targets


def validate_live_result(result: dict, target: dict, returncode: int) -> bool:
    required = REQUIRED_CHECKS | ({"embedder"} if target.get("embedding_model") else set())
    checks = result.get("checks", {})
    return (
        returncode == 0
        and result.get("ok") is True
        and result.get("authenticated_live") is True
        and result.get("provider") == target["provider"]
        and result.get("backend") == target.get("backend", "native")
        and result.get("model") == target["model"]
        and (
            not target.get("embedding_model")
            or result.get("embedding_model") == target["embedding_model"]
        )
        and all(
            isinstance(checks.get(name), dict) and checks[name].get("ok") is True
            for name in required
        )
    )


def wheel_version(path: Path) -> str:
    with zipfile.ZipFile(path) as wheel:
        metadata_paths = [name for name in wheel.namelist() if name.endswith(".dist-info/METADATA")]
        if len(metadata_paths) != 1:
            raise ValueError("Wheel must contain exactly one package metadata file")
        metadata = email.message_from_bytes(wheel.read(metadata_paths[0]))
        if metadata["Name"] != "gaik":
            raise ValueError("Release wheel is not gaik")
        return metadata["Version"]


def validate_distributions(directory: Path, version: str, source_root: Path | None = None) -> list:
    """Verify the sdist-built wheel preserves every runtime file without repo data."""
    source_root = source_root or ROOT / "implementation_layer/src/gaik"
    wheels, sdists = list(directory.glob("*.whl")), list(directory.glob("*.tar.gz"))
    if len(wheels) != 1 or len(sdists) != 1:
        raise ValueError("Release requires exactly one wheel and one source distribution")
    artifacts = [wheels[0], sdists[0]]
    if any(path.stat().st_size > MAX_DISTRIBUTION_BYTES for path in artifacts):
        raise ValueError("Release artifact exceeds the 10 MiB library packaging budget")
    if wheel_version(wheels[0]) != version:
        raise ValueError("Built wheel version does not match the planned release")
    expected = {
        "gaik/" + path.relative_to(source_root).as_posix(): path.read_bytes()
        for path in source_root.rglob("*")
        if path.is_file() and (path.suffix in {".py", ".sql"} or path.name == "py.typed")
    }
    if "gaik/__init__.py" not in expected or "gaik/py.typed" not in expected:
        raise ValueError("Library source or its py.typed marker is missing")
    with zipfile.ZipFile(wheels[0]) as wheel:
        packaged = {name: wheel.read(name) for name in wheel.namelist() if name.startswith("gaik/")}
    if packaged != expected:
        raise ValueError("Wheel runtime files differ from the library source (including SQL/typing)")

    source_files = {}
    metadata_files = {"README.md", "LICENSE", "pyproject.toml", "MANIFEST.in", "PKG-INFO", "setup.cfg"}
    egg_metadata = {"PKG-INFO", "SOURCES.txt", "dependency_links.txt", "requires.txt", "top_level.txt"}
    with tarfile.open(sdists[0], "r:gz") as archive:
        for member in archive.getmembers():
            path = PurePosixPath(member.name)
            if path.parts[0] != f"gaik-{version}" or ".." in path.parts or path.is_absolute():
                raise ValueError("Unexpected source distribution root or unsafe path")
            if member.isdir():
                continue
            if not member.isfile():
                raise ValueError("Source distribution must not contain links or special files")
            relative = PurePosixPath(*path.parts[1:]).as_posix()
            prefix = "implementation_layer/src/"
            if relative.startswith(prefix + "gaik/"):
                source_files[relative.removeprefix(prefix)] = archive.extractfile(member).read()
            elif relative in metadata_files:
                if relative == "PKG-INFO":
                    metadata = email.message_from_bytes(archive.extractfile(member).read())
                    if metadata["Name"] != "gaik" or metadata["Version"] != version:
                        raise ValueError("Source distribution metadata does not match the release")
            elif not (
                relative.startswith(prefix + "gaik.egg-info/") and path.name in egg_metadata
            ):
                raise ValueError("Source distribution contains files outside the library allowlist")
    if source_files != expected:
        raise ValueError("Source distribution runtime files differ from the library source")
    return [
        {
            "filename": path.name,
            "bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "runtime_files": len(expected),
        }
        for path in artifacts
    ]


def _git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def _write_report(path: Path, report: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


def _run_command(command: list[str], *, timeout: float, env=None):
    """Enforce deadlines on the entire uv/Python process tree, including Windows."""
    options = (
        {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
        if os.name == "nt"
        else {"start_new_session": True}
    )
    with subprocess.Popen(command, cwd=ROOT, env=env, **options) as process:
        try:
            returncode = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                )
                if process.poll() is None:
                    process.kill()
            else:
                os.killpg(process.pid, signal.SIGKILL)
            process.wait()
            raise
    return subprocess.CompletedProcess(command, returncode)


def run_gate(args) -> dict:
    report = {
        "schema_version": 1,
        "planned_version": args.version,
        "started_utc": datetime.now(UTC).isoformat(),
        "git_commit": _git("rev-parse", "HEAD"),
        "worktree_clean": not bool(_git("status", "--porcelain", "--untracked-files=normal")),
        "stages": [],
        "live": [],
        "release_ready": False,
    }
    _write_report(args.report, report)

    def stage(name: str, command: list[str], *, timeout: int = 1800, env=None) -> bool:
        print(f"[release] {name}", flush=True)
        start = time.monotonic()
        try:
            completed = _run_command(command, env=env, timeout=timeout)
            entry = {
                "name": name,
                "ok": completed.returncode == 0,
                "exit_code": completed.returncode,
            }
        except subprocess.TimeoutExpired:
            entry = {"name": name, "ok": False, "error_type": "TimeoutExpired"}
        entry["elapsed_s"] = round(time.monotonic() - start, 2)
        report["stages"].append(entry)
        _write_report(args.report, report)
        return entry["ok"]

    try:
        if not re.fullmatch(r"\d+\.\d+\.\d+", args.version):
            raise ValueError("--version must be a numeric release version, such as 0.8.0")
        targets = select_targets(args.providers, os.environ, args.require_provider)
        report["selected_targets"] = targets
        pin = ROOT / "implementation_layer/solution_wizard/gaik_validated_version.txt"
        if pin.read_text(encoding="utf-8").strip() != args.version:
            raise ValueError("Wizard validated version must match --version before release")
        if not report["worktree_clean"]:
            raise ValueError("Commit release files before certification so the report binds HEAD")

        if not stage("all-extras", ["uv", "sync", "--all-extras"]):
            return report
        test_env = {**os.environ, "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"}
        uv_python = ["uv", "run", "--no-sync", "python"]
        if not stage(
            "offline-tests",
            [*uv_python, "-m", "pytest", "-m", "not llm", "--strict-markers"],
            env=test_env,
        ):
            return report
        if not stage(
            "wizard-tests",
            [*uv_python, "-m", "pytest", "implementation_layer/solution_wizard/tests", "-q"],
            env=test_env,
        ):
            return report
        if not stage(
            "wizard-audit",
            [*uv_python, ".claude/skills/gaik-sync/scripts/audit_registry.py", "--strict"],
        ):
            return report

        with tempfile.TemporaryDirectory(prefix="gaik-release-check-") as temp:
            temp_dir = Path(temp)
            build_env = {**os.environ, "SETUPTOOLS_SCM_PRETEND_VERSION_FOR_GAIK": args.version}
            if not stage(
                "build",
                [*uv_python, "-m", "build", "--outdir", str(temp_dir / "dist")],
                env=build_env,
            ):
                return report
            report["distributions"] = validate_distributions(temp_dir / "dist", args.version)
            report["wheel_version"] = args.version
            distributions = [str(path) for path in (temp_dir / "dist").iterdir()]
            if not stage("package-metadata", [*uv_python, "-m", "twine", "check", *distributions]):
                return report

            for target in targets:
                print(
                    f"[release] live {target['provider']}/{target['backend']} / {target['model']}",
                    flush=True,
                )
                result_path = temp_dir / f"{target['provider']}-{target['backend']}.json"
                command = [
                    *uv_python,
                    "scripts/release_smoke.py",
                    "--provider",
                    target["provider"],
                    "--backend",
                    target["backend"],
                    "--model",
                    target["model"],
                    "--timeout",
                    str(args.request_timeout),
                    "--output-tokens",
                    str(args.output_tokens),
                    "--max-calls",
                    "10",
                    "--result",
                    str(result_path),
                ]
                if target["embedding_model"]:
                    command += ["--embedding-model", target["embedding_model"]]
                try:
                    completed = _run_command(command, timeout=args.provider_timeout)
                    result = json.loads(result_path.read_text(encoding="utf-8"))
                    passed = validate_live_result(result, target, completed.returncode)
                except (subprocess.TimeoutExpired, OSError, ValueError) as exc:
                    result = {
                        "provider": target["provider"],
                        "backend": target["backend"],
                        "model": target["model"],
                        "ok": False,
                        "error_type": type(exc).__name__,
                    }
                    passed = False
                result["gate_passed"] = passed
                report["live"].append(result)
                _write_report(args.report, report)
        report["release_ready"] = (
            all(stage["ok"] for stage in report["stages"])
            and len(report["live"]) == len(targets)
            and all(result["gate_passed"] for result in report["live"])
            and _git("rev-parse", "HEAD") == report["git_commit"]
            and not bool(_git("status", "--porcelain", "--untracked-files=normal"))
        )
    except Exception as exc:
        # Configuration messages are deliberately authored here and contain no
        # credential values. Unexpected exception bodies must never be logged.
        report["error_type"] = type(exc).__name__
        if isinstance(exc, ValueError):
            report["configuration_error"] = str(exc)
    finally:
        report["finished_utc"] = datetime.now(UTC).isoformat()
        _write_report(args.report, report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--live",
        action="store_true",
        required=True,
        help="Explicitly authorize the bounded authenticated provider requests",
    )
    parser.add_argument("--version", required=True)
    parser.add_argument("--providers", default=os.getenv("RELEASE_PROVIDERS", "azure"))
    parser.add_argument(
        "--require-provider",
        action="append",
        default=[],
        help="CI uses azure so the repository matrix cannot remove its minimum",
    )
    parser.add_argument("--request-timeout", type=float, default=180)
    parser.add_argument("--provider-timeout", type=int, default=900)
    parser.add_argument("--output-tokens", type=int, default=2048)
    parser.add_argument("--report", type=Path, default=ROOT / "results/release-check.json")
    args = parser.parse_args()
    if not 1 <= args.output_tokens <= 8192:
        parser.error("--output-tokens must be between 1 and 8192")
    if not 1 <= args.request_timeout <= args.provider_timeout <= 1800:
        parser.error("Require 1 <= request-timeout <= provider-timeout <= 1800 seconds")
    report = run_gate(args)
    print(json.dumps({"release_ready": report["release_ready"], "report": str(args.report)}))
    return 0 if report["release_ready"] else 1


if __name__ == "__main__":
    sys.exit(main())
