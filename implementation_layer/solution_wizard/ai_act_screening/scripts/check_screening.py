#!/usr/bin/env python3
"""Check an AI Act screening against the solution pack it describes.

The agent writes ``ai_act_screening.json``; this script checks that every
finding has evidence, a citation and reasoning; that blueprint values,
document passages, conversation quotes and screening answers really occur in
their sources; that every citation is in the reference's citable-provisions
list; and that the risk class and flags follow from the findings.

It does not check that a quote means what the screening says it means.

Errors are for a screening that is malformed, contradicts itself or its sources, or cites
something that does not exist. Everything else (a missing duty, an outdated screening, a
date not in the reference) is a warning: advice for the agent and the user, never a stop.

    python check_screening.py --pack <wizard_output_dir>
    python check_screening.py --pack <dir> --transcript conversation.md
    python check_screening.py --pack <dir> --hash     # blueprint fingerprint to record
    python check_screening.py --pack <dir> --status   # current | outdated | unverified | none

Exit code 0 when there are no errors (warnings allowed), 1 otherwise.
Standard library only.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any

FINDING_IDS = ["F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8"]
STATUSES = {"yes", "no", "unknown", "not_applicable"}
# The four risk levels of the AI Act. "not_decided" is not a level: it says that a fact that
# decides the level is unknown, and the screening then lists the possible levels.
DECIDED_CLASSES = {"unacceptable", "high", "limited", "minimal"}
RISK_CLASSES = DECIDED_CLASSES | {"not_decided"}
ROLES = {"provider", "deployer", "both", "unknown"}
CONFIDENCES = {"high", "medium", "low"}
SOURCES = {"blueprint", "document", "conversation", "screening_answer", "absent"}
INSTRUMENTS = {"AI Act", "GDPR"}
ACTION_TYPES = {"required", "recommended"}
ROUTES = {"wizard", "organisation"}
OUTPUT_FILES = {"ai_act_screening.json", "docs/ai_act_screening.md"}
MISSING = object()

GLOSSARY_FILE = Path(__file__).resolve().parents[1] / "references" / "glossary.json"
GLOSSARY_KEYS = (
    set(json.loads(GLOSSARY_FILE.read_text(encoding="utf-8"))) if GLOSSARY_FILE.is_file() else set()
)
REFERENCE = Path(__file__).resolve().parents[1] / "references" / "ai-act-reference.md"
CITABLE_LINE = re.compile(r"^- (AI Act|GDPR): (.+?)\s*$")
INDEX = re.compile(r"^(0|[1-9][0-9]*)$")
MONTHS = {
    m: i
    for i, m in enumerate(
        [
            "January",
            "February",
            "March",
            "April",
            "May",
            "June",
            "July",
            "August",
            "September",
            "October",
            "November",
            "December",
        ],
        1,
    )
}
DATE_ROW = re.compile(r"^\|\s*(\d{1,2}) ([A-Z][a-z]+) (\d{4})\s*\|")

# Parts of the blueprint that change without changing what the solution is or does. They are
# left out of the fingerprint, so a timestamp, a change-log entry or the screening's own saved
# answers do not make a screening outdated.
FINGERPRINT_LEAVES_OUT = (
    ("metadata", "last_updated_at"),
    ("change_log",),
    ("business_spec", "ai_act_context"),
)

# Duties of a high-risk system by role, for the advice that a high-risk result lists some.
DEPLOYER_DUTIES = {
    "Art. 26(1)",
    "Art. 26(2)",
    "Art. 26(4)",
    "Art. 26(5)",
    "Art. 26(6)",
    "Art. 26(7)",
    "Art. 26(11)",
    "Art. 27",
    "Art. 86",
}
PROVIDER_DUTIES = {
    "Art. 9",
    "Art. 10",
    "Art. 11",
    "Art. 12",
    "Art. 13",
    "Art. 14",
    "Art. 15",
    "Art. 16",
    "Art. 17",
    "Art. 43",
    "Art. 47",
    "Art. 48",
    "Art. 49",
    "Art. 72",
    "Art. 73",
}


# --------------------------------------------------------------------------- helpers


def collapse(text: str) -> str:
    """Collapse runs of whitespace. Case and punctuation are kept."""
    return re.sub(r"\s+", " ", text).strip()


def words_of(text: str) -> list[str]:
    """The words of a text, lowercase, without punctuation."""
    return re.findall(r"\w+", text.casefold())


def has_words_in_order(source: str, quote: str) -> bool:
    """Whether the quote's words occur in the source in order, ignoring case and punctuation."""
    wanted = words_of(quote)
    if not wanted:
        return False
    return " " + " ".join(wanted) + " " in " " + " ".join(words_of(source)) + " "


