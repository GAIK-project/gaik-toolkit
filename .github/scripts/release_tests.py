"""Add a "Tested" section to a Wizard V2 GitHub Release.

Run by whoever makes the release, after the tag's CI has finished:

    python .github/scripts/release_tests.py --tag wizard-v2-0.4.0 \\
        --uc "R48 (s4, 20 Nov): full path 59/59, frozen packages 59/59" --apply

It finds the Solution Wizard V2 run (and the whole-stack run, if any) for the
commit the tag points to, downloads their JUnit reports with `gh`, counts the
results per suite and writes a table with a link to each run. The use case
round is run by hand on s4, so its result is given with --uc; write the round,
the instance and the result only, never session ids or model names. Without
--apply the section is printed. With it, the section replaces an earlier one in
the release notes, or is appended.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from junit_summary import count  # noqa: E402

START, END = "<!-- tested:start -->", "<!-- tested:end -->"
SUITES = [  # (artifact, title)
    ("junit-wizard-api", "API (wizard_api)"),
    ("junit-solution-wizard", "Wizard V1 copy (solution_wizard)"),
    ("junit-web-app", "Web app (vitest)"),
    ("junit-e2e", "Browser tests (Playwright)"),
    ("junit-deploy-manifests", "Deploy manifests"),
]
STACK = ("stack-e2e-report", "Whole-stack browser tests")


def gh(*args: str) -> str:
    return subprocess.run(["gh", *args], check=True, capture_output=True, text=True).stdout


def latest_run(repo: str, workflow: str, sha: str) -> dict | None:
    runs = json.loads(
        gh(
            "run",
            "list",
            "--repo",
            repo,
            "--workflow",
            workflow,
            "--commit",
            sha,
            "--json",
            "databaseId,conclusion,status,url",
            "--limit",
            "20",
        )
    )
    done = [r for r in runs if r["status"] == "completed"]
    return done[0] if done else None


def download(repo: str, run_id: int, name: str, into: Path) -> list[Path]:
    target = into / name
    try:
        gh("run", "download", str(run_id), "--repo", repo, "--name", name, "--dir", str(target))
    except subprocess.CalledProcessError:
        return []
    return sorted(target.rglob("*.xml"))


def row(title: str, totals: dict[str, int] | None) -> str:
    if totals is None:
        return f"| {title} | – | – | – | no report in this run |"
    mark = "✅" if totals["failed"] == 0 else "❌"
    return f"| {title} | {totals['passed']} | {totals['failed']} | {totals['skipped']} | {mark} |"


def section(repo: str, tag: str, uc: str, run_id: int | None) -> str:
    sha = subprocess.run(
        ["git", "rev-list", "-n", "1", tag], check=True, capture_output=True, text=True
    ).stdout.strip()
    main = (
        {
            "databaseId": run_id,
            "url": f"https://github.com/{repo}/actions/runs/{run_id}",
            "conclusion": "?",
        }
        if run_id
        else latest_run(repo, "solution-wizard-v2.yml", sha)
    )
    stack = latest_run(repo, "wizard-v2-acceptance.yml", sha)
    lines = [START, "## Tested", "", f"Commit `{sha[:8]}`.", ""]
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        lines += ["| Suite | Passed | Failed | Skipped | |", "|---|---:|---:|---:|---|"]
        if main is None:
            lines.append(
                "| CI | – | – | – | no Solution Wizard V2 run for this commit; pass --run-id |"
            )
        else:
            for name, title in SUITES:
                lines.append(row(title, count(download(repo, main["databaseId"], name, tmpdir))))
        if stack is not None:
            lines.append(
                row(STACK[1], count(download(repo, stack["databaseId"], STACK[0], tmpdir)))
            )
        else:
            lines.append(f"| {STACK[1]} | – | – | – | no run for this commit |")
    lines.append("")
    if main is not None:
        lines.append(
            f"CI run: {main['url']}" + (f" · whole stack: {stack['url']}" if stack else "")
        )
    lines += ["", f"Use case round: {uc}", END]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--tag", required=True)
    ap.add_argument(
        "--uc",
        required=True,
        help="the use case round's result, for example 'R48 (s4): full path 59/59'",
    )
    ap.add_argument("--repo", default="NCF-public/gaik-toolkit-configuration-wizard-v2")
    ap.add_argument(
        "--run-id",
        type=int,
        help="the Solution Wizard V2 run to read, when none ran on the tag's commit",
    )
    ap.add_argument("--apply", action="store_true", help="write the section into the release notes")
    args = ap.parse_args()
    text = section(args.repo, args.tag, args.uc, args.run_id)
    if not args.apply:
        print(text)
        return 0
    body = (
        json.loads(gh("release", "view", args.tag, "--repo", args.repo, "--json", "body"))["body"]
        or ""
    )
    if START in body and END in body:
        body = body[: body.index(START)] + text + body[body.index(END) + len(END) :]
    else:
        body = (body.rstrip() + "\n\n" + text).lstrip()
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as fh:
        fh.write(body)
    gh("release", "edit", args.tag, "--repo", args.repo, "--notes-file", fh.name)
    print(f"Release {args.tag} updated.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
