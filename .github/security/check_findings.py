"""Apply the CI security policy to pip-audit, npm audit and Trivy reports.

Policy: a HIGH or CRITICAL finding that has a fix available fails the check,
unless an unexpired entry in allowlist.toml covers it. Every other finding is
reported and does not fail. For a Trivy misconfiguration the fix is a change
to the Dockerfile or manifest, so it always counts as fixable.

pip-audit reports no severity, so this looks each advisory up in OSV
(api.osv.dev, no credentials): the GitHub advisory rating first, then a CVSS
v3 vector. A fixable advisory whose severity cannot be found fails closed,
because nothing shows it is below HIGH; allowlist it if it is accepted.

Usage:
  python check_findings.py --allowlist allowlist.toml \
      --report pip-audit:wizard-api=wizard-api.json \
      --report npm-audit:solution-wizard-v2=npm.json \
      --report trivy:config=trivy-config.json

Writes a Markdown summary to stdout and, in GitHub Actions, to the job summary.
Exit codes: 0 pass, 1 blocking findings, 2 bad input or allowlist.
"""

from __future__ import annotations

import argparse
import datetime as dt
import fnmatch
import json
import math
import os
import re
import sys
import tomllib
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

BLOCKING = {"CRITICAL", "HIGH"}
ORDER = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "UNKNOWN"]
OSV_URL = "https://api.osv.dev/v1/vulns/{}"


@dataclass
class Finding:
    source: str  # pip-audit / npm-audit / trivy
    label: str  # what was scanned
    id: str
    package: str
    version: str
    severity: str
    fixable: bool
    fix: str
    title: str
    target: str = ""
    aliases: set[str] = field(default_factory=set)

    @property
    def ids(self) -> set[str]:
        return {self.id, *self.aliases}

    @property
    def blocking_severity(self) -> bool:
        # pip-audit's UNKNOWN means OSV had no rating: fail closed on it.
        # Trivy's UNKNOWN is the advisory's own rating and is only reported.
        if self.severity == "UNKNOWN":
            return self.source == "pip-audit"
        return self.severity in BLOCKING


@dataclass
class Entry:
    id: str
    reason: str
    expires: dt.date
    package: str | None = None
    target: str | None = None
    source: str | None = None
    used: bool = False

    def matches(self, f: Finding) -> bool:
        if self.id not in f.ids:
            return False
        if self.source and self.source != f.source:
            return False
        if self.package and self.package != f.package:
            return False
        if self.target and not fnmatch.fnmatch(f.target or f.label, self.target):
            return False
        return True


# ---------------------------------------------------------------- severities


def normalise(severity: str | None) -> str:
    s = (severity or "").upper()
    if s == "MODERATE":
        return "MEDIUM"
    return s if s in ORDER else "UNKNOWN"


def _roundup(x: float) -> float:
    i = int(round(x * 100000))
    return i / 100000.0 if i % 10000 == 0 else (math.floor(i / 10000) + 1) / 10.0


def cvss3_score(vector: str) -> float | None:
    """Base score of a CVSS v3.x vector, per the FIRST specification."""
    m = dict(p.split(":", 1) for p in vector.split("/")[1:] if ":" in p)
    try:
        scope_changed = m["S"] == "C"
        av = {"N": 0.85, "A": 0.62, "L": 0.55, "P": 0.2}[m["AV"]]
        ac = {"L": 0.77, "H": 0.44}[m["AC"]]
        pr = {
            "N": 0.85,
            "L": 0.68 if scope_changed else 0.62,
            "H": 0.5 if scope_changed else 0.27,
        }[m["PR"]]
        ui = {"N": 0.85, "R": 0.62}[m["UI"]]
        cia = {"H": 0.56, "L": 0.22, "N": 0.0}
        c, i, a = cia[m["C"]], cia[m["I"]], cia[m["A"]]
    except KeyError:
        return None
    iss = 1 - (1 - c) * (1 - i) * (1 - a)
    if scope_changed:
        impact = 7.52 * (iss - 0.029) - 3.25 * (iss - 0.02) ** 15
    else:
        impact = 6.42 * iss
    if impact <= 0:
        return 0.0
    exploitability = 8.22 * av * ac * pr * ui
    total = impact + exploitability
    if scope_changed:
        total *= 1.08
    return _roundup(min(total, 10))


def rating(score: float) -> str:
    if score >= 9.0:
        return "CRITICAL"
    if score >= 7.0:
        return "HIGH"
    if score >= 4.0:
        return "MEDIUM"
    return "LOW" if score > 0 else "UNKNOWN"


