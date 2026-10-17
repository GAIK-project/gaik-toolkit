#!/usr/bin/env python3
"""Check for Pandoc, which Word output needs, and install it only when asked.

  python install_pandoc.py --check      report whether Pandoc is found; install nothing
  python install_pandoc.py              install Pandoc if it is missing

Run the install only after the user has agreed to it: it downloads Pandoc from the internet.
It uses pypandoc's own installer, which unpacks the official Pandoc release into a per-user
folder (`~\\AppData\\Local\\Pandoc` on Windows, `~/Applications/pandoc` on macOS, `~/bin` on
Linux), needs no administrator rights and changes no system setting. pypandoc, which writes the
Word file, looks in those folders, so Pandoc works at once even when it is not on the PATH.

Every command takes --json to print one JSON result on stdout. Exit codes: 0 Pandoc is
available (found or installed), 4 it is missing, or the install failed, so Word output must be
turned off. Nothing here calls a model.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from typing import Any

EXIT_OK, EXIT_MISSING = 0, 4
MANUAL = (
    "Install it yourself, then run this check again: "
    "winget install --id JohnMacFarlane.Pandoc (Windows), brew install pandoc (macOS), "
    "sudo apt install pandoc (Debian, Ubuntu); or https://pandoc.org/installing.html"
)


def find_pandoc() -> dict[str, Any]:
    """Whether pypandoc can find a Pandoc program, and which."""
    try:
        import pypandoc
    except ImportError:
        return {"found": False, "reason": "the pypandoc package is not installed"}
    try:
        return {
            "found": True,
            "version": pypandoc.get_pandoc_version(),
            "path": pypandoc.get_pandoc_path(),
        }
    except OSError:
        return {"found": False, "reason": "the Pandoc program is not installed"}


def download_pandoc() -> None:
    import pypandoc

    # The installer is fetched into a temporary folder and removed, not left in the working one.
    with tempfile.TemporaryDirectory() as folder:
        pypandoc.download_pandoc(download_folder=folder, delete_installer=True)


def run(check_only: bool) -> tuple[int, dict[str, Any]]:
    state = find_pandoc()
    if state["found"]:
        return EXIT_OK, {**state, "installed_now": False}
    if check_only:
        return EXIT_MISSING, {**state, "installed_now": False, "next": MANUAL}
    if state.get("reason", "").startswith("the pypandoc package"):
        return EXIT_MISSING, {**state, "installed_now": False, "next": "pip install pypandoc"}
    try:
        download_pandoc()
    except Exception as exc:
        return EXIT_MISSING, {
            "found": False,
            "installed_now": False,
            "reason": f"the install failed: {type(exc).__name__}: {exc}",
            "next": MANUAL,
        }
    state = find_pandoc()
    if not state["found"]:
        return EXIT_MISSING, {
            **state,
            "installed_now": False,
            "reason": "the install finished but Pandoc is still not found",
            "next": MANUAL,
        }
    return EXIT_OK, {**state, "installed_now": True}


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Check for Pandoc and install it when asked.")
    parser.add_argument("--check", action="store_true", help="only report; install nothing")
    parser.add_argument("--json", action="store_true", help="print one JSON result on stdout")
    args = parser.parse_args(argv)
    code, result = run(args.check)
    result = {"ok": code == EXIT_OK, **result}
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    elif result["found"]:
        verb = "installed" if result["installed_now"] else "found"
        print(f"Pandoc {verb}: {result['version']} at {result['path']}")
    else:
        print(f"Pandoc is not available: {result['reason']}")
        print(result["next"])
    return code


if __name__ == "__main__":
    sys.exit(main())