def blueprint_hash(blueprint: Any) -> str:
    """SHA-256 of what the blueprint says, independent of key order and formatting.

    Leaves out the parts in FINGERPRINT_LEAVES_OUT, which change without changing the solution.
    """
    view = copy.deepcopy(blueprint)
    for path in FINGERPRINT_LEAVES_OUT:
        node = view
        for key in path[:-1]:
            node = node.get(key) if isinstance(node, dict) else None
        if isinstance(node, dict):
            node.pop(path[-1], None)
    canonical = json.dumps(view, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def screening_status(pack: Path) -> str:
    """current | outdated | unverified | none, for the screening saved in the pack."""
    path = pack / "ai_act_screening.json"
    if not path.is_file():
        return "none"
    try:
        blueprint = json.loads((pack / "use_case.blueprint.json").read_text(encoding="utf-8"))
        data = json.loads(path.read_text(encoding="utf-8"))
        recorded = data["pack"]["blueprint_sha256"]
    except (OSError, ValueError, KeyError, TypeError):
        return "unverified"
    if not isinstance(recorded, str) or not recorded:
        return "unverified"
    return "current" if recorded == blueprint_hash(blueprint) else "outdated"


def parse_pointer(pointer: str) -> list[str]:
    """Split an RFC 6901 JSON Pointer into reference tokens; raise ValueError if malformed."""
    if pointer == "":
        return []
    if not pointer.startswith("/"):
        raise ValueError("must be empty or start with '/'")
    tokens = []
    for raw in pointer[1:].split("/"):
        if re.search(r"~(?![01])", raw):
            raise ValueError(f"invalid escape in {raw!r}")
        tokens.append(raw.replace("~1", "/").replace("~0", "~"))
    return tokens


def resolve(doc: Any, pointer: str) -> Any:
    """Value at ``pointer`` in ``doc``, or MISSING. Raises ValueError for a malformed pointer."""
    node = doc
    for token in parse_pointer(pointer):
        if isinstance(node, dict):
            if token not in node:
                return MISSING
            node = node[token]
        elif isinstance(node, list):
            if not INDEX.match(token):
                raise ValueError(
                    f"array index {token!r} is not a non-negative integer without leading zeros"
                )
            if int(token) >= len(node):
                return MISSING
            node = node[int(token)]
        else:
            return MISSING
    return node


def scalar_text(value: Any) -> str:
    """How a JSON scalar is quoted: strings as themselves, others in JSON form (true, 0.0, null)."""
    return value if isinstance(value, str) else json.dumps(value)


def is_scalar(value: Any) -> bool:
    return value is None or isinstance(value, (str, bool, int, float))


def is_empty(value: Any) -> bool:
    return value is MISSING or value is None or value == "" or value == [] or value == {}


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


def load_application_dates(text: str) -> set[str]:
    """The ISO dates in the reference's table of application dates."""
    dates: set[str] = set()
    section = text.split("## 10. Application dates", 1)
    if len(section) == 2:
        for line in section[1].split("\n## ", 1)[0].splitlines():
            m = DATE_ROW.match(line)
            if m and m.group(2) in MONTHS:
                dates.add(f"{int(m.group(3)):04d}-{MONTHS[m.group(2)]:02d}-{int(m.group(1)):02d}")
    return dates


def match_quote(quote: str, source: str, at: str, where: str, rep: Report) -> None:
    """A quote is found as written, or by its words in order (a warning); otherwise an error."""
    if collapse(quote) in collapse(source):
        return
    if has_words_in_order(source, quote):
        rep.warn(at, f"quote differs from {where} in case or punctuation; copy it as written")
    else:
        rep.error(at, f"quote is not in {where}")


class Report:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def error(self, where: str, message: str) -> None:
        self.errors.append(f"{where}: {message}")

    def warn(self, where: str, message: str) -> None:
        self.warnings.append(f"{where}: {message}")


def text_field(obj: dict, key: str, where: str, rep: Report) -> str | None:
    """A required non-empty string field; reports and returns None otherwise."""
    value = obj.get(key)
    if not isinstance(value, str) or not value.strip():
        rep.error(where, f"'{key}' must be a non-empty string")
        return None
    return value


def objects(value: Any, where: str, rep: Report, required: bool = False) -> list[dict]:
    """The dict items of a list field; reports a non-list and non-dict items."""
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


# --------------------------------------------------------------------------- citations


def check_citations(
    value: Any,
    where: str,
    rep: Report,
    citable: dict[str, set[str]],
    allowed: set[str],
    need_ai_act: bool,
) -> list[str]:
    """Validate citations; return the AI Act refs found."""
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
            rep.error(
                where,
                f"{instrument} '{ref}' is not in the citable list of ai-act-reference.md",
            )
            continue
        if instrument == "AI Act":
            ai_act_refs.append(collapse(ref))
    if need_ai_act and not ai_act_refs:
        rep.error(where, "needs at least one valid AI Act citation")
    return ai_act_refs


# --------------------------------------------------------------------------- evidence


def check_evidence(
    value: Any,
    where: str,
    rep: Report,
    pack: Path,
    blueprint: Any,
    transcript: str | None,
    answers: dict[str, str],
    required: bool,
) -> set[str]:
    """Validate evidence items; return the set of sources used."""
    items = objects(value, f"{where} evidence", rep)
    if required and not items:
        rep.error(where, "no evidence")
    used: set[str] = set()
    for i, ev in enumerate(items, 1):
        at = f"{where} evidence {i}"
        source, locator, quote = ev.get("source"), ev.get("locator"), ev.get("quote")
        if source not in SOURCES:
            rep.error(at, f"source must be one of {sorted(SOURCES)}")
            continue
        if not isinstance(locator, str) or (source != "blueprint" and not locator.strip()):
            rep.error(at, "'locator' must be a string")
            continue
        if not isinstance(quote, str):
            rep.error(at, "'quote' must be a string")
            continue
        used.add(source)

        if source == "absent":
            if quote != "":
                rep.error(at, "an 'absent' item must have an empty quote")
            for pointer in (p.strip() for p in locator.split(",")):
                try:
                    found = resolve(blueprint, pointer)
                except ValueError as exc:
                    rep.error(at, f"pointer {pointer!r}: {exc}")
                    continue
                if not pointer:
                    rep.error(at, "an 'absent' locator cannot be the whole blueprint")
                elif not is_empty(found):
                    rep.error(at, f"marked absent, but '{pointer}' has a value in the blueprint")
            continue

        if not collapse(quote):
            rep.error(at, "quote is empty")
            continue

        if source == "blueprint":
            try:
                found = resolve(blueprint, locator)
            except ValueError as exc:
                rep.error(at, f"pointer {locator!r}: {exc}")
                continue
            if found is MISSING:
                rep.error(at, f"'{locator}' does not exist in the blueprint")
            elif isinstance(found, dict):
                rep.error(at, f"'{locator}' is an object; point to one of its fields")
            elif isinstance(found, list):
                if not all(is_scalar(x) for x in found):
                    rep.error(at, f"'{locator}' holds objects; point to one element")
                elif quote not in [scalar_text(x) for x in found]:
                    rep.error(at, f"quote is not an element of the list at '{locator}'")
            elif quote != scalar_text(found):
                rep.error(
                    at,
                    f"quote does not equal the value at '{locator}' ({scalar_text(found)[:80]!r})",
                )

        elif source == "document":
            if collapse(locator) in OUTPUT_FILES:
                rep.error(at, "the screening's own output cannot be evidence")
                continue
            target = (pack / locator).resolve()
            if pack.resolve() not in target.parents:
                rep.error(at, f"'{locator}' is outside the pack")
            elif not target.is_file():
                rep.error(at, f"'{locator}' not found in the pack")
            else:
                match_quote(
                    quote,
                    target.read_text(encoding="utf-8", errors="replace"),
                    at,
                    f"'{locator}'",
                    rep,
                )

        elif source == "conversation":
            if transcript is None:
                rep.warn(at, "conversation quote not verified (no --transcript given)")
            else:
                match_quote(quote, transcript, at, "the transcript", rep)

        elif source == "screening_answer":
            if locator not in answers:
                rep.error(at, f"'{locator}' is not a question id in 'questions'")
            else:
                match_quote(quote, answers[locator], at, f"the recorded answer to {locator}", rep)
    return used


# --------------------------------------------------------------------------- classification


def expected_class(s: dict[str, str]) -> str:
    """The risk level the findings imply. Mirrors SKILL.md Step 3.

    A system the Act does not cover (F1 no) is "minimal": Minimal or no risk.
    """
    if s["F1"] == "no":
        return "minimal"
    if s["F1"] == "unknown":
        return "not_decided"
    if s["F3"] == "yes":
        return "unacceptable"
    if s["F3"] == "unknown":
        return "not_decided"
    if s["F4"] == "yes" or (s["F5"] == "yes" and s["F6"] == "no"):
        return "high"
    if s["F4"] == "unknown" or s["F5"] == "unknown" or (s["F5"] == "yes" and s["F6"] == "unknown"):
        return "not_decided"
    if s["F7"] == "yes":
        return "limited"
    if s["F7"] == "unknown":
        return "not_decided"
    return "minimal"


def not_applicable_allowed(fid: str, s: dict[str, str]) -> bool:
    """`not_applicable` only where a finding depends on another: F6 on F5, and F2–F8 on F1."""
    if fid != "F1" and s.get("F1") == "no":
        return True
    return fid == "F6" and s.get("F5") != "yes"


# --------------------------------------------------------------------------- main check


def check(pack: Path, screening_path: Path, transcript: str | None) -> Report:
    rep = Report()
    try:
        blueprint = json.loads((pack / "use_case.blueprint.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        rep.error("pack", f"cannot read use_case.blueprint.json: {exc}")
        return rep
    try:
        data = json.loads(screening_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        rep.error("screening", f"cannot read {screening_path.name}: {exc}")
        return rep
    try:
        reference_text = REFERENCE.read_text(encoding="utf-8")
        citable, verified = load_reference(reference_text)
        dates = load_application_dates(reference_text)
    except OSError as exc:
        rep.error("reference", f"cannot read {REFERENCE}: {exc}")
        return rep
    if not citable["AI Act"]:
        rep.error("reference", "ai-act-reference.md has no citable-provisions list")
        return rep
    if not isinstance(data, dict):
        rep.error("screening", "the top level must be a JSON object")
        return rep

    # Version and reference date
    if data.get("screening_version") != "1.0":
        rep.error("screening_version", "must be '1.0'")
    if verified and data.get("reference_last_verified") != verified:
        rep.warn(
            "reference_last_verified", f"differs from {verified}, the date in ai-act-reference.md"
        )
    if verified and (date.today() - date.fromisoformat(verified)).days > 183:
        rep.warn("reference", "ai-act-reference.md was verified more than six months ago")
    if not isinstance(data.get("disclaimer"), str) or not data["disclaimer"].strip():
        rep.error("disclaimer", "missing")

    # Which blueprint this screening describes
    pack_info = data.get("pack")
    if not isinstance(pack_info, dict):
        rep.error("pack", "must be an object")
        pack_info = {}
    recorded = pack_info.get("blueprint_sha256")
    current = blueprint_hash(blueprint)
    if recorded == "":
        rep.warn(
            "pack.blueprint_sha256", "empty: outdated screenings cannot be detected (manual check)"
        )
    elif not isinstance(recorded, str):
        rep.warn(
            "pack.blueprint_sha256",
            "missing: outdated screenings cannot be detected; get it with --hash",
        )
    elif recorded != current:
        rep.warn(
            "pack.blueprint_sha256",
            "OUTDATED: the blueprint changed after this screening; rerun it "
            f"if you want it to match (current fingerprint {current})",
        )

    # Recorded questions and answers
    answers: dict[str, str] = {}
    for i, q in enumerate(objects(data.get("questions"), "questions", rep, required=True), 1):
        qid = q.get("id")
        if not isinstance(qid, str) or not qid.strip():
            rep.error(f"questions {i}", "'id' must be a non-empty string")
            continue
        if qid in answers:
            rep.error(f"questions {i}", f"duplicate id {qid!r}")
        text_field(q, "question", f"questions {qid}", rep)
        answer = q.get("answer")
        if not isinstance(answer, str):
            rep.error(
                f"questions {qid}", "'answer' must be a string (use \"unknown\" if not answered)"
            )
            answer = ""
        answers[qid] = answer

    # Summary
    summary = data.get("summary")
    if not isinstance(summary, dict):
        rep.error("summary", "must be an object")
        summary = {}
    if summary.get("risk_class") not in RISK_CLASSES:
        rep.error("summary.risk_class", f"must be one of {sorted(RISK_CLASSES)}")
    if summary.get("role") not in ROLES:
        rep.error("summary.role", f"must be one of {sorted(ROLES)}")
    if summary.get("confidence") not in CONFIDENCES:
        rep.error("summary.confidence", f"must be one of {sorted(CONFIDENCES)}")
    if (
        not isinstance(summary.get("intended_deployment"), str)
        or not summary["intended_deployment"].strip()
    ):
        rep.error("summary.intended_deployment", "say which production use was screened")
    flags = summary.get("flags")
    if not isinstance(flags, dict) or not all(
        isinstance(flags.get(k), bool) for k in ("art_6_3_exempt", "transparency_duties")
    ):
        rep.error("summary.flags", "must hold booleans 'art_6_3_exempt' and 'transparency_duties'")
        flags = None

    # What a reader needs to understand the result without the skill at hand
    for key, what in (
        ("interpretation", "a short summary of the overall result"),
        ("confidence_reason", "why the confidence is what it is"),
    ):
        if not isinstance(summary.get(key), str) or not summary[key].strip():
            rep.warn(f"summary.{key}", f"missing: write {what}; the brief shows it")
    glossary = data.get("glossary")
    if not isinstance(glossary, dict) or not GLOSSARY_KEYS <= set(glossary):
        rep.warn("glossary", "missing or incomplete: run render_brief.py, which adds it")

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
        needed = st != "not_applicable"  # a finding that does not apply needs only its reasoning
        used = check_evidence(
            f.get("evidence"), fid, rep, pack, blueprint, transcript, answers, required=needed
        )
        check_citations(f.get("citations"), fid, rep, citable, {"AI Act"}, need_ai_act=needed)
        if f.get("confidence") == "high" and used == {"absent"}:
            rep.warn(fid, "confidence 'high' rests on absent evidence only; 'medium' fits better")

    # Class and flags follow from findings
    if findings_ok:
        for fid in FINDING_IDS:
            if status[fid] == "not_applicable" and not not_applicable_allowed(fid, status):
                rep.error(
                    fid,
                    "'not_applicable' is allowed only for F6 when F5 is not 'yes', "
                    "or for F2–F8 when F1 is 'no'",
                )
        if status["F5"] == "yes" and status["F6"] == "not_applicable":
            rep.error("F6", "must be answered when F5 is 'yes'")

        implied = expected_class(status)
        actual = summary.get("risk_class")
        if actual != implied:
            rep.error(
                "summary.risk_class", f"findings imply '{implied}', screening says '{actual}'"
            )
        if implied == "not_decided":
            alternatives = objects(summary.get("alternatives"), "summary.alternatives", rep)
            if len(alternatives) < 2:
                rep.warn(
                    "summary.alternatives",
                    "list at least two possible levels when the result is 'not_decided'",
                )
            for i, alt in enumerate(alternatives, 1):
                text_field(alt, "if", f"summary.alternatives {i}", rep)
                if alt.get("risk_class") not in DECIDED_CLASSES:
                    rep.error(
                        f"summary.alternatives {i}", "'risk_class' must be one of the four levels"
                    )
            if summary.get("confidence") == "high":
                rep.warn("summary.confidence", "'high' does not fit a 'not_decided' result")
        if status["F2"] == "unknown" and summary.get("role") != "unknown":
            rep.error("summary.role", "F2 is 'unknown', so the role must be 'unknown'")
        if flags is not None:
            if flags["art_6_3_exempt"] != (status["F5"] == "yes" and status["F6"] == "yes"):
                rep.error(
                    "summary.flags.art_6_3_exempt", "must be true exactly when F5 and F6 are 'yes'"
                )
            if flags["transparency_duties"] != (status["F7"] == "yes"):
                rep.error(
                    "summary.flags.transparency_duties", "must be true exactly when F7 is 'yes'"
                )

    # Actions
    cited_in_required: list[str] = []
    actions = objects(data.get("actions"), "actions", rep, required=True)
    required_count = 0
    for i, ac in enumerate(actions, 1):
        at = f"action {i}"
        kind = ac.get("type")
        if kind not in ACTION_TYPES:
            rep.error(at, f"type must be one of {sorted(ACTION_TYPES)}")
            continue
        text_field(ac, "action", at, rep)
        if ac.get("route") not in ROUTES:
            rep.error(at, f"route must be one of {sorted(ROUTES)}")
        based_on = ac.get("based_on")
        if (
            not isinstance(based_on, list)
            or not based_on
            or any(b not in FINDING_IDS for b in based_on)
        ):
            rep.error(at, "based_on must be a non-empty list of finding ids F1–F8")
        if kind == "required":
            required_count += 1
            if ac.get("applies_to") not in {"provider", "deployer", "both"}:
                rep.error(at, "applies_to must be provider, deployer or both")
            try:
                date.fromisoformat(str(ac.get("applies_from")))
            except ValueError:
                rep.error(at, "applies_from must be an ISO date (YYYY-MM-DD)")
            else:
                if dates and str(ac.get("applies_from")) not in dates:
                    rep.warn(
                        at,
                        f"applies_from {ac.get('applies_from')} is not a date in the reference's "
                        "table of application dates",
                    )
            cited_in_required += check_citations(
                ac.get("citations"), at, rep, citable, {"AI Act"}, need_ai_act=True
            )
        else:
            text_field(ac, "reason", at, rep)
            for key in ("applies_to", "applies_from"):
                if key in ac:
                    rep.warn(at, f"a recommendation is not a legal duty: remove '{key}'")
            check_citations(ac.get("citations"), at, rep, citable, {"AI Act"}, need_ai_act=False)

    risk_class = summary.get("risk_class")
    if risk_class == "unacceptable" and required_count:
        rep.warn(
            "actions",
            "an unacceptable-risk practice has no required actions; say what must change instead",
        )
    required_refs = set(cited_in_required)
    if flags is not None and risk_class != "unacceptable":
        if flags["art_6_3_exempt"] and not ({"Art. 6(4)", "Art. 49(2)"} & required_refs):
            rep.warn(
                "actions",
                "an Art. 6(3)-exempt system keeps its assessment and registration "
                "duties: consider a required action citing Art. 6(4) or Art. 49(2)",
            )
        if flags["transparency_duties"] and not any(r.startswith("Art. 50") for r in required_refs):
            rep.warn(
                "actions",
                "F7 is 'yes': consider the applicable Art. 50 duty as a required action, "
                "whatever the class",
            )
    if risk_class == "high":
        role = summary.get("role")
        missing = []
        if (
            role in {"deployer", "both", "unknown"}
            and not (DEPLOYER_DUTIES & required_refs)
            and not (role == "unknown" and PROVIDER_DUTIES & required_refs)
        ):
            missing.append("a deployer duty (Art. 26, 27 or 86)")
        if role in {"provider", "both"} and not (PROVIDER_DUTIES & required_refs):
            missing.append("a provider duty (Art. 9-17, 43, 47-49, 72 or 73)")
        if missing:
            rep.warn(
                "actions",
                "a high-risk result usually carries more duties; consider listing "
                + " and ".join(missing)
                + " as required actions",
            )

    # Triggers
    for i, tr in enumerate(objects(data.get("triggers"), "triggers", rep), 1):
        at = f"trigger {i}"
        text_field(tr, "change", at, rep)
        if tr.get("would_become") not in DECIDED_CLASSES:
            rep.error(at, "would_become must be a decided class")
        check_citations(tr.get("citations"), at, rep, citable, {"AI Act"}, need_ai_act=True)
    if risk_class in {"minimal", "limited"} and not data.get("triggers"):
        rep.warn("triggers", "none listed; say what would raise the class")

    # Open questions
    oq = data.get("open_questions", [])
    if not isinstance(oq, list) or not all(isinstance(x, str) and x.strip() for x in oq):
        rep.error("open_questions", "must be a list of non-empty strings")

    # Adjacent law
    for i, adj in enumerate(objects(data.get("adjacent"), "adjacent", rep), 1):
        at = f"adjacent {i}"
        text_field(adj, "flag", at, rep)
        check_citations(adj.get("citations"), at, rep, citable, INSTRUMENTS, need_ai_act=False)
        check_evidence(
            adj.get("evidence"), at, rep, pack, blueprint, transcript, answers, required=False
        )

    if not (pack / "docs" / "ai_act_screening.md").is_file():
        rep.warn("brief", "docs/ai_act_screening.md has not been written yet")
    return rep


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--pack", required=True, type=Path, help="the wizard's output directory")
    parser.add_argument("--screening", type=Path, help="default: <pack>/ai_act_screening.json")
    parser.add_argument(
        "--transcript", type=Path, help="saved wizard conversation, to verify conversation quotes"
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--hash", action="store_true", help="print the blueprint fingerprint and exit"
    )
    mode.add_argument(
        "--status",
        action="store_true",
        help="print current | outdated | unverified | none for the saved screening and exit",
    )
    args = parser.parse_args()

    if args.status:
        print(screening_status(args.pack))
        return 0
    if args.hash:
        try:
            print(
                blueprint_hash(
                    json.loads((args.pack / "use_case.blueprint.json").read_text(encoding="utf-8"))
                )
            )
        except (OSError, ValueError) as exc:
            print(f"ERROR    cannot read use_case.blueprint.json: {exc}")
            return 1
        return 0

    transcript = None
    if args.transcript:
        try:
            transcript = args.transcript.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            print(f"ERROR    transcript: cannot read {args.transcript}: {exc}")
            return 1
    rep = check(args.pack, args.screening or args.pack / "ai_act_screening.json", transcript)

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
