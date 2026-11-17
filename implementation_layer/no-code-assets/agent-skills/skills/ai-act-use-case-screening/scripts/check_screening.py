#!/usr/bin/env python3
"""Check an AI Act use-case screening against the intake it was made from.

The screening folder holds ``intake.json`` (the user's description, documents and
answers), ``documents/`` and ``screening.json``. This script checks that every
finding has evidence, a citation and reasoning; that every quote occurs in the
description, recorded answer or document it names; that every citation is in the
reference's citable-provisions list; that the risk class, flags, actions and
timeline follow from the findings and dates; and that the intake has not changed
since the screening.

It does not check that a quote means what the screening says it means, and it
cannot confirm what the user said: the intake is recorded by the agent.

    python check_screening.py --dir <screening_folder>
    python check_screening.py --dir <screening_folder> --hash     # intake fingerprint to record
    python check_screening.py --dir <screening_folder> --status   # current | outdated | none

Exit code 0 when there are no errors (warnings allowed), 1 otherwise.
Standard library only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any

FINDING_IDS = ["F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8"]
STATUSES = {"yes", "no", "unknown", "not_applicable"}
RISK_CLASSES = {"unacceptable", "high", "limited", "minimal"}      # the AI Act's four risk tiers
OUTCOMES = {"classified", "undetermined", "not_in_scope"}
ROLES = {"provider", "deployer", "both", "unknown"}
CONFIDENCES = {"high", "medium", "low"}
SOURCES = {"description", "answer", "document"}
INSTRUMENTS = {"AI Act", "GDPR"}
ACTION_TYPES = {"required", "recommended"}
ROUTES = {"system", "organisation"}
ACTION_STATUSES = {"in_place", "partly", "missing", "unknown"}
STAGES = {"planned": {"idea", "development"}, "existing": {"pilot", "production"}}
TIMELINE_STATUSES = {"in_force", "upcoming"}

REFERENCE = Path(__file__).resolve().parents[1] / "references" / "ai-act-reference.md"
CITABLE_LINE = re.compile(r"^- (AI Act|GDPR): (.+?)\s*$")
QUESTION_ID = re.compile(r"^Q[1-9][0-9]*$")
# Internal names that must not reach the report for people (report-guide.md, rule 1)
REPORT_LEAKS = [
    (re.compile(r"`"), "backticks"),
    (re.compile(r"\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b"), "field name or value code"),
    (re.compile(r"\b[FQD][1-9][0-9]?\b"), "finding, question or document id"),
    (re.compile(r"\b[\w-]+\.json\b"), "data file name"),
]
URL = re.compile(r"https?://\S+")
QUOTED = re.compile(r'"[^"]*"|“[^”]*”|„[^“”]*[“”]|«[^»]*»')   # quotes keep the user's own words
DOCUMENT_ID = re.compile(r"^D[1-9][0-9]*$")


# --------------------------------------------------------------------------- helpers

def collapse(text: str) -> str:
    """Collapse runs of whitespace. Case and punctuation are kept."""
    return re.sub(r"\s+", " ", text).strip()


def load_reference(text: str) -> tuple[dict[str, set[str]], str | None]:
    """Citable provision ids per instrument, and the last_verified date."""
    citable: dict[str, set[str]] = {name: set() for name in INSTRUMENTS}
    section = text.split("## 14. Citable provisions", 1)
    if len(section) == 2:
        for line in section[1].splitlines():
            m = CITABLE_LINE.match(line)
            if m:
                citable[m.group(1)].add(collapse(m.group(2)))
    verified = re.search(r"last_verified:\s*(\d{4}-\d{2}-\d{2})", text)
    return citable, verified.group(1) if verified else None


def one_of(value: Any, allowed: set[str]) -> bool:
    """True when value is a string in ``allowed`` (never raises on unhashable values)."""
    return isinstance(value, str) and value in allowed


def iso_date(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


def inside(folder: Path, relative: str) -> Path | None:
    """The resolved path if it stays inside ``folder``, else None."""
    target = (folder / relative).resolve()
    return target if folder.resolve() in target.parents else None


def intake_hash(folder: Path) -> str:
    """SHA-256 over the intake's content and the text of every document it lists."""
    intake = json.loads((folder / "intake.json").read_text(encoding="utf-8"))
    digest = hashlib.sha256()
    digest.update(json.dumps(intake, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    for doc in intake.get("documents", []) if isinstance(intake, dict) else []:
        path = inside(folder, str(doc.get("file", ""))) if isinstance(doc, dict) else None
        if path and path.is_file():
            digest.update(b"\0" + str(doc.get("id")).encode("utf-8") + b"\0")
            digest.update(path.read_bytes())
    return digest.hexdigest()


def screening_status(folder: Path) -> str:
    """current | outdated | none."""
    path = folder / "screening.json"
    if not path.is_file():
        return "none"
    try:
        recorded = json.loads(path.read_text(encoding="utf-8"))["intake_sha256"]
        return "current" if recorded == intake_hash(folder) else "outdated"
    except (OSError, ValueError, KeyError, TypeError):
        return "outdated"


class Report:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def error(self, where: str, message: str) -> None:
        self.errors.append(f"{where}: {message}")

    def warn(self, where: str, message: str) -> None:
        self.warnings.append(f"{where}: {message}")


def text_field(obj: dict, key: str, where: str, rep: Report) -> str | None:
    value = obj.get(key)
    if not isinstance(value, str) or not value.strip():
        rep.error(where, f"'{key}' must be a non-empty string")
        return None
    return value


def objects(value: Any, where: str, rep: Report, required: bool = False) -> list[dict]:
    if value is None:
        if required:
            rep.error(where, "missing")
        return []
    if not isinstance(value, list):
        rep.error(where, "must be a list")
        return []
    items = []
    for i, item in enumerate(value, 1):
        if isinstance(item, dict):
            items.append(item)
        else:
            rep.error(f"{where} {i}", "must be an object")
    return items


# --------------------------------------------------------------------------- intake

class Intake:
    """The parts of intake.json that evidence is checked against."""

    def __init__(self) -> None:
        self.mode: str | None = None
        self.stage: str | None = None
        self.description = ""
        self.answers: dict[str, str] = {}
        self.documents: dict[str, str] = {}


def load_intake(folder: Path, rep: Report) -> Intake | None:
    try:
        data = json.loads((folder / "intake.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        rep.error("intake", f"cannot read intake.json: {exc}")
        return None
    if not isinstance(data, dict):
        rep.error("intake", "the top level must be a JSON object")
        return None
    intake = Intake()
    if data.get("intake_version") != "1.0":
        rep.error("intake.intake_version", "must be '1.0'")
    text_field(data, "use_case_name", "intake", rep)
    intake.mode = data.get("mode")
    intake.stage = data.get("lifecycle_stage")
    if intake.mode not in STAGES:
        rep.error("intake.mode", f"must be one of {sorted(STAGES)}")
    elif intake.stage not in STAGES[intake.mode]:
        rep.error("intake.lifecycle_stage", f"for mode '{intake.mode}' must be one of {sorted(STAGES[intake.mode])}")
    intake.description = text_field(data, "description", "intake", rep) or ""

    for i, q in enumerate(objects(data.get("questions"), "intake.questions", rep, required=True), 1):
        qid = q.get("id")
        if not isinstance(qid, str) or not QUESTION_ID.match(qid):
            rep.error(f"intake.questions {i}", "id must be Q1, Q2, …")
            continue
        if qid in intake.answers:
            rep.error(f"intake.questions {i}", f"duplicate id {qid}")
        text_field(q, "question", f"intake {qid}", rep)
        answer = q.get("answer")
        if not isinstance(answer, str) or not answer.strip():
            rep.error(f"intake {qid}", "'answer' must be a non-empty string ('unknown' if not answered)")
            answer = ""
        intake.answers[qid] = answer

    for i, d in enumerate(objects(data.get("documents"), "intake.documents", rep), 1):
        did = d.get("id")
        if not isinstance(did, str) or not DOCUMENT_ID.match(did):
            rep.error(f"intake.documents {i}", "id must be D1, D2, …")
            continue
        if did in intake.documents:
            rep.error(f"intake.documents {i}", f"duplicate id {did}")
        text_field(d, "original_name", f"intake {did}", rep)
        path = inside(folder, str(d.get("file", "")))
        if path is None:
            rep.error(f"intake {did}", "'file' must be a path inside the screening folder")
        elif not path.is_file():
            rep.error(f"intake {did}", f"'{d.get('file')}' not found")
        else:
            intake.documents[did] = path.read_text(encoding="utf-8", errors="replace")
    return intake


# --------------------------------------------------------------------------- citations and evidence

def check_citations(value: Any, where: str, rep: Report, citable: dict[str, set[str]],
                    allowed: set[str], need_ai_act: bool) -> list[str]:
    ai_act_refs = []
    for c in objects(value, f"{where} citation", rep):
        ref = c.get("ref")
        instrument = c.get("instrument", "AI Act")
        if not isinstance(ref, str) or not ref.strip():
            rep.error(where, "citation without 'ref'")
            continue
        if instrument not in INSTRUMENTS:
            rep.error(where, f"instrument {instrument!r} must be one of {sorted(INSTRUMENTS)}")
            continue
        if instrument not in allowed:
            rep.error(where, f"{instrument} citations belong in 'adjacent', not here")
            continue
        if collapse(ref) not in citable[instrument]:
            rep.error(where, f"{instrument} '{ref}' is not in the citable-provisions list of ai-act-reference.md")
            continue
        if instrument == "AI Act":
            ai_act_refs.append(collapse(ref))
    if need_ai_act and not ai_act_refs:
        rep.error(where, "needs at least one valid AI Act citation")
    return ai_act_refs


def check_evidence(value: Any, where: str, rep: Report, intake: Intake, required: bool) -> None:
    items = objects(value, f"{where} evidence", rep)
    if required and not items:
        rep.error(where, "no evidence")
    for i, ev in enumerate(items, 1):
        at = f"{where} evidence {i}"
        source, locator, quote = ev.get("source"), ev.get("locator"), ev.get("quote")
        if source not in SOURCES:
            rep.error(at, f"source must be one of {sorted(SOURCES)}")
            continue
        if not isinstance(locator, str) or not isinstance(quote, str):
            rep.error(at, "'locator' and 'quote' must be strings")
            continue
        if not collapse(quote):
            rep.error(at, "quote is empty")
            continue
        if source == "description":
            text = intake.description
        elif source == "answer":
            if locator not in intake.answers:
                rep.error(at, f"'{locator}' is not a question id in intake.json")
                continue
            text = intake.answers[locator]
        else:
            if locator not in intake.documents:
                rep.error(at, f"'{locator}' is not a document id in intake.json")
                continue
            text = intake.documents[locator]
        if collapse(quote) not in collapse(text):
            rep.error(at, f"quote is not in the {source} '{locator}' (case and punctuation must match)")


# --------------------------------------------------------------------------- classification

def expected_result(s: dict[str, str]) -> tuple[str, str | None]:
    """(outcome, risk tier) the findings imply. Mirrors SKILL.md Step 3."""
    if s["F1"] == "no":
        return "not_in_scope", None
    if s["F1"] == "unknown":
        return "undetermined", None
    if s["F3"] == "yes":
        return "classified", "unacceptable"
    if s["F3"] == "unknown":
        return "undetermined", None
    if s["F4"] == "yes" or (s["F5"] == "yes" and s["F6"] == "no"):
        return "classified", "high"
    if s["F4"] == "unknown" or s["F5"] == "unknown" or (s["F5"] == "yes" and s["F6"] == "unknown"):
        return "undetermined", None
    if s["F7"] == "yes":
        return "classified", "limited"
    if s["F7"] == "unknown":
        return "undetermined", None
    return "classified", "minimal"


def not_applicable_allowed(fid: str, s: dict[str, str]) -> bool:
    if fid != "F1" and s.get("F1") == "no":
        return True
    return fid == "F6" and s.get("F5") != "yes"


# --------------------------------------------------------------------------- main check

def check(folder: Path) -> Report:
    rep = Report()
    intake = load_intake(folder, rep)
    if intake is None:
        return rep
    try:
        data = json.loads((folder / "screening.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        rep.error("screening", f"cannot read screening.json: {exc}")
        return rep
    try:
        citable, verified = load_reference(REFERENCE.read_text(encoding="utf-8"))
    except OSError as exc:
        rep.error("reference", f"cannot read {REFERENCE}: {exc}")
        return rep
    if not citable["AI Act"]:
        rep.error("reference", "ai-act-reference.md has no citable-provisions list")
        return rep
    if not isinstance(data, dict):
        rep.error("screening", "the top level must be a JSON object")
        return rep

    # Header
    if data.get("screening_version") != "1.0":
        rep.error("screening_version", "must be '1.0'")
    if verified and data.get("reference_last_verified") != verified:
        rep.error("reference_last_verified", f"must be {verified}, the date in ai-act-reference.md")
    if verified and (date.today() - date.fromisoformat(verified)).days > 183:
        rep.warn("reference", "ai-act-reference.md was verified more than six months ago")
    screened_on = iso_date(data.get("screened_on"))
    if screened_on is None:
        rep.error("screened_on", "must be an ISO date (YYYY-MM-DD)")
    if not isinstance(data.get("disclaimer"), str) or not data["disclaimer"].strip():
        rep.error("disclaimer", "missing")
    recorded = data.get("intake_sha256")
    current = intake_hash(folder)
    if not isinstance(recorded, str) or not recorded:
        rep.error("intake_sha256", "missing; get it with --hash")
    elif recorded != current:
        rep.error("intake_sha256", "OUTDATED: the intake changed after this screening; rerun it "
                                   f"(current fingerprint {current})")

    # Summary
    summary = data.get("summary")
    if not isinstance(summary, dict):
        rep.error("summary", "must be an object")
        summary = {}
    if not one_of(summary.get("outcome"), OUTCOMES):
        rep.error("summary.outcome", f"must be one of {sorted(OUTCOMES)}")
    tier = summary.get("risk_class")
    if summary.get("outcome") == "classified":
        if not one_of(tier, RISK_CLASSES):
            rep.error("summary.risk_class", f"must be one of the four tiers {sorted(RISK_CLASSES)}")
    elif tier is not None:
        rep.error("summary.risk_class", "must be null when no tier is assigned")
    if summary.get("role") not in ROLES:
        rep.error("summary.role", f"must be one of {sorted(ROLES)}")
    if summary.get("confidence") not in CONFIDENCES:
        rep.error("summary.confidence", f"must be one of {sorted(CONFIDENCES)}")
    if summary.get("mode") != intake.mode:
        rep.error("summary.mode", f"must match intake.json ('{intake.mode}')")
    if summary.get("lifecycle_stage") != intake.stage:
        rep.error("summary.lifecycle_stage", f"must match intake.json ('{intake.stage}')")
    text_field(summary, "screened_use", "summary", rep)
    flags = summary.get("flags")
    if not isinstance(flags, dict) or not all(
        isinstance(flags.get(k), bool) for k in ("art_6_3_exempt", "transparency_duties")
    ):
        rep.error("summary.flags", "must hold booleans 'art_6_3_exempt' and 'transparency_duties'")
        flags = None

    # Findings
    findings = objects(data.get("findings"), "findings", rep, required=True)
    ids = [f.get("id") for f in findings]
    findings_ok = ids == FINDING_IDS and len(findings) == len(data.get("findings") or [])
    if not findings_ok:
        rep.error("findings", f"must be exactly {FINDING_IDS} in order, got {ids}")
    status: dict[str, str] = {}
    for f in findings:
        fid = str(f.get("id"))
        st = f.get("status")
        if st not in STATUSES:
            rep.error(fid, f"status must be one of {sorted(STATUSES)}")
            findings_ok = False
        status[fid] = st if isinstance(st, str) else ""
        if f.get("confidence") not in CONFIDENCES:
            rep.error(fid, f"confidence must be one of {sorted(CONFIDENCES)}")
        for key in ("question", "answer", "reasoning"):
            text_field(f, key, fid, rep)
        check_evidence(f.get("evidence"), fid, rep, intake, required=True)
        check_citations(f.get("citations"), fid, rep, citable, {"AI Act"}, need_ai_act=True)

    if findings_ok:
        for fid in FINDING_IDS:
            if status[fid] == "not_applicable" and not not_applicable_allowed(fid, status):
                rep.error(fid, "'not_applicable' is allowed only for F6 when F5 is not 'yes', "
                               "or for F2–F8 when F1 is 'no'")
        if status["F5"] == "yes" and status["F6"] == "not_applicable":
            rep.error("F6", "must be answered when F5 is 'yes'")
        outcome, implied = expected_result(status)
        if summary.get("outcome") != outcome:
            rep.error("summary.outcome", f"findings imply '{outcome}', screening says '{summary.get('outcome')}'")
        elif summary.get("risk_class") != implied:
            rep.error("summary.risk_class", f"findings imply '{implied}', screening says '{summary.get('risk_class')}'")
        if outcome == "undetermined":
            alternatives = objects(summary.get("alternatives"), "summary.alternatives", rep)
            if len(alternatives) < 2:
                rep.error("summary.alternatives", "list at least two outcomes when the class is 'undetermined'")
            for i, alt in enumerate(alternatives, 1):
                text_field(alt, "if", f"summary.alternatives {i}", rep)
                if not one_of(alt.get("risk_class"), RISK_CLASSES):
                    rep.error(f"summary.alternatives {i}", f"'risk_class' must be one of {sorted(RISK_CLASSES)}")
            if summary.get("confidence") == "high":
                rep.error("summary.confidence", "cannot be 'high' when the class is 'undetermined'")
        if status["F2"] == "unknown" and summary.get("role") != "unknown":
            rep.error("summary.role", "F2 is 'unknown', so the role must be 'unknown'")
        if flags is not None:
            if flags["art_6_3_exempt"] != (status["F5"] == "yes" and status["F6"] == "yes"):
                rep.error("summary.flags.art_6_3_exempt", "must be true exactly when F5 and F6 are 'yes'")
            if flags["transparency_duties"] != (status["F7"] == "yes"):
                rep.error("summary.flags.transparency_duties", "must be true exactly when F7 is 'yes'")

    # Actions
    cited_in_required: list[str] = []
    required_count = 0
    for i, ac in enumerate(objects(data.get("actions"), "actions", rep, required=True), 1):
        at = f"action {i}"
        kind = ac.get("type")
        if kind not in ACTION_TYPES:
            rep.error(at, f"type must be one of {sorted(ACTION_TYPES)}")
            continue
        text_field(ac, "action", at, rep)
        if ac.get("route") not in ROUTES:
            rep.error(at, f"route must be one of {sorted(ROUTES)}")
        based_on = ac.get("based_on")
        if not isinstance(based_on, list) or not based_on or any(b not in FINDING_IDS for b in based_on):
            rep.error(at, "based_on must be a non-empty list of finding ids F1–F8")
        if kind == "required":
            required_count += 1
            if ac.get("applies_to") not in {"provider", "deployer", "both"}:
                rep.error(at, "applies_to must be provider, deployer or both")
            if iso_date(ac.get("applies_from")) is None:
                rep.error(at, "applies_from must be an ISO date (YYYY-MM-DD)")
            cited_in_required += check_citations(ac.get("citations"), at, rep, citable, {"AI Act"}, need_ai_act=True)
            if intake.mode == "existing":
                st = ac.get("status")
                if st not in ACTION_STATUSES:
                    rep.error(at, f"an existing system's required action needs a status: {sorted(ACTION_STATUSES)}")
                elif st != "unknown":
                    if not ac.get("status_evidence"):
                        rep.error(at, f"status '{st}' needs status_evidence")
                    check_evidence(ac.get("status_evidence"), f"{at} status", rep, intake, required=False)
            elif "status" in ac:
                rep.error(at, "a planned system's required action has no status")
        else:
            text_field(ac, "reason", at, rep)
            for key in ("applies_to", "applies_from", "status"):
                if key in ac:
                    rep.error(at, f"a recommendation is not a legal duty: remove '{key}'")
            check_citations(ac.get("citations"), at, rep, citable, {"AI Act"}, need_ai_act=False)

    risk_class = summary.get("risk_class") if one_of(summary.get("risk_class"), RISK_CLASSES) else None
    no_duties = risk_class == "unacceptable" or summary.get("outcome") == "not_in_scope"
    if risk_class == "unacceptable" and required_count:
        rep.error("actions", "no required actions for the unacceptable tier; say what must change instead")
    if flags is not None and not no_duties:
        if flags["art_6_3_exempt"] and not ({"Art. 6(4)", "Art. 49(2)"} & set(cited_in_required)):
            rep.error("actions", "an Art. 6(3)-exempt system keeps its assessment and registration "
                                 "duties: add a required action citing Art. 6(4) or Art. 49(2)")
        if flags["transparency_duties"] and not any(r.startswith("Art. 50") for r in cited_in_required):
            rep.error("actions", "F7 is 'yes': add the applicable Art. 50 duty as a required action, "
                                 "whatever the class")

    # Timeline
    timeline = objects(data.get("timeline"), "timeline", rep, required=True)
    for i, item in enumerate(timeline, 1):
        at = f"timeline {i}"
        when = iso_date(item.get("date"))
        text_field(item, "what", at, rep)
        if when is None:
            rep.error(at, "date must be an ISO date (YYYY-MM-DD)")
        elif item.get("status") not in TIMELINE_STATUSES:
            rep.error(at, f"status must be one of {sorted(TIMELINE_STATUSES)}")
        elif screened_on is not None:
            expected = "in_force" if when <= screened_on else "upcoming"
            if item["status"] != expected:
                rep.error(at, f"{when} is '{expected}' on the screening date {screened_on}")
        check_citations(item.get("citations"), at, rep, citable, {"AI Act"}, need_ai_act=True)
    if not timeline and not no_duties:
        rep.warn("timeline", "empty; list the dates that affect this use case")

    # Triggers, open questions, adjacent
    for i, tr in enumerate(objects(data.get("triggers"), "triggers", rep), 1):
        at = f"trigger {i}"
        text_field(tr, "change", at, rep)
        if not one_of(tr.get("would_become"), RISK_CLASSES):
            rep.error(at, f"would_become must be one of {sorted(RISK_CLASSES)}")
        check_citations(tr.get("citations"), at, rep, citable, {"AI Act"}, need_ai_act=True)
    if risk_class in {"minimal", "limited"} and not data.get("triggers"):
        rep.warn("triggers", "none listed; say what would raise the class")
    oq = data.get("open_questions", [])
    if not isinstance(oq, list) or not all(isinstance(x, str) and x.strip() for x in oq):
        rep.error("open_questions", "must be a list of non-empty strings")
    for i, adj in enumerate(objects(data.get("adjacent"), "adjacent", rep), 1):
        at = f"adjacent {i}"
        text_field(adj, "flag", at, rep)
        check_citations(adj.get("citations"), at, rep, citable, INSTRUMENTS, need_ai_act=False)
        check_evidence(adj.get("evidence"), at, rep, intake, required=False)

    check_report(folder, rep)
    return rep


def check_report(folder: Path, rep: Report) -> None:
    """The report must not contain internal names from the data (report-guide.md, rule 1)."""
    path = folder / "report.md"
    if not path.is_file():
        rep.warn("report", "report.md has not been written yet")
        return
    for number, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        text = QUOTED.sub("", URL.sub("", line))
        for pattern, what in REPORT_LEAKS:
            found = pattern.findall(text)
            if found:
                shown = ", ".join(sorted(set(found))[:3])
                rep.error(f"report.md line {number}", f"{what} for readers: {shown}; use plain words "
                                                        "(report-guide.md)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--dir", required=True, type=Path, help="the screening folder")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--hash", action="store_true", help="print the intake fingerprint and exit")
    mode.add_argument("--status", action="store_true", help="print current | outdated | none and exit")
    args = parser.parse_args()

    if args.status:
        print(screening_status(args.dir))
        return 0
    if args.hash:
        try:
            print(intake_hash(args.dir))
        except (OSError, ValueError) as exc:
            print(f"ERROR    cannot read intake.json: {exc}")
            return 1
        return 0

    rep = check(args.dir)
    for line in rep.warnings:
        print(f"WARNING  {line}")
    for line in rep.errors:
        print(f"ERROR    {line}")
    if rep.errors:
        print(f"\nFAILED: {len(rep.errors)} error(s), {len(rep.warnings)} warning(s)")
        return 1
    print(f"PASSED with {len(rep.warnings)} warning(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
