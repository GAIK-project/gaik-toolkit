"""Write a JUnit XML report as a table in the GitHub Actions run summary.

Usage: junit_summary.py TITLE REPORT.xml [REPORT.xml ...]

Appends to $GITHUB_STEP_SUMMARY (or prints when it is unset). A missing report
is listed as such rather than failing, so the step can run with `if: always()`
after a test step that never got to write one. The exit code is always 0: the
test step itself decides whether the job fails.
"""

from __future__ import annotations

import html
import os
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

MAX_FAILURES = 50
MAX_MESSAGE = 2000


def _cases(root: ET.Element):
    yield from root.iter("testcase")


def summarize(title: str, paths: list[Path]) -> str:
    totals = {"passed": 0, "failed": 0, "skipped": 0}
    failures: list[tuple[str, str]] = []
    missing: list[str] = []
    seconds = 0.0

    for path in paths:
        if not path.is_file():
            missing.append(path.name)
            continue
        try:
            root = ET.parse(path).getroot()
        except ET.ParseError as exc:
            missing.append(f"{path.name} (unreadable: {exc})")
            continue
        for case in _cases(root):
            seconds += float(case.get("time") or 0)
            name = "::".join(p for p in (case.get("classname"), case.get("name")) if p)
            problem = case.find("failure")
            if problem is None:
                problem = case.find("error")
            if problem is not None:
                totals["failed"] += 1
                text = problem.get("message") or ""
                if problem.text:
                    text = f"{text}\n{problem.text}".strip()
                failures.append((name, text[:MAX_MESSAGE]))
            elif case.find("skipped") is not None:
                totals["skipped"] += 1
            else:
                totals["passed"] += 1

    icon = "❌" if totals["failed"] or missing else "✅"
    lines = [
        f"### {icon} {title}",
        "",
        "| Passed | Failed | Skipped | Time |",
        "|---:|---:|---:|---:|",
        f"| {totals['passed']} | {totals['failed']} | {totals['skipped']} | {seconds:.1f} s |",
        "",
    ]
    for name in missing:
        lines.append(f"No report: `{name}`. The tests did not run to the end.")
        lines.append("")
    for name, text in failures[:MAX_FAILURES]:
        lines.append(f"<details><summary>❌ <code>{html.escape(name)}</code></summary>")
        lines.append("")
        lines.append(f"<pre>{html.escape(text)}</pre>")
        lines.append("</details>")
        lines.append("")
    if len(failures) > MAX_FAILURES:
        lines.append(f"…and {len(failures) - MAX_FAILURES} more failures; see the job log.")
        lines.append("")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print(__doc__, file=sys.stderr)
        return 0
    text = summarize(argv[1], [Path(p) for p in argv[2:]])
    target = os.environ.get("GITHUB_STEP_SUMMARY")
    if target:
        with open(target, "a", encoding="utf-8") as fh:
            fh.write(text + "\n")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
