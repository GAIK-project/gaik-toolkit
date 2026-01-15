#!/usr/bin/env python3
"""Fetch the latest GAIK package information from PyPI.

Usage:
    python fetch_pypi_readme.py              # Full info with description
    python fetch_pypi_readme.py --version    # Version only
    python fetch_pypi_readme.py --output FILE # Save to file

Fetches package metadata from https://pypi.org/pypi/gaik/json
No external dependencies required (uses stdlib only).
"""

import argparse
import json
import sys
from urllib.request import urlopen
from urllib.error import URLError, HTTPError

PYPI_URL = "https://pypi.org/pypi/gaik/json"


def fetch_pypi_info() -> dict:
    """Fetch package info from PyPI."""
    try:
        with urlopen(PYPI_URL, timeout=15) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as e:
        print(f"HTTP Error {e.code}: {e.reason}", file=sys.stderr)
        sys.exit(1)
    except URLError as e:
        print(f"Network error: {e.reason}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Invalid JSON response: {e}", file=sys.stderr)
        sys.exit(1)


def format_output(data: dict, include_description: bool = True) -> str:
    """Format PyPI data for display."""
    info = data["info"]

    # Extract just license name (first line if multi-line)
    license_text = info.get('license', 'MIT')
    if license_text and '\n' in license_text:
        license_text = license_text.split('\n')[0].strip()

    lines = [
        f"# GAIK v{info['version']}",
        "",
        f"**Summary:** {info.get('summary', 'N/A')}",
        f"**Author:** {info.get('author', 'GAIK Project')}",
        f"**License:** {license_text}",
        f"**Python:** {info.get('requires_python', '>=3.10')}",
        "",
        "## Links",
        f"- Homepage: {info.get('home_page', 'https://gaik.ai')}",
        f"- PyPI: https://pypi.org/project/gaik/",
        f"- Repository: {info.get('project_urls', {}).get('Repository', 'https://github.com/GAIK-project/gaik-toolkit')}",
        f"- Documentation: {info.get('project_urls', {}).get('Documentation', 'https://gaik-project.github.io/gaik-toolkit/')}",
    ]

    if include_description:
        description = info.get("description", "")
        if description:
            lines.extend([
                "",
                "## Description",
                "",
                description[:5000],  # Limit to first 5000 chars
            ])

    # Add release info
    releases = data.get("releases", {})
    if releases:
        latest_versions = sorted(releases.keys(), reverse=True)[:5]
        lines.extend([
            "",
            "## Recent Versions",
        ])
        for v in latest_versions:
            lines.append(f"- {v}")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Fetch GAIK package info from PyPI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python fetch_pypi_readme.py              # Show full info
  python fetch_pypi_readme.py --version    # Show version only
  python fetch_pypi_readme.py -o info.md   # Save to file
        """
    )
    parser.add_argument(
        "--version", "-v",
        action="store_true",
        help="Show version number only"
    )
    parser.add_argument(
        "--output", "-o",
        metavar="FILE",
        help="Output file (default: stdout)"
    )
    parser.add_argument(
        "--no-description",
        action="store_true",
        help="Exclude the full description"
    )
    args = parser.parse_args()

    data = fetch_pypi_info()

    if args.version:
        print(data["info"]["version"])
        return

    output = format_output(data, include_description=not args.no_description)

    if args.output:
        try:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(output)
            print(f"Saved to {args.output}")
        except IOError as e:
            print(f"Error writing file: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        print(output)


if __name__ == "__main__":
    main()
