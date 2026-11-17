"""Tests for the checker of the wizard's AI Act screening (ai_act_screening/scripts/)

The checker has two kinds of finding. An error means the screening is malformed, contradicts
itself or its sources, or cites something that does not exist. A warning is advice (a missing
duty, an outdated screening, a date not in the reference) and never stops anything. The tests
check which of the two a case gives and a key phrase of the message, not its full wording.
The pack is built from the wizard's incident-reporting example blueprint. No network.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import shutil
from collections.abc import Callable
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_DIR = REPO_ROOT / "implementation_layer/solution_wizard/ai_act_screening"
EXAMPLE = (
    REPO_ROOT / "implementation_layer/solution_wizard/examples/incident_reporting_blueprint.json"
)

_spec = importlib.util.spec_from_file_location(
    "check_screening", SKILL_DIR / "scripts/check_screening.py"
)
cs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cs)

REFERENCE_DATE = cs.load_reference(
    (SKILL_DIR / "references/ai-act-reference.md").read_text("utf-8")
)[1]
DESCRIPTION = (
    "Convert spoken incident observations into structured incident reports "
    "for review and submission."
)
CANVAS = (
    "# Product canvas\n\nA safety manager approves every report before submission.\n"
    "Reports are not used to assess the reporter.\n"
)


def bp(locator: str, quote: str) -> dict:
    return {"source": "blueprint", "locator": locator, "quote": quote}


def finding(fid, status, evidence, citations, confidence="medium"):
    return {
        "id": fid,
        "question": f"Question {fid}",
        "status": status,
        "answer": "Answer.",
        "evidence": evidence,
        "citations": [{"ref": c} for c in citations],
        "reasoning": "Reasoning.",
        "confidence": confidence,
    }


def valid_screening() -> dict:
    return {
        "screening_version": "1.0",
        "reference_last_verified": REFERENCE_DATE,
        "screened_at": "2026-11-16T15:00:00+02:00",
        "pack": {
            "blueprint_id": "incident_reporting_v1",
            "blueprint_sha256": cs.blueprint_hash(json.loads(EXAMPLE.read_text("utf-8"))),
        },
        "questions": [
            {
                "id": "Q1",
                "question": "Who uses it?",
                "answer": "We build it for our own factory and use it ourselves.",
            },
        ],
        "summary": {
            "risk_class": "minimal",
            "role": "both",
            "confidence": "medium",
            "confidence_reason": "it relies on your answer about how the reports are used",
            "interpretation": "Minimal or no risk: it documents incidents for a safety manager.",
            "one_line": "Documents incidents.",
            "intended_deployment": (
                "In-house incident reporting at one factory, reviewed by a safety manager."
            ),
            "flags": {"art_6_3_exempt": False, "transparency_duties": False},
        },
        "findings": [
            finding(
                "F1", "yes", [bp("/models/extraction_model", "gpt-5.4")], ["Art. 3(1)"], "high"
            ),
            finding(
                "F2",
                "yes",
                [
                    {
                        "source": "screening_answer",
                        "locator": "Q1",
                        "quote": "We build it for our own factory",
                    }
                ],
                ["Art. 3(3)", "Art. 3(4)"],
            ),
            finding("F3", "no", [bp("/use_case/description", DESCRIPTION)], ["Art. 5"]),
            finding(
                "F4",
                "no",
                [{"source": "absent", "locator": "/technical_spec/regulated_product", "quote": ""}],
                ["Art. 6(1)"],
            ),
            finding(
                "F5",
                "no",
                [
                    bp("/use_case/description", DESCRIPTION),
                    {
                        "source": "document",
                        "locator": "docs/genai_product_canvas.md",
                        "quote": "Reports are not used to assess the reporter.",
                    },
                ],
                ["Art. 6(2)", "Annex III(4)(b)"],
            ),
            finding("F6", "not_applicable", [], []),
            finding(
                "F7",
                "no",
                [
                    {
                        "source": "document",
                        "locator": "docs/genai_product_canvas.md",
                        "quote": "A safety manager approves every report before submission.",
                    }
                ],
                ["Art. 50(1)"],
            ),
            finding(
                "F8",
                "yes",
                [bp("/governance/data_handling/external_model_api_allowed", "true")],
                ["Art. 53"],
            ),
        ],
        "actions": [
            {
                "type": "required",
                "action": "AI literacy.",
                "route": "organisation",
                "applies_to": "both",
                "applies_from": "2025-02-02",
                "citations": [{"ref": "Art. 4"}],
                "based_on": ["F1", "F2"],
            },
            {
                "type": "recommended",
                "action": "Drop the reporter name field.",
                "reason": "Not needed to fix hazards.",
                "route": "wizard",
                "citations": [{"ref": "Annex III(4)(b)"}],
                "based_on": ["F5"],
            },
        ],
        "triggers": [
            {
                "change": "Used to discipline reporters.",
                "would_become": "high",
                "citations": [{"ref": "Annex III(4)(b)"}],
            }
        ],
        "open_questions": ["Retention policy is not specified."],
        "adjacent": [
            {
                "flag": "Health data.",
                "citations": [{"instrument": "GDPR", "ref": "Art. 9"}],
                "evidence": [bp("/target_output_spec/fields", "injured_persons")],
            }
        ],
        "disclaimer": "Preliminary screening. Not legal advice.",
        "glossary": json.loads((SKILL_DIR / "references/glossary.json").read_text("utf-8")),
    }


@pytest.fixture()
def pack(tmp_path: Path) -> Path:
    shutil.copy(EXAMPLE, tmp_path / "use_case.blueprint.json")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs/genai_product_canvas.md").write_text(CANVAS, "utf-8")
    (tmp_path / "docs/ai_act_screening.md").write_text("# brief\n", "utf-8")
    return tmp_path


def run(pack: Path, data, transcript: str | None = None):
    path = pack / "ai_act_screening.json"
    path.write_text(json.dumps(data), "utf-8")
    return cs.check(pack, path, transcript)


def status(data, fid, value):
    next(f for f in data["findings"] if f["id"] == fid)["status"] = value


def test_valid_screening_passes(pack):
    rep = run(pack, valid_screening())
    assert rep.errors == []


def _set(path: list, value) -> Callable[[dict], None]:
    def apply(d):
        node = d
        for key in path[:-1]:
            node = node[key]
        node[path[-1]] = value

    return apply


def _undetermined(fid: str) -> Callable[[dict], None]:
    def apply(d):
        status(d, fid, "unknown")
        if fid == "F3":  # make F4 point to high-risk, as in the defect
            status(d, "F4", "yes")

    return apply


def _applies(d, fid, value):
    """Make a finding apply, with the evidence and citation an applying finding needs."""
    status(d, fid, value)
    f = next(f for f in d["findings"] if f["id"] == fid)
    f["evidence"] = [bp("/use_case/domain", "manufacturing_safety")]
    f["citations"] = [{"ref": "Art. 6(3)"}]


def _f5_yes_f6_unknown(d):
    status(d, "F5", "yes")
    _applies(d, "F6", "unknown")
    d["summary"]["risk_class"] = "high"


def _f6_exempt_without_duty(d):
    status(d, "F5", "yes")
    _applies(d, "F6", "yes")
    d["summary"]["flags"]["art_6_3_exempt"] = True


def _transparency_without_art50(d):
    status(d, "F7", "yes")
    d["summary"]["risk_class"] = "limited"
    d["summary"]["flags"]["transparency_duties"] = True


def _high_risk_without_duty(d):
    status(d, "F5", "yes")
    _applies(d, "F6", "no")
    d["summary"]["risk_class"] = "high"


BUGS = {
    # citations
    "annex IV read as annex I": (
        _set(["triggers", 0, "citations", 0, "ref"], "Annex IV"),
        "Annex IV",
    ),
    "invented paragraph": (
        _set(["findings", 3, "citations", 0, "ref"], "Art. 6(999)(z)"),
        "Art. 6(999)(z)",
    ),
    "invented annex point": (
        _set(["triggers", 0, "citations", 0, "ref"], "Annex III(4)(z)"),
        "Annex III(4)(z)",
    ),
    "GDPR article as AI Act": (_set(["findings", 0, "citations", 0, "ref"], "Art. 35"), "Art. 35"),
    "foreign instrument bypass": (
        _set(["findings", 0, "citations"], [{"instrument": "Other", "ref": "Art. 999"}]),
        "instrument",
    ),
    "GDPR in a finding": (
        _set(["findings", 0, "citations"], [{"instrument": "GDPR", "ref": "Art. 9"}]),
        "belong in 'adjacent'",
    ),
    # quotes
    "number fragment": (
        _set(["findings", 0, "evidence", 0], bp("/workflow/steps/1/parameters/language", "f")),
        "does not equal",
    ),
    "string fragment": (
        _set(["findings", 0, "evidence", 0], bp("/models/extraction_model", "5.4")),
        "does not equal",
    ),
    "list fragment": (
        _set(["findings", 2, "evidence", 0], bp("/target_output_spec/fields", "sever")),
        "not an element",
    ),
    "object pointer": (
        _set(["findings", 0, "evidence", 0], bp("/models", "gpt-5.4")),
        "is an object",
    ),
    "dropped negation": (
        _set(["findings", 4, "evidence", 1, "quote"], "used to assess the reporter."),
        None,
    ),
    "quote marks only": (_set(["findings", 4, "evidence", 1, "quote"], '""'), "not in"),
    "whitespace only": (_set(["findings", 4, "evidence", 1, "quote"], "   "), "quote is empty"),
    "fabricated answer id": (
        _set(["findings", 1, "evidence", 0, "locator"], "Q999"),
        "not a question id",
    ),
    "fabricated answer text": (
        _set(["findings", 1, "evidence", 0, "quote"], "We sell it to clients"),
        "recorded answer",
    ),
    "screening cites itself": (
        _set(["findings", 4, "evidence", 1, "locator"], "docs/ai_act_screening.md"),
        "own output",
    ),
    "path traversal": (
        _set(["findings", 4, "evidence", 1, "locator"], "../../etc/passwd"),
        "outside the pack",
    ),
    "absent with a quote": (
        _set(["findings", 2, "evidence", 0], {"source": "absent", "locator": "/x", "quote": "y"}),
        "empty quote",
    ),
    "absent not a pointer": (
        _set(
            ["findings", 2, "evidence", 0], {"source": "absent", "locator": "fields", "quote": ""}
        ),
        "pointer",
    ),
    # pointers
    "leading-zero index": (
        _set(["findings", 0, "evidence", 0, "locator"], "/workflow/steps/05/type"),
        "leading zeros",
    ),
    "bad escape": (
        _set(["findings", 3, "evidence", 0, "locator"], "/runtime/~2"),
        "invalid escape",
    ),
    "slash is not root": (_set(["findings", 0, "evidence", 0, "locator"], "/"), "does not exist"),
    # classification
    "F1 unknown, minimal": (_undetermined("F1"), "findings imply 'not_decided'"),
    "F3 unknown hidden by F4": (_undetermined("F3"), "findings imply 'not_decided'"),
    "F5 yes, F6 unknown": (_f5_yes_f6_unknown, "findings imply 'not_decided'"),
    "not_applicable bypass": (
        lambda d: status(d, "F3", "not_applicable"),
        "'not_applicable' is allowed only",
    ),
    "applying finding without evidence": (
        lambda d: d["findings"][3].update(evidence=[]),
        "no evidence",
    ),
    "flag contradicts findings": (
        _set(["summary", "flags", "transparency_duties"], True),
        "transparency_duties",
    ),
    # structure
    "null reasoning": (_set(["findings", 0, "reasoning"], None), "'reasoning' must be"),
    "duplicate finding": (
        lambda d: d["findings"].append(copy.deepcopy(d["findings"][7])),
        "must be exactly",
    ),
    "summary as string": (_set(["summary"], "minimal"), "summary: must be an object"),
    "findings not objects": (_set(["findings"], ["F1"]), "must be an object"),
    "questions missing": (lambda d: d.pop("questions"), "questions: missing"),
}


@pytest.mark.parametrize("name", list(BUGS))
def test_defect_is_rejected(pack, name):
    mutate, expected = BUGS[name]
    data = valid_screening()
    mutate(data)
    rep = run(pack, data)
    if name == "dropped negation":
        # A shorter quote that still occurs is not detectable mechanically; the skill
        # requires whole sentences instead. Record that the checker does not claim it.
        assert rep.errors == []
        return
    assert rep.errors, f"{name} passed"
    assert any(expected in e for e in rep.errors), rep.errors


@pytest.mark.parametrize("root", [[], "x", 1, None])
def test_malformed_root_is_an_error_not_a_crash(pack, root):
    rep = run(pack, root)
    assert any("top level" in e for e in rep.errors)


def _prohibited_with_required(d):
    status(d, "F3", "yes")
    d["summary"]["risk_class"] = "unacceptable"


ACTION_BUGS = {
    "required without citation": (_set(["actions", 0, "citations"], []), "AI Act citation"),
    "missing route": (lambda d: d["actions"][0].pop("route"), "route"),
    "unknown type": (_set(["actions", 0, "type"], "optional"), "type must be"),
    "recommendation without reason": (lambda d: d["actions"][1].pop("reason"), "'reason'"),
    "no intended deployment": (
        lambda d: d["summary"].pop("intended_deployment"),
        "intended_deployment",
    ),
    "date that is not a date": (_set(["actions", 0, "applies_from"], "soon"), "ISO date"),
}


@pytest.mark.parametrize("name", list(ACTION_BUGS))
def test_action_contract(pack, name):
    mutate, expected = ACTION_BUGS[name]
    data = valid_screening()
    mutate(data)
    rep = run(pack, data)
    assert any(expected in e for e in rep.errors), rep.errors


def test_blueprint_change_makes_screening_outdated(pack):
    assert cs.screening_status(pack) == "none"
    run(pack, valid_screening())
    assert cs.screening_status(pack) == "current"
    # Reformatting the file is not a change
    blueprint = json.loads((pack / "use_case.blueprint.json").read_text("utf-8"))
    (pack / "use_case.blueprint.json").write_text(json.dumps(blueprint, indent=4), "utf-8")
    assert cs.screening_status(pack) == "current"
    # A change of intent is
    blueprint["target_output_spec"]["fields"].remove("reporter_name")
    (pack / "use_case.blueprint.json").write_text(json.dumps(blueprint), "utf-8")
    assert cs.screening_status(pack) == "outdated"
    rep = cs.check(pack, pack / "ai_act_screening.json", None)
    assert rep.errors == [] and any("OUTDATED" in w for w in rep.warnings)


def test_manual_run_without_fingerprint_is_unverified(pack):
    data = valid_screening()
    data["pack"]["blueprint_sha256"] = ""
    rep = run(pack, data)
    assert rep.errors == [] and any("manual" in w for w in rep.warnings)
    assert cs.screening_status(pack) == "unverified"


def test_conversation_quote_without_transcript_is_unverified(pack):
    data = valid_screening()
    data["findings"][1]["evidence"] = [
        {"source": "conversation", "locator": "user", "quote": "It is for our own factory."}
    ]
    rep = run(pack, data)
    assert rep.errors == []
    assert any("not verified" in w for w in rep.warnings)
    assert run(pack, data, transcript="user: Something else.").errors
    assert run(pack, data, transcript="user: It is for our own factory.").errors == []


def test_pointer_rules():
    doc = {"": 1, "a/b": 2, "m~n": 3, "l": [10, 11]}
    assert cs.resolve(doc, "") is doc
    assert cs.resolve(doc, "/") == 1
    assert cs.resolve(doc, "/a~1b") == 2
    assert cs.resolve(doc, "/m~0n") == 3
    assert cs.resolve(doc, "/l/1") == 11
    for bad in ("/l/01", "/l/-", "/x~2", "x"):
        with pytest.raises(ValueError):
            cs.resolve(doc, bad)


def test_undetermined_needs_alternatives(pack):
    data = valid_screening()
    status(data, "F5", "unknown")
    data["summary"]["risk_class"] = "not_decided"
    rep = run(pack, data)
    assert rep.errors == [] and any("alternatives" in w for w in rep.warnings)
    data["summary"]["alternatives"] = [
        {"if": "Output is used to evaluate workers", "risk_class": "high"},
        {"if": "Output is only used to fix hazards", "risk_class": "minimal"},
    ]
    rep = run(pack, data)
    assert rep.errors == [] and not any("alternatives" in w for w in rep.warnings)
    data["summary"]["alternatives"][0]["risk_class"] = "not_decided"
    assert any("four levels" in e for e in run(pack, data).errors)


def test_every_reference_citation_label_is_unique_and_wellformed():
    citable, verified = cs.load_reference(
        (SKILL_DIR / "references/ai-act-reference.md").read_text("utf-8")
    )
    assert verified
    assert "Annex III(4)(b)" in citable["AI Act"] and "Art. 35" not in citable["AI Act"]
    assert citable["GDPR"] >= {"Art. 9", "Art. 35"}


# --------------------------------------------------------------------------- advice, never a stop


def _recommendation_with_date(d):
    d["actions"][1]["applies_from"] = "2025-02-02"


def _prohibited_with_required(d):
    status(d, "F3", "yes")
    d["summary"]["risk_class"] = "unacceptable"


ADVICE = {
    "high-risk without a duty for the role": (_high_risk_without_duty, "high-risk result"),
    "exempt without registration duty": (_f6_exempt_without_duty, "Art. 6(4) or Art. 49(2)"),
    "transparency without Art. 50": (_transparency_without_art50, "Art. 50"),
    "date not in the reference": (
        _set(["actions", 0, "applies_from"], "2031-01-01"),
        "table of application dates",
    ),
    "recommendation posing as duty": (_recommendation_with_date, "not a legal duty"),
    "prohibited with required action": (_prohibited_with_required, "no required actions"),
    "fingerprint missing": (lambda d: d["pack"].pop("blueprint_sha256"), "--hash"),
    "old reference date": (_set(["reference_last_verified"], "2020-01-01"), "differs from"),
    "high confidence on absent evidence": (
        _set(["findings", 3, "confidence"], "high"),
        "absent evidence",
    ),
    "case changed in a quote": (
        _set(
            ["findings", 4, "evidence", 1, "quote"], "reports are not used to assess the reporter."
        ),
        "case or punctuation",
    ),
    "a dash inside a quote": (
        _set(
            ["findings", 6, "evidence", 0, "quote"],
            "A safety manager approves every report \u2014 before submission.",
        ),
        "case or punctuation",
    ),
}


@pytest.mark.parametrize("name", list(ADVICE))
def test_advice_is_a_warning_not_an_error(pack, name):
    mutate, phrase = ADVICE[name]
    data = valid_screening()
    mutate(data)
    rep = run(pack, data)
    assert rep.errors == [], rep.errors
    assert any(phrase in w for w in rep.warnings), rep.warnings


def test_a_high_risk_result_with_a_duty_for_the_role_has_no_warning(pack):
    data = valid_screening()
    _high_risk_without_duty(data)
    data["actions"].append(
        {
            "type": "required",
            "action": "Assign trained people to oversee it.",
            "route": "organisation",
            "applies_to": "deployer",
            "applies_from": "2027-12-02",
            "citations": [{"ref": "Art. 26(2)"}],
            "based_on": ["F5"],
        }
    )
    data["actions"].append(
        {
            "type": "required",
            "action": "Keep technical documentation.",
            "route": "organisation",
            "applies_to": "provider",
            "applies_from": "2027-12-02",
            "citations": [{"ref": "Art. 11"}],
            "based_on": ["F5"],
        }
    )
    rep = run(pack, data)
    assert rep.errors == [] and not any("high-risk result" in w for w in rep.warnings)


def test_quote_with_curly_quotes_and_other_case_is_found(pack):
    data = valid_screening()
    data["findings"][6]["evidence"][0]["quote"] = (
        "\u201cA SAFETY MANAGER approves every report before submission.\u201d"
    )
    rep = run(pack, data)
    assert rep.errors == [] and any("case or punctuation" in w for w in rep.warnings)


def test_a_quote_with_an_extra_word_is_not_found(pack):
    data = valid_screening()
    data["findings"][6]["evidence"][0]["quote"] = (
        "A safety manager approves every single report before submission."
    )
    assert any("not in" in e for e in run(pack, data).errors)


def test_a_finding_that_does_not_apply_needs_only_its_reasoning(pack):
    data = valid_screening()
    assert (
        data["findings"][5]["status"] == "not_applicable" and data["findings"][5]["evidence"] == []
    )
    assert run(pack, data).errors == []
    data["findings"][5]["reasoning"] = ""
    assert any("reasoning" in e for e in run(pack, data).errors)


def test_fingerprint_ignores_what_does_not_change_the_solution(pack):
    run(pack, valid_screening())
    path = pack / "use_case.blueprint.json"
    blueprint = json.loads(path.read_text("utf-8"))
    blueprint["metadata"]["last_updated_at"] = "2099-01-01T00:00:00Z"
    blueprint["change_log"] = (blueprint.get("change_log") or []) + [{"note": "AI Act screening"}]
    blueprint["business_spec"]["ai_act_context"] = {"role": "both"}
    path.write_text(json.dumps(blueprint), "utf-8")
    assert cs.screening_status(pack) == "current"
    blueprint["use_case"]["description"] = "Rank job applicants."
    path.write_text(json.dumps(blueprint), "utf-8")
    assert cs.screening_status(pack) == "outdated"


def test_outdated_screening_never_fails_the_command(pack):
    import subprocess
    import sys

    run(pack, valid_screening())
    path = pack / "use_case.blueprint.json"
    blueprint = json.loads(path.read_text("utf-8"))
    blueprint["use_case"]["name"] = "Another name"
    path.write_text(json.dumps(blueprint), "utf-8")
    done = subprocess.run(
        [sys.executable, str(SKILL_DIR / "scripts/check_screening.py"), "--pack", str(pack)],
        capture_output=True,
        text=True,
    )
    assert done.returncode == 0 and "OUTDATED" in done.stdout


def test_application_dates_come_from_the_reference():
    dates = cs.load_application_dates(
        (SKILL_DIR / "references/ai-act-reference.md").read_text("utf-8")
    )
    assert {"2025-02-02", "2026-08-02", "2027-12-02"} <= dates


# --------------------------------------------------------------------------- the four levels


def test_only_the_four_risk_levels_of_the_act_are_classes():
    assert cs.DECIDED_CLASSES == {"unacceptable", "high", "limited", "minimal"}
    assert cs.RISK_CLASSES - cs.DECIDED_CLASSES == {"not_decided"}
    for old in ("prohibited", "high_risk", "transparency", "out_of_scope", "undetermined"):
        assert old not in cs.RISK_CLASSES


def test_a_system_the_act_does_not_cover_is_minimal_or_no_risk(pack):
    data = valid_screening()
    status(data, "F1", "no")
    for fid in ("F2", "F3", "F4", "F5", "F6", "F7", "F8"):
        status(data, fid, "not_applicable")
    data["summary"]["role"] = "both"
    assert (
        cs.expected_class({f"F{i}": "not_applicable" for i in range(2, 9)} | {"F1": "no"})
        == "minimal"
    )


def test_missing_summary_and_glossary_are_warnings(pack):
    data = valid_screening()
    del data["summary"]["interpretation"]
    del data["summary"]["confidence_reason"]
    del data["glossary"]
    rep = run(pack, data)
    assert rep.errors == []
    assert any("interpretation" in w for w in rep.warnings)
    assert any("confidence_reason" in w for w in rep.warnings)
    assert any("glossary" in w for w in rep.warnings)


# --------------------------------------------------------------------------- the brief

_spec2 = importlib.util.spec_from_file_location(
    "render_brief", SKILL_DIR / "scripts/render_brief.py"
)
rb = importlib.util.module_from_spec(_spec2)
_spec2.loader.exec_module(rb)


def rendered(pack, data, outdated=False):
    path = pack / "ai_act_screening.json"
    path.write_text(json.dumps(data), "utf-8")
    glossary = json.loads((SKILL_DIR / "references/glossary.json").read_text("utf-8"))
    reference = (SKILL_DIR / "references/ai-act-reference.md").read_text("utf-8")
    blueprint = json.loads((pack / "use_case.blueprint.json").read_text("utf-8"))
    provisions = json.loads((SKILL_DIR / "references/provisions.json").read_text("utf-8"))
    return rb.render(data, blueprint, glossary, provisions, reference, outdated)


def test_the_brief_starts_with_a_summary_and_explains_its_terms(pack):
    brief = rendered(pack, valid_screening())
    assert brief.index("## Summary") < brief.index("## Result") < brief.index("## How the result")
    for level in (
        "Unacceptable risk",
        "High-risk",
        "Limited risk (transparency obligations)",
        "Minimal or no risk",
    ):
        assert level in brief
    assert "◀ this result" in brief
    # every term a reader meets is explained where it is used
    assert "Exception for high-risk areas (Art. 6(3))" in brief and "not relied on" in brief
    assert "Transparency obligations (Art. 50)" in brief and "do not apply" in brief
    assert "How firmly the result rests on facts" in brief
    assert "Provider:" in brief and "Deployer:" in brief
    assert "The wizard does not enforce it" in brief
    # no raw field names leak into the text for people
    for raw in ("art_6_3_exempt", "transparency_duties", "risk_class", "not_applicable"):
        assert raw not in brief


def test_the_brief_explains_each_provision_it_cites(pack):
    brief = rendered(pack, valid_screening())
    table = brief.split("## Provisions cited", 1)[1].split("## Terms used", 1)[0]
    assert "| Art. 3(1) | Definition: an AI system is a machine-based system" in table
    assert "| Annex III(4)(b) |" in table and "performance and behaviour" in table
    assert "See the Act." not in table


def test_a_result_that_is_not_decided_lists_the_possible_levels(pack):
    data = valid_screening()
    status(data, "F5", "unknown")
    data["summary"].update(
        risk_class="not_decided",
        alternatives=[
            {"if": "the output is used to evaluate workers", "risk_class": "high"},
            {"if": "it is only used to fix hazards", "risk_class": "minimal"},
        ],
    )
    brief = rendered(pack, data)
    assert "Not decided yet" in brief and "this is not a risk level" in brief.lower()
    assert "◀ this result" not in brief
    assert "If the output is used to evaluate workers" in brief or "if the output is used" in brief


def test_the_outdated_line_is_added_on_request(pack):
    assert "**Outdated.**" in rendered(pack, valid_screening(), outdated=True)
    assert "**Outdated.**" not in rendered(pack, valid_screening())


def test_rendering_writes_the_glossary_into_the_data_file(pack):
    data = valid_screening()
    del data["glossary"]
    (pack / "ai_act_screening.json").write_text(json.dumps(data), "utf-8")
    import subprocess
    import sys

    done = subprocess.run(
        [sys.executable, str(SKILL_DIR / "scripts/render_brief.py"), "--pack", str(pack)],
        capture_output=True,
        text=True,
    )
    assert done.returncode == 0, done.stdout
    written = json.loads((pack / "ai_act_screening.json").read_text("utf-8"))
    assert "art_6_3_exempt" in written["glossary"] and "confidence" in written["glossary"]
    assert (
        (pack / "docs/ai_act_screening.md").read_text("utf-8").startswith("# EU AI Act screening")
    )
    assert cs.check(pack, pack / "ai_act_screening.json", None).errors == []


def test_every_citable_provision_has_a_plain_words_line():
    """A report must never say 'See the Act': every provision the checker accepts is explained."""
    text = (SKILL_DIR / "references/ai-act-reference.md").read_text("utf-8")
    citable, _ = cs.load_reference(text)
    provisions = json.loads((SKILL_DIR / "references/provisions.json").read_text("utf-8"))
    for instrument, refs in citable.items():
        missing = sorted(set(refs) - set(provisions.get(instrument, {})))
        assert not missing, f"{instrument}: add plain words to provisions.json for {missing}"
