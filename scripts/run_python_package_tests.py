#!/usr/bin/env python3
"""Utility to install and test every Python package under packages/."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict

try:  # Python 3.11+
    import tomllib  # type: ignore[attr-defined]
except ModuleNotFoundError:  # pragma: no cover - fallback for 3.10
    try:
        import tomli as tomllib  # type: ignore[import-not-found]
    except ModuleNotFoundError:
        subprocess.run([sys.executable, "-m", "pip", "install", "tomli"], check=True)
        import tomli as tomllib  # type: ignore[import-not-found]

REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGES_ROOT = REPO_ROOT / "packages"


def run_command(
    command: list[str], *, cwd: Path | None = None, env: Dict[str, str] | None = None
) -> None:
    """Run a subprocess and raise if it fails."""
    print(f"\n➡️  Running: {' '.join(command)}")
    completed = subprocess.run(command, cwd=cwd, env=env, check=False)
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)


def discover_python_packages() -> list[Path]:
    """Return every directory under packages/ that contains a pyproject.toml."""
    if not PACKAGES_ROOT.exists():
        return []
    return sorted(path.parent for path in PACKAGES_ROOT.glob("*/pyproject.toml"))


def load_metadata(package_dir: Path) -> Dict[str, Any]:
    """Load pyproject metadata for a given package directory."""
    pyproject = package_dir / "pyproject.toml"
    with pyproject.open("rb") as handle:
        return tomllib.load(handle)


def determine_extras(metadata: Dict[str, Any]) -> list[str]:
    """Return a prioritized list of extras to install for CI."""
    optional = metadata.get("project", {}).get("optional-dependencies", {}) or {}

    if "ci" in optional:
        return ["ci"]

    extras: list[str] = []
    for candidate in ("dev", "test", "tests"):
        if candidate in optional:
            extras.append(candidate)

    # Heuristic extras that frequently contain provider/test deps
    for candidate in ("extract", "vision"):
        if candidate in optional and candidate not in extras:
            extras.append(candidate)

    return extras


def main() -> None:
    packages = discover_python_packages()
    if not packages:
        print("⚠️  No Python packages discovered under packages/.")
        return

    run_command(
        [sys.executable, "-m", "pip", "install", "--upgrade", "pip"], cwd=REPO_ROOT
    )

    for package_dir in packages:
        metadata = load_metadata(package_dir)
        package_name = metadata["project"]["name"]
        extras = determine_extras(metadata)
        extras_suffix = f"[{','.join(extras)}]" if extras else ""
        editable_target = f"{package_dir.as_posix()}{extras_suffix}"

        print(f"\n=== 🧪 Testing package: {package_name} ({package_dir}) ===")
        run_command(
            [sys.executable, "-m", "pip", "install", "-e", editable_target],
            cwd=package_dir,
        )

        coverage_file = package_dir / f".coverage.{package_name}"
        coverage_xml = package_dir / "coverage.xml"
        env = os.environ.copy()
        env["COVERAGE_FILE"] = str(coverage_file)

        pytest_command = [
            sys.executable,
            "-m",
            "pytest",
            "-v",
            "--strict-markers",
            f"--cov={package_name}",
            "--cov-report=term",
            f"--cov-report=xml:{coverage_xml}",
        ]
        run_command(pytest_command, cwd=package_dir, env=env)

    print("\n✅ All Python packages tested successfully.")


if __name__ == "__main__":
    main()
