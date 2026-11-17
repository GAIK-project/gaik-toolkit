#!/usr/bin/env python3
"""Write the AI Act screening brief in plain language from ai_act_screening.json.

The brief is a rendering of the JSON: it says nothing the JSON does not. It starts with a short
summary, explains every term where it is used (risk level, confidence, role, the two duties that
apply whatever the level, evidence, provision, required and recommended actions), and ends with
the provisions the screening cites, in plain words taken from the reference.

It also writes the standard glossary into the JSON, so the data file explains itself too.

    python render_brief.py --pack <wizard_output_dir>
    python render_brief.py --pack <wizard_output_dir> --outdated   # adds the outdated line

Standard library only.
"""

from __future__ import annotations

import argparse
import datetime
import json
import re
import sys
from pathlib import Path

REFERENCES = Path(__file__).resolve().parents[1] / "references"
LEVELS = [
    ("unacceptable", "Unacceptable risk"),
    ("high", "High-risk"),
    ("limited", "Limited risk (transparency obligations)"),
    ("minimal", "Minimal or no risk"),
]
NAMES = dict(LEVELS) | {"not_decided": "Not decided yet"}
ANSWERS = {"yes": "Yes", "no": "No", "unknown": "Unknown", "not_applicable": "Not applicable"}
WHERE = {"wizard": "Change through the wizard", "organisation": "Your organisation"}
TERMS = [
    ("AI system", "ai_system"),
    ("High-risk areas (Annex III)", "annex_iii"),
    ("General-purpose AI model", "gpai"),
    ("Role", "role"),
    ("Confidence", "confidence"),
    ("Evidence", "evidence"),
    ("Provision", "provision"),
    ("Required action", "required_action"),
    ("Recommended action", "recommended_action"),
    ("Where (route)", "route"),
    ("Fingerprint", "fingerprint"),
]


def plain(text: str) -> str:
    """Text without markdown emphasis, on one line."""
    return " ".join(re.sub(r"[*`]", "", text).split())


def shorten(text: str, limit: int = 230) -> str:
    """The first sentence, or the text cut at a word boundary."""
    text = plain(text)
    end = text.find(". ")
    if 0 < end < limit:
        return text[: end + 1]
    if len(text) <= limit:
        return text.rstrip(".") + "."
    return text[:limit].rsplit(" ", 1)[0] + "…"


def provision_text(ref: str, reference: str) -> str | None:
    """What a provision says, in plain words, from the reference's own bullets."""
    flags = re.S | re.M
    safe = re.escape(ref)
    m = re.search(rf"^(?:- )?\*\*{safe}\*\*\s*[—-]?\s*(.+?)(?=\n- |\n\n|\Z)", reference, flags)
    if m:
        return shorten(m.group(1))
    if re.fullmatch(r"Art\. \d+", ref):  # a whole article: use its first paragraph
        return provision_text(f"{ref}(1)", reference)
    sub = re.match(r"(.+\(\d+\))\(([a-z])\)$", ref)
    if sub:
        parent, letter = sub.groups()
        pm = re.search(
            rf"^- \*\*{re.escape(parent)}[^*]*\*\*\s*[—-]\s*(.+?)(?=\n- |\n\n|\Z)", reference, flags
        )
        if pm:
            body = " ".join(pm.group(1).split())
            part = re.search(rf"\({letter}\)\s*(.+?)(?=\s\([a-z]\)|$)", body)
            if part:
                return shorten(part.group(1))
    m = re.search(rf"\*\*{safe}\*\*\s+([^·\n*]+?)(?=\s*·|\n|$)", reference)
    if m:
        return shorten(m.group(1))
    return None


def meaning(glossary: dict, key: str) -> str:
    """A glossary entry without its leading label ("Minimal or no risk: ...")."""
    text = glossary.get(key, "")
    head, sep, rest = text.partition(": ")
    return rest if sep and len(head) < 60 else text


def sentence(text: str) -> str:
    """The text starting with a capital letter."""
    text = text.strip()
    return text[:1].upper() + text[1:]


def without_verdict(answer: str) -> str:
    """The answer without a leading Yes/No that the heading already says."""
    return re.sub(r"^(yes|no|unknown|not applicable)\b[.:,]?\s*", "", answer.strip(), flags=re.I)