_osv_cache: dict[str, dict | None] = {}


def osv(vuln_id: str) -> dict | None:
    if vuln_id not in _osv_cache:
        try:
            with urllib.request.urlopen(OSV_URL.format(vuln_id), timeout=20) as r:
                _osv_cache[vuln_id] = json.load(r)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            _osv_cache[vuln_id] = None
    return _osv_cache[vuln_id]


def osv_severity(ids: set[str]) -> str:
    # GHSA records carry the GitHub rating; PYSEC records often only a vector.
    records = [osv(i) for i in sorted(ids, key=lambda i: not i.startswith("GHSA-"))]
    for rec in records:
        if rec and rec.get("database_specific", {}).get("severity"):
            return normalise(rec["database_specific"]["severity"])
    for rec in records:
        for sev in (rec or {}).get("severity", []):
            if sev.get("type") == "CVSS_V3":
                score = cvss3_score(sev.get("score", ""))
                if score is not None:
                    return rating(score)
    return "UNKNOWN"


# ------------------------------------------------------------------- parsers


def parse_pip_audit(label: str, data: dict) -> list[Finding]:
    out, seen = [], set()
    for dep in data.get("dependencies", []):
        for v in dep.get("vulns", []):
            key = (dep["name"], v["id"])
            if key in seen:
                continue
            seen.add(key)
            fixes = v.get("fix_versions") or []
            aliases = set(v.get("aliases") or [])
            out.append(
                Finding(
                    source="pip-audit",
                    label=label,
                    id=v["id"],
                    aliases=aliases,
                    package=dep["name"],
                    version=dep.get("version", ""),
                    severity=osv_severity({v["id"], *aliases}),
                    fixable=bool(fixes),
                    fix=", ".join(fixes),
                    title=(v.get("description") or "").split("\n", 1)[0][:100],
                )
            )
    return out


def parse_npm_audit(label: str, data: dict) -> list[Finding]:
    if "vulnerabilities" not in data:
        raise ValueError("not an npm audit --json (v2) report")
    out, seen = [], set()
    for pkg, v in data["vulnerabilities"].items():
        fix = v.get("fixAvailable")
        if isinstance(fix, dict):
            fix_text = f"{fix.get('name')}@{fix.get('version')}"
            if fix.get("isSemVerMajor"):
                fix_text += " (semver-major)"
        else:
            fix_text = "npm audit fix" if fix else ""
        # String entries in `via` point at another package's advisory, which is
        # reported under that package; only the advisories themselves count.
        for adv in v.get("via", []):
            if not isinstance(adv, dict):
                continue
            url = adv.get("url", "")
            m = re.search(r"GHSA(-[0-9a-z]{4}){3}", url)
            vid = m.group(0) if m else str(adv.get("source"))
            if (pkg, vid) in seen:
                continue
            seen.add((pkg, vid))
            out.append(
                Finding(
                    source="npm-audit",
                    label=label,
                    id=vid,
                    package=adv.get("name", pkg),
                    version=adv.get("range", ""),
                    severity=normalise(adv.get("severity")),
                    fixable=bool(fix),
                    fix=fix_text,
                    title=(adv.get("title") or "")[:100],
                )
            )
    return out


def parse_trivy(label: str, data: dict) -> list[Finding]:
    out = []
    for res in data.get("Results") or []:
        target = res.get("Target", "")
        for v in res.get("Vulnerabilities") or []:
            fixed = v.get("FixedVersion") or ""
            out.append(
                Finding(
                    source="trivy",
                    label=label,
                    target=target,
                    id=v["VulnerabilityID"],
                    package=v.get("PkgName", ""),
                    version=v.get("InstalledVersion", ""),
                    severity=normalise(v.get("Severity")),
                    fixable=bool(fixed),
                    fix=fixed,
                    title=(v.get("Title") or "")[:100],
                )
            )
        for mc in res.get("Misconfigurations") or []:
            if mc.get("Status") != "FAIL":
                continue
            aliases = {a for a in (mc.get("AVDID"), mc.get("ID")) if a}
            out.append(
                Finding(
                    source="trivy",
                    label=label,
                    target=target,
                    id=mc.get("ID") or mc.get("AVDID", ""),
                    aliases=aliases,
                    package="",
                    version="",
                    severity=normalise(mc.get("Severity")),
                    fixable=True,
                    fix=(mc.get("Resolution") or "")[:100],
                    title=(mc.get("Title") or "")[:100],
                )
            )
    return out


PARSERS = {"pip-audit": parse_pip_audit, "npm-audit": parse_npm_audit, "trivy": parse_trivy}


