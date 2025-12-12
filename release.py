#!/usr/bin/env python3
"""
Release script for gaik-toolkit.

Usage:
    python release.py [version]

Examples:
    python release.py           # Interactive mode - suggests next version
    python release.py 0.4.0     # Direct mode - creates v0.4.0 tag

The script will:
1. Validate the version format (X.Y.Z)
2. Check that you're on main branch with clean working tree
3. Show recent tags for reference
4. Create and push the git tag
5. GitHub Actions will automatically publish to PyPI
"""

import re
import subprocess
import sys


def run(cmd: str, check: bool = True, capture: bool = True) -> subprocess.CompletedProcess:
    """Run a shell command."""
    result = subprocess.run(cmd, shell=True, capture_output=capture, text=True)
    if check and result.returncode != 0:
        print(f"Error running: {cmd}")
        print(result.stderr)
        sys.exit(1)
    return result


def get_current_branch() -> str:
    """Get current git branch name."""
    result = run("git branch --show-current")
    return result.stdout.strip()


def has_uncommitted_changes() -> bool:
    """Check if there are uncommitted changes."""
    result = run("git status --porcelain", check=False)
    return bool(result.stdout.strip())


def get_recent_tags(n: int = 5) -> list[str]:
    """Get the n most recent version tags."""
    result = run("git tag --sort=-v:refname", check=False)
    tags = [t for t in result.stdout.strip().split("\n") if t.startswith("v")]
    return tags[:n]


def validate_version(version: str) -> bool:
    """Validate version format is X.Y.Z (semver)."""
    pattern = r"^\d+\.\d+\.\d+$"
    return bool(re.match(pattern, version))


def suggest_next_version(current_tag: str) -> str:
    """Suggest next patch version based on current tag."""
    if not current_tag:
        return "0.1.0"
    version = current_tag.lstrip("v")
    parts = version.split(".")
    if len(parts) == 3:
        major, minor, patch = int(parts[0]), int(parts[1]), int(parts[2])
        return f"{major}.{minor}.{patch + 1}"
    return "0.1.0"


def tag_exists(tag: str) -> bool:
    """Check if a tag already exists."""
    result = run(f"git tag -l {tag}", check=False)
    return bool(result.stdout.strip())


def main():
    print("=" * 50)
    print("  GAIK Toolkit Release Script")
    print("=" * 50)
    print()

    # Check branch
    branch = get_current_branch()
    if branch != "main":
        print(f"⚠️  Warning: You are on branch '{branch}', not 'main'")
        response = input("Continue anyway? [y/N]: ").strip().lower()
        if response != "y":
            print("Aborted.")
            sys.exit(0)

    # Check for uncommitted changes
    if has_uncommitted_changes():
        print("❌ Error: You have uncommitted changes.")
        print("   Please commit or stash them first.")
        run("git status --short", capture=False)
        sys.exit(1)

    # Show recent tags and suggest next version
    recent_tags = get_recent_tags()
    suggested = suggest_next_version(recent_tags[0] if recent_tags else "")

    if recent_tags:
        print("Recent releases:")
        for tag in recent_tags:
            print(f"  - {tag}")
        print()

    # Get version from argument or prompt
    if len(sys.argv) > 1:
        version = sys.argv[1].lstrip("v")  # Remove 'v' prefix if provided
    else:
        version = input(f"Enter new version [{suggested}]: ").strip().lstrip("v")
        if not version:
            version = suggested

    # Validate version
    if not validate_version(version):
        print(f"❌ Error: Invalid version format '{version}'")
        print("   Must be X.Y.Z (e.g., 0.4.0, 1.0.0)")
        sys.exit(1)

    tag = f"v{version}"

    # Check if tag exists
    if tag_exists(tag):
        print(f"❌ Error: Tag '{tag}' already exists!")
        sys.exit(1)

    # Confirm
    print()
    print(f"📦 About to create release: {tag}")
    print()
    print("This will:")
    print(f"  1. Create git tag '{tag}'")
    print(f"  2. Push tag to origin")
    print(f"  3. GitHub Actions will publish to PyPI")
    print()

    response = input("Proceed? [y/N]: ").strip().lower()
    if response != "y":
        print("Aborted.")
        sys.exit(0)

    # Create and push tag
    print()
    print(f"Creating tag {tag}...")
    run(f'git tag -a {tag} -m "Release {tag}"')

    print(f"Pushing tag {tag} to origin...")
    run(f"git push origin {tag}")

    print()
    print("=" * 50)
    print(f"✅ Release {tag} created successfully!")
    print()
    print("Next steps:")
    print("  1. GitHub Actions will build and publish to PyPI")
    print("  2. Check: https://github.com/GAIK-project/gaik-toolkit/actions")
    print(f"  3. After publish: pip install gaik=={version}")
    print("=" * 50)


if __name__ == "__main__":
    main()