def evidence_line(e: dict) -> str:
    source, quote = e.get("source"), e.get("quote", "")
    if source == "blueprint":
        return f"The blueprint, at `{e['locator']}`: “{quote}”"
    if source == "document":
        return f"The document `{e['locator']}`: “{quote}”"
    if source == "screening_answer":
        return f"Your answer {e['locator']}: “{quote}”"
    if source == "conversation":
        return f"The conversation ({e['locator']}): “{quote}”"
    return f"The pack does not record it (checked `{e['locator']}`)."


def when(iso: str, today: datetime.date) -> str:
    day = datetime.date.fromisoformat(iso)
    label = f"{day.day} {day.strftime('%b %Y')}"
    if day <= today:
        return f"{label} (in force)"
    return f"{label} (in {max(1, round((day - today).days / 30.4))} months)"


def refs(citations: list[dict]) -> str:
    return (
        ", ".join(("GDPR " if c.get("instrument") == "GDPR" else "") + c["ref"] for c in citations)
        or "—"
    )


def render(
    d: dict, blueprint: dict, glossary: dict, provisions: dict, reference: str, outdated: bool
) -> str:
    s = d["summary"]
    cls = s["risk_class"]
    today = datetime.datetime.fromisoformat(d["screened_at"]).date()
    findings = {f["id"]: f for f in d["findings"]}
    required = [a for a in d["actions"] if a["type"] == "required"]
    optional = [a for a in d["actions"] if a["type"] == "recommended"]
    name = blueprint.get("use_case", {}).get("name", d["pack"].get("blueprint_id", ""))

    out = [f"# EU AI Act screening — {name}", ""]
    if outdated:
        out += [
            f"> **Outdated.** The blueprint changed after this screening ({today}). Rerun the",
            "> screening before relying on it.",
            "",
        ]
    out += [
        "**This is a preliminary screening, not legal advice.** It sorts the solution into one",
        "of the four risk levels of the EU AI Act, using the facts recorded in the solution",
        "pack and your answers. It only proposes: nothing here blocks the wizard, and you can",
        "accept or skip every proposal.",
        "",
        f"Blueprint `{d['pack']['blueprint_id']}`; screened {today}; the AI Act reference used",
        f"was verified on {d['reference_last_verified']}.",
        "",
        "## Summary",
        "",
        s.get("interpretation") or s.get("one_line", ""),
        "",
        f"- **Risk level:** {NAMES[cls]}",
        f"- **Duties for you:** {len(required)} required (duties in the Act),"
        f" {len(optional)} optional suggestion(s)",
        f"- **Still open:** {len(d.get('open_questions', []))} question(s)",
        "",
        "## Result",
        "",
        "| | |",
        "|---|---|",
        f"| Risk level | **{NAMES[cls]}**. {sentence(meaning(glossary, cls))} |",
        f"| Your role | **{s['role']}**. {glossary['role']} |",
        f"| Confidence | **{s['confidence']}**. {sentence(s.get('confidence_reason', ''))} "
        f"*{glossary['confidence']}* |",
        "",
        "The four risk levels of the Act, and where this result falls:",
        "",
        "| Risk level | What it means | This result |",
        "|---|---|---|",
    ]
    for key, label in LEVELS:
        mark = "◀ this result" if key == cls else ""
        out.append(f"| {label} | {sentence(meaning(glossary, key))} | {mark} |")
    if cls == "not_decided":
        possible = ", ".join(NAMES[a["risk_class"]] for a in s.get("alternatives", []))
        out += [
            "",
            f"**Not decided yet.** {glossary['not_decided']} Possible levels: {possible}.",
            "",
        ]
        for alt in s.get("alternatives", []):
            out.append(f"- If {alt['if']}: **{NAMES[alt['risk_class']]}**.")
    out += [
        "",
        f"**What was screened:** {s['intended_deployment']} The proof of concept itself is"
        " development work and outside the Act; the screening looks at the intended real use.",
        "",
        "## Duties that apply whatever the risk level",
        "",
    ]
    f6, f7 = findings.get("F6", {}), findings.get("F7", {})
    flags = s["flags"]
    out += [
        "- **Exception for high-risk areas (Art. 6(3)):** "
        + ("**relied on.**" if flags["art_6_3_exempt"] else "**not relied on.**")
        + f" {glossary['art_6_3_exempt']} {without_verdict(f6.get('answer', ''))}",
        "- **Transparency obligations (Art. 50):** "
        + ("**apply.**" if flags["transparency_duties"] else "**do not apply.**")
        + f" {glossary['transparency_duties']} {without_verdict(f7.get('answer', ''))}",
        "",
        "## How the result was reached",
        "",
        "The screening answers eight fixed questions. Each answer is Yes, No, Unknown or Not",
        "applicable, and shows its evidence, the provision it rests on, and the reasoning.",
        "",
    ]
    for fid in sorted(findings):
        f = findings[fid]
        question, _, why_it_matters = glossary.get(fid, f["question"]).partition("? ")
        out += [
            f"### {fid} — {question}?",
            "",
        ]
        if why_it_matters:
            out += [f"*{why_it_matters}*", ""]
        out += [
            f"**Answer: {ANSWERS[f['status']]}.** {without_verdict(f['answer'])}",
            "",
            f"**Why:** {f['reasoning']}",
            "",
        ]
        if f["evidence"]:
            out += ["**Evidence:**"] + [f"- {evidence_line(e)}" for e in f["evidence"]] + [""]
        if f["citations"]:
            out += [f"**Provision:** {refs(f['citations'])}", ""]
    out += [
        "## What you must do",
        "",
        f"{glossary['required_action']}",
        "",
        "| Action | From | Provision | Where | Already in the pack |",
        "|---|---|---|---|---|",
    ]
    for a in required:
        out.append(
            f"| {a['action']} | {when(a['applies_from'], today)} | {refs(a['citations'])} |"
            f" {WHERE[a['route']]} | {a.get('pack_support', '—')} |"
        )
    if not required:
        out.append("| None on the recorded facts. | | | | |")
    out += ["", "## Suggestions (optional)", "", glossary["recommended_action"], ""]
    for a in optional:
        out.append(f"- {a['action']} {a['reason']} *({WHERE[a['route']]})*")
    if not optional:
        out.append("- None at the moment.")
    out += ["", "## What would raise the risk level", "", glossary["triggers"], ""]
    for t in d.get("triggers", []):
        out.append(f"- {t['change']} → **{NAMES[t['would_become']]}** ({refs(t['citations'])})")
    out += ["", "## Open questions", "", glossary["open_questions"], ""]
    out += [f"- {q}" for q in d.get("open_questions", [])] or ["- None."]
    out += ["", "## Related rules outside the AI Act", "", glossary["related_rules"], ""]
    out += [f"- {a['flag']} ({refs(a['citations'])})" for a in d.get("adjacent", [])] or ["- None."]

    cited: dict[tuple[str, str], None] = {}
    groups = [d["findings"], d["actions"], d.get("triggers", []), d.get("adjacent", [])]
    for group in groups:
        for item in group:
            for c in item.get("citations", []):
                cited[(c.get("instrument", "AI Act"), c["ref"])] = None
    out += ["", "## Provisions cited", "", "| Provision | In plain words |", "|---|---|"]
    for instrument, ref in cited:
        plain_words = provisions.get(instrument, {}).get(ref) or provision_text(ref, reference)
        label = f"GDPR {ref}" if instrument == "GDPR" else ref
        out.append(f"| {label} | {plain_words or 'See the Act.'} |")
    out += ["", "## Terms used", ""]
    out += [f"- **{label}:** {glossary[key]}" for label, key in TERMS]
    return "\n".join(out) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--pack", required=True, type=Path, help="the wizard's output directory")
    parser.add_argument("--outdated", action="store_true", help="add the outdated line")
    args = parser.parse_args()
    pack = args.pack
    try:
        data = json.loads((pack / "ai_act_screening.json").read_text(encoding="utf-8"))
        blueprint = json.loads((pack / "use_case.blueprint.json").read_text(encoding="utf-8"))
        glossary = json.loads((REFERENCES / "glossary.json").read_text(encoding="utf-8"))
        provisions = json.loads((REFERENCES / "provisions.json").read_text(encoding="utf-8"))
        reference = (REFERENCES / "ai-act-reference.md").read_text(encoding="utf-8")
    except (OSError, ValueError) as exc:
        print(f"ERROR    {exc}")
        return 1
    try:
        brief = render(data, blueprint, glossary, provisions, reference, args.outdated)
    except (KeyError, TypeError, ValueError) as exc:
        print(
            f"ERROR    the screening is incomplete or malformed ({exc!r}); run check_screening.py"
        )
        return 1
    data["glossary"] = glossary
    (pack / "ai_act_screening.json").write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (pack / "docs").mkdir(exist_ok=True)
    (pack / "docs" / "ai_act_screening.md").write_text(brief, encoding="utf-8")
    print(f"Wrote docs/ai_act_screening.md ({len(brief.splitlines())} lines) and the glossary.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
