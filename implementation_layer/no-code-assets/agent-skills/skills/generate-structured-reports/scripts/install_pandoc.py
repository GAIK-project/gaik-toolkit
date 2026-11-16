#!/usr/bin/env python3
"""Check for Pandoc, which Word output needs, and install it only when asked.

  python install_pandoc.py --check      report whether Pandoc is found; install nothing
  python install_pandoc.py              install Pandoc if it is missing

Run the install only after the user has agreed to it: it downloads Pandoc from the internet. It
downloads one pinned Pandoc release (PANDOC_VERSION) from its GitHub release page and checks
the file against the SHA-256 pinned below before anything is unpacked; a file that does not
match is deleted and nothing is installed. pypandoc's own installer then unpacks it into a
per-user folder (`~\\AppData\\Local\\Pandoc` on Windows, `~/Applications/pandoc` on macOS,
`~/bin` on Linux), needs no administrator rights and changes no system setting. pypandoc, which
writes the Word file, looks in those folders, so Pandoc works at once even when it is not on
the PATH.

Every command takes --json to print one JSON result on stdout. Exit codes: 0 Pandoc is
available (found or installed), 4 it is missing, or the install failed, so Word output must be
turned off. Nothing here calls a model.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
import tempfile
import urllib.request
from pathlib import Path
from typing import Any

EXIT_OK, EXIT_MISSING = 0, 4
MANUAL = (
    "Install it yourself, then run this check again: "
    "winget install --id JohnMacFarlane.Pandoc (Windows), brew install pandoc (macOS), "
    "sudo apt install pandoc (Debian, Ubuntu); or https://pandoc.org/installing.html"
)


# The Pandoc release the install fetches, and the SHA-256 and size of each installer, as the
# release lists them. To move to another release, update all three together.
PANDOC_VERSION = "3.10.2"
_RELEASE = f"https://github.com/jgm/pandoc/releases/download/{PANDOC_VERSION}/"
PANDOC_INSTALLERS: dict[tuple[str, str], tuple[str, str, int]] = {
    ("win32", "x86_64"): (
        f"pandoc-{PANDOC_VERSION}-windows-x86_64.msi",
        "937ed557c4565f4e7c7e1ee59cb059dfe8aafc9adb5b422bfdf688fcaee63a0b",
        41394176,
    ),
    ("darwin", "arm64"): (
        f"pandoc-{PANDOC_VERSION}-arm64-macOS.pkg",
        "0fa0892a05b1545948cf1ef5ef962f0c000b057b3c438510e1596c6f4b9d967d",
        41608515,
    ),
    ("darwin", "x86_64"): (
        f"pandoc-{PANDOC_VERSION}-x86_64-macOS.pkg",
        "d09aa0969d7dd5b3217f9f0121163ed522f04aee7bb185ac19ce29e7a8a50488",
        26052715,
    ),
    ("linux", "x86_64"): (
        f"pandoc-{PANDOC_VERSION}-1-amd64.deb",
        "6c06b69b49ae95087573631a6fcafb233ab7ab51e5cfa73f7539d6c964a2640d",
        34309822,
    ),
    ("linux", "arm64"): (
        f"pandoc-{PANDOC_VERSION}-1-arm64.deb",
        "868c7675806237dd21711e3890e82f2844e011c8f542a1ddc6245df4324dd6b5",
        36798968,
    ),
}
_MACHINES = {"amd64": "x86_64", "x86_64": "x86_64", "arm64": "arm64", "aarch64": "arm64"}


class InstallerMismatchError(RuntimeError):
    """The downloaded installer is not the pinned file."""


def pinned_installer() -> tuple[str, str, int]:
    """The installer name, SHA-256 and size pinned for this platform."""
    system = "linux" if sys.platform.startswith("linux") else sys.platform
    machine = _MACHINES.get(platform.machine().lower(), platform.machine().lower())
    if system == "win32":
        machine = "x86_64"  # Pandoc ships one Windows build; Windows on Arm runs it emulated.
    try:
        return PANDOC_INSTALLERS[(system, machine)]
    except KeyError:
        raise RuntimeError(f"no pinned Pandoc installer for {system} {machine}") from None


def fetch_checked(name: str, sha256: str, size: int, folder: Path) -> Path:
    """Download a pinned installer into ``folder`` and check its size and SHA-256."""
    target = folder / name
    digest = hashlib.sha256()
    received = 0
    with urllib.request.urlopen(_RELEASE + name, timeout=60) as response:  # noqa: S310
        with target.open("wb") as out:
            while chunk := response.read(1 << 20):
                received += len(chunk)
                if received > size:
                    break
                digest.update(chunk)
                out.write(chunk)
    if received != size or digest.hexdigest() != sha256:
        target.unlink(missing_ok=True)
        raise InstallerMismatchError(
            f"the downloaded {name} does not match the pinned SHA-256; nothing was installed"
        )
    return target


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
    from pypandoc.pandoc_download import download_pandoc as unpack_pandoc

    name, sha256, size = pinned_installer()
    # The installer is fetched into a temporary folder and removed, not left in the working one.
    # pypandoc finds the checked file there and unpacks it instead of downloading its own.
    with tempfile.TemporaryDirectory() as folder:
        fetch_checked(name, sha256, size, Path(folder))
        unpack_pandoc(
            url=_RELEASE + name,
            version=PANDOC_VERSION,
            download_folder=folder,
            delete_installer=True,
        )


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
