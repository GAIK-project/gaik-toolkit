"""A small, valid EU AI Act screening, synthetic, for the checker's tests and smoke check.

It is an intake and a screening that pass the skill's own checker (minimal risk, planned,
no required action beyond AI literacy). Its quotes are copied from the intake, as the checker
demands, so a change to the skill's rules that this sample no longer meets shows up as a
failing test or smoke check.
"""

from __future__ import annotations

import copy

DESCRIPTION = (
    "We plan an AI tool that reads supplier invoices and extracts the supplier, dates and "
    "totals for our accounting staff to check."
)
ANSWER_USERS = "Only our own accounting staff use it."
ANSWER_ROLE = "We build it ourselves."

INTAKE: dict = {
    "intake_version": "1.0",
    "use_case_name": "Invoice data extraction",
    "mode": "planned",
    "lifecycle_stage": "idea",
    "description": DESCRIPTION,
    "documents": [],
    "questions": [
        {"id": "Q1", "batch": "B", "question": "Who uses it?", "answer": ANSWER_USERS},
        {
            "id": "Q2",
            "batch": "D",
            "question": "Do you build it yourselves or buy it?",
            "answer": ANSWER_ROLE,
        },
    ],
}


def _finding(fid: str, question: str, status: str, citation: str, quote: dict) -> dict:
    return {
        "id": fid,
        "question": question,
        "status": status,
        "answer": "See the reasoning.",
        "evidence": [quote],
        "citations": [{"ref": citation}],
        "reasoning": "The description gives the facts this finding rests on.",
        "confidence": "medium",
    }


_DESC = {"source": "description", "locator": "description", "quote": DESCRIPTION}
_USERS = {"source": "answer", "locator": "Q1", "quote": ANSWER_USERS}
_ROLE = {"source": "answer", "locator": "Q2", "quote": ANSWER_ROLE}

SCREENING: dict = {
    "screened_on": "2026-11-16",
    "summary": {
        "outcome": "classified",
        "risk_class": "minimal",
        "role": "both",
        "confidence": "medium",
        "mode": "planned",
        "lifecycle_stage": "idea",
        "screened_use": "An in-house invoice reader used by accounting staff.",
        "one_line": "Reads invoices for staff to check; no listed high-risk use.",
        "flags": {"art_6_3_exempt": False, "transparency_duties": False},
    },
    "findings": [
        _finding("F1", "Is it an AI system in scope of the Act?", "yes", "Art. 3(1)", _DESC),
        _finding("F2", "Is the user a provider, a deployer, or both?", "yes", "Art. 3(3)", _ROLE),
        _finding("F3", "Does it involve a prohibited practice?", "no", "Art. 5", _DESC),
        _finding("F4", "Is it part of a regulated product?", "no", "Annex I", _DESC),
        _finding("F5", "Does its purpose fall in an Annex III area?", "no", "Annex III", _USERS),
        _finding("F6", "Does the Art. 6(3) exception apply?", "not_applicable", "Art. 6(3)", _DESC),
        _finding("F7", "Do transparency duties apply?", "no", "Art. 50(1)", _USERS),
        _finding(
            "F8", "Which general-purpose AI model does it rely on?", "unknown", "Art. 53", _DESC
        ),
    ],
    "actions": [
        {
            "type": "required",
            "action": "Make sure the staff who use the tool know enough about AI to use it well.",
            "route": "organisation",
            "applies_to": "both",
            "applies_from": "2025-02-02",
            "citations": [{"ref": "Art. 4"}],
            "based_on": ["F2"],
        }
    ],
    "timeline": [
        {
            "date": "2025-02-02",
            "what": "AI literacy for staff using AI systems",
            "status": "in_force",
            "citations": [{"ref": "Art. 4"}],
        }
    ],
    "triggers": [
        {
            "change": "the tool is used to rank job applicants",
            "would_become": "high",
            "citations": [{"ref": "Annex III(4)(a)"}],
        },
        {
            "change": "the tool starts to talk to suppliers as a chatbot",
            "would_become": "limited",
            "citations": [{"ref": "Art. 50(1)"}],
        },
    ],
    "open_questions": ["Which general-purpose AI model the tool will use."],
    "adjacent": [],
    "disclaimer": "Preliminary screening based on the description and answers. Not legal advice.",
}


def sample() -> tuple[dict, dict]:
    """A fresh copy of the intake and the screening."""
    return copy.deepcopy(INTAKE), copy.deepcopy(SCREENING)