# ------------------------------------------------------------------ allowlist


def load_allowlist(path: Path) -> list[Entry]:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    entries = []
    for n, raw in enumerate(data.get("finding", []), 1):
        missing = [k for k in ("id", "reason", "expires") if not raw.get(k)]
        if missing:
            raise ValueError(f"allowlist entry {n}: missing {', '.join(missing)}")
        if not isinstance(raw["expires"], dt.date):
            raise ValueError(f"allowlist entry {n}: expires must be a date (YYYY-MM-DD)")
        unknown = set(raw) - {"id", "reason", "expires", "package", "target", "source"}
        if unknown:
            raise ValueError(f"allowlist entry {n}: unknown keys {sorted(unknown)}")
        entries.append(Entry(**raw))
    return entries


# --------------------------------------------------------------------- report


def counts(findings: list[Finding]) -> str:
    by = {s: 0 for s in ORDER}
    for f in findings:
        by[f.severity] += 1
    return " · ".join(f"{s.lower()} {n}" for s, n in by.items() if n) or "none"


def row(f: Finding, extra: str = "") -> str:
    where = f.target or f.label
    pkg = f"{f.package} {f.version}".strip() or "-"
    return f"| {f.severity} | {f.id} | {pkg} | {where} | {f.fix or 'no fix'} | {extra or f.title} |"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--allowlist", type=Path, required=True)
    ap.add_argument(
        "--report",
        action="append",
        default=[],
        metavar="KIND:LABEL=PATH",
        help=f"KIND is one of {', '.join(PARSERS)}",
    )
    ap.add_argument("--today", type=dt.date.fromisoformat, default=dt.date.today())
    opts = ap.parse_args()

    try:
        entries = load_allowlist(opts.allowlist)
        findings: list[Finding] = []
        labels: list[tuple[str, str]] = []
        for spec in opts.report:
            m = re.fullmatch(r"([\w-]+):([^=]+)=(.+)", spec)
            if not m or m.group(1) not in PARSERS:
                raise ValueError(f"bad --report {spec!r}")
            kind, label, path = m.groups()
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            findings += PARSERS[kind](label, data)
            labels.append((kind, label))
    except (OSError, ValueError, KeyError, tomllib.TOMLDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    active = [e for e in entries if e.expires >= opts.today]
    expired = [e for e in entries if e.expires < opts.today]
    blocking, allowed, rest = [], [], []
    for f in findings:
        if not (f.fixable and f.blocking_severity):
            rest.append(f)
            continue
        entry = next((e for e in active if e.matches(f)), None)
        if entry:
            entry.used = True
            allowed.append((f, entry))
        else:
            blocking.append(f)

    lines = ["## Dependency and image security checks", ""]
    lines += ["| Scan | Findings by severity |", "| --- | --- |"]
    for kind, label in labels:
        mine = [f for f in findings if f.source == kind and f.label == label]
        lines.append(f"| {kind}: {label} | {counts(mine)} |")
    lines.append("")
    header = [
        "| Severity | ID | Package | Where | Fix | Note |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    if blocking:
        lines += [f"### Blocking: {len(blocking)} (high/critical with a fix)", "", *header]
        lines += [row(f) for f in sorted(blocking, key=lambda f: ORDER.index(f.severity))]
        lines.append("")
        lines.append(
            "Fix these, or add an entry with a reason and an expiry date to "
            "`.github/security/allowlist.toml`. UNKNOWN means OSV had no rating."
        )
        lines.append("")
    else:
        lines += ["### Blocking: none", ""]
    if allowed:
        lines += [f"### Allowlisted: {len(allowed)}", "", *header]
        lines += [row(f, f"until {e.expires}: {e.reason}") for f, e in allowed]
        lines.append("")
    for e in expired:
        lines.append(
            f"- warning: allowlist entry {e.id} expired on {e.expires}; it no longer applies"
        )
    for e in active:
        if not e.used:
            lines.append(
                f"- note: allowlist entry {e.id} matched nothing; remove it if it is fixed"
            )
    if expired or any(not e.used for e in active):
        lines.append("")
    if rest:
        lines += [
            f"### Reported, not blocking: {len(rest)}",
            "",
            "<details><summary>List</summary>",
            "",
        ]
        lines += header
        lines += [row(f) for f in sorted(rest, key=lambda f: ORDER.index(f.severity))]
        lines += ["", "</details>", ""]

    text = "\n".join(lines)
    print(text)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write(text + "\n")
    return 1 if blocking else 0


if __name__ == "__main__":
    sys.exit(main())
