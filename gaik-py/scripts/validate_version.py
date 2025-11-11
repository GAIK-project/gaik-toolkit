#!/usr/bin/env python3
"""Validate that git tag matches pyproject.toml version before release."""

import re
import sys
from pathlib import Path


def validate_version(tag: str) -> bool:
    """Check if git tag matches pyproject.toml version.

    Args:
        tag: Git tag (e.g., "v0.2.4")

    Returns:
        True if versions match, False otherwise
    """
    # Parse tag version
    tag_match = re.match(r"^v(\d+\.\d+\.\d+)$", tag)
    if not tag_match:
        print(f"❌ Invalid tag format: {tag}")
        print("   Expected format: v0.2.4")
        return False

    tag_version = tag_match.group(1)

    # Read pyproject.toml version
    pyproject = Path(__file__).parent.parent / "pyproject.toml"
    if not pyproject.exists():
        print(f"❌ File not found: {pyproject}")
        return False

    content = pyproject.read_text()
    version_match = re.search(r'version = "(\d+\.\d+\.\d+)"', content)

    if not version_match:
        print("❌ Version not found in pyproject.toml")
        return False

    file_version = version_match.group(1)

    # Compare versions
    if tag_version != file_version:
        print(f"❌ Version mismatch!")
        print(f"   Git tag:        v{tag_version}")
        print(f"   pyproject.toml:  {file_version}")
        print(f"\n💡 Fix: Update version in gaik-py/pyproject.toml to {tag_version}")
        return False

    print(f"✅ Version validation passed: {tag_version}")
    return True


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python gaik-py/tests/validate_version.py v0.2.4")
        sys.exit(1)

    tag = sys.argv[1]
    if not validate_version(tag):
        sys.exit(1)
