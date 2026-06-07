"""RequirementCompletenessChecker -- the V3 Gate-1 completeness gate (spec §9).

V1-V2 collected 7 fast-path questions and proceeded with recorded assumptions.
V3 collects the complete Section-8 requirement model and, before component
selection, verifies the 13 Section-9 checklist points are each *answered or
explicitly marked unknown*. The wizard asks follow-up questions for any gap.

This module is the deterministic half of that gate: given a (possibly draft)
Blueprint, ``check_completeness`` returns the list of unmet checklist points so
the agent (SKILL.md) knows exactly what to ask next. "Answered" is intentionally
permissive -- an explicit ``"unknown"`` / ``"none"`` / empty-list value counts,
because the spec allows a point to be *explicitly* deferred. What it catches is
the *silently missing* field.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List

from .blueprint import Blueprint


@dataclass
class Gap:
    """An unmet Section-9 checklist point."""

    number: int
    question: str
    satisfied_by: str  # human-readable hint: which blueprint field(s) close it

    def __str__(self) -> str:
        return f"[{self.number}] {self.question}  (set: {self.satisfied_by})"


# ---------------------------------------------------------------------------
# Field accessors -- specs are free-form dicts (blueprint.py keeps them as
# Dict[str, Any]); these helpers express "answered" precisely.
# ---------------------------------------------------------------------------


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _answered(d: Dict[str, Any], key: str) -> bool:
    """True when key holds a meaningful value. An explicit string such as
    "unknown"/"none"/"no" counts as answered (the user deferred on purpose)."""
    if key not in d:
        return False
    v = d[key]
    if v is None:
        return False
    if isinstance(v, str):
        return v.strip() != ""
    if isinstance(v, (list, dict)):
        return len(v) > 0
    return True  # bool / number


def _present_key(d: Dict[str, Any], key: str) -> bool:
    """True when the key exists at all -- used where an empty list / explicit
    'none' is itself a valid answer (e.g. integration_targets: [] means 'no
    integration', domain_vocabulary: 'none')."""
    return key in d and d[key] is not None


# ---------------------------------------------------------------------------
# The 13 Section-9 checkpoints
# ---------------------------------------------------------------------------


def _check(blueprint: Blueprint) -> List[tuple]:
    bspec = _as_dict(blueprint.business_spec)
    tspec = _as_dict(blueprint.technical_spec)
    tos = _as_dict(blueprint.target_output_spec)
    gov = blueprint.governance.data_handling

    def task_supported() -> bool:
        return bool((blueprint.use_case.description or "").strip()) or _answered(
            bspec, "proposed_solution"
        )

    def users() -> bool:
        return _answered(bspec, "intended_users")

    def inputs() -> bool:
        return _answered(tspec, "input_types") or _answered(bspec, "input_artifacts")

    def outputs() -> bool:
        return _answered(tspec, "output_types") or _answered(bspec, "target_outputs")

    def required_fields() -> bool:
        # Extraction/structured cases need a field list; for answer/report/
        # classification/transcript outputs the output type itself answers it.
        if _answered(tos, "fields") or _present_key(tos, "required_fields"):
            return True
        out = tspec.get("output_types") or []
        out_text = " ".join(out).lower() if isinstance(out, list) else str(out).lower()
        return any(
            t in out_text for t in ("answer", "report", "classification", "transcript", "summary")
        )

    def language() -> bool:
        return _answered(tspec, "language")

    def domain_vocabulary() -> bool:
        # "none" is a valid answer, so presence of the key is enough.
        return _present_key(tspec, "domain_vocabulary")

    def human_review() -> bool:
        return _present_key(tspec, "human_review") or _present_key(tspec, "human_review_required")

    def privacy() -> bool:
        return (
            _answered(tspec, "security_constraints")
            or gov.contains_personal_data != "unknown"
            or gov.output_sensitivity != "unknown"
        )

    def model_provider() -> bool:
        return _answered(tspec, "model_provider")

    def integration() -> bool:
        # [] means "no integration" -- a valid answer.
        return _present_key(tspec, "integration_targets")

    def evaluation() -> bool:
        return _answered(tspec, "evaluation_requirements") or bool(_as_dict(blueprint.evaluation))

    def poc_goal() -> bool:
        return _answered(bspec, "poc_goal") or _answered(bspec, "success_criteria")

    # (number, question, predicate, satisfied_by-hint)
    return [
        (
            1,
            "What task should the system support?",
            task_supported,
            "use_case.description / business_spec.proposed_solution",
        ),
        (2, "Who will use the system?", users, "business_spec.intended_users"),
        (
            3,
            "What input artifacts will the system receive?",
            inputs,
            "technical_spec.input_types / business_spec.input_artifacts",
        ),
        (
            4,
            "What output should the system produce?",
            outputs,
            "technical_spec.output_types / business_spec.target_outputs",
        ),
        (
            5,
            "Which fields, sections, or answer types are required?",
            required_fields,
            "target_output_spec.fields / required_fields (or a non-structured output_type)",
        ),
        (6, "What language is used in the input and output?", language, "technical_spec.language"),
        (
            7,
            "Is domain-specific vocabulary needed?",
            domain_vocabulary,
            "technical_spec.domain_vocabulary (set 'none' if not)",
        ),
        (8, "Does the use case require human review?", human_review, "technical_spec.human_review"),
        (
            9,
            "Are there privacy, security, or compliance constraints?",
            privacy,
            "technical_spec.security_constraints / governance.data_handling",
        ),
        (
            10,
            "Should the solution use a specific model provider?",
            model_provider,
            "technical_spec.model_provider (e.g. 'configurable')",
        ),
        (
            11,
            "Should the output be integrated into another system?",
            integration,
            "technical_spec.integration_targets (set [] for none)",
        ),
        (
            12,
            "How should quality be evaluated?",
            evaluation,
            "technical_spec.evaluation_requirements / evaluation",
        ),
        (
            13,
            "What should the first PoC demonstrate?",
            poc_goal,
            "business_spec.poc_goal / success_criteria",
        ),
    ]


def check_completeness(blueprint: Blueprint) -> List[Gap]:
    """Return the unmet Section-9 checklist points (empty list = complete)."""
    gaps: List[Gap] = []
    for number, question, predicate, hint in _check(blueprint):
        try:
            ok = bool(predicate())
        except Exception:
            ok = False
        if not ok:
            gaps.append(Gap(number=number, question=question, satisfied_by=hint))
    return gaps


def summary(blueprint: Blueprint) -> str:
    """Human-readable satisfied/missing report for the CLI."""
    gaps = check_completeness(blueprint)
    missing = {g.number for g in gaps}
    lines: List[str] = []
    if not gaps:
        lines.append("Requirement completeness PASSED (13/13 checklist points answered)")
    else:
        lines.append(
            f"Requirement completeness INCOMPLETE ({13 - len(gaps)}/13 answered, {len(gaps)} missing)"
        )
    for number, question, _predicate, hint in _check(blueprint):
        mark = "MISSING" if number in missing else "  ok   "
        lines.append(f"  [{mark}] {number:>2}. {question}")
        if number in missing:
            lines.append(f"            -> answer via: {hint}")
    return "\n".join(lines)
