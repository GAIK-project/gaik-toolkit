"""Documentation suite generator (spec §18) -- V3.

Produces the five use-case documents from a validated blueprint into
``<output_dir>/docs/``:

    genai_product_canvas.md      technical_specification.md
    user_guide.md                developer_guide.md
    evaluation_plan.md

Design: deterministic skeleton + agent prose ("Python enforces structure, the
agent authors meaning"). Each template carries ``${...}`` placeholders that this
module fills with blueprint-derived facts, plus ``<!-- AGENT: ... -->`` markers
the wizard fills with narrative afterwards. Mirrors ``scaffolder._write_readme``.

Public API mirrors the other generators:
    generate_docs(blueprint, output_dir) -> list[Path]
"""

from __future__ import annotations

import string
from pathlib import Path
from typing import Any, Dict, List

from .blueprint import Blueprint

TEMPLATES_DIR = Path(__file__).parent.parent.parent / "templates" / "docs"

DOC_NAMES = [
    "genai_product_canvas",
    "technical_specification",
    "user_guide",
    "developer_guide",
    "evaluation_plan",
]


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _fmt_value(value: Any) -> str:
    if value is None or value == "":
        return "_not specified_"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, list):
        return ", ".join(str(v) for v in value) if value else "_none_"
    if isinstance(value, dict):
        return ", ".join(f"{k}: {v}" for k, v in value.items()) if value else "_none_"
    return str(value)


def _bullets(value: Any) -> str:
    if isinstance(value, list):
        items = [str(v) for v in value if str(v).strip()]
    elif isinstance(value, dict):
        items = [f"**{k}**: {v}" for k, v in value.items()]
    elif value in (None, ""):
        items = []
    else:
        items = [str(value)]
    if not items:
        return "- _not specified_"
    return "\n".join(f"- {it}" for it in items)


def _field(d: Dict[str, Any], key: str) -> str:
    return _fmt_value(d.get(key))


# ---------------------------------------------------------------------------
# Variable extraction
# ---------------------------------------------------------------------------


def _components_block(blueprint: Blueprint) -> str:
    comps = blueprint.components
    lines: List[str] = []
    for m in comps.selected_modules:
        mid = getattr(m, "name", None) or getattr(m, "id", "")
        reason = getattr(m, "reason", "") or ""
        lines.append(f"- **{mid}** (module){f' — {reason}' if reason else ''}")
    for b in comps.selected_building_blocks:
        lines.append(f"- **{b}** (component)")
    for c in comps.custom_components:
        lines.append(f"- **{c}** (custom)")
    return "\n".join(lines) if lines else "- _none selected_"


def _workflow_table(blueprint: Blueprint) -> str:
    steps = blueprint.workflow.steps
    if not steps:
        return "_No workflow steps defined._"
    rows = [
        "| Step | Type | Component | Inputs | Outputs |",
        "|------|------|-----------|--------|---------|",
    ]
    for s in steps:
        comp = s.component or "—"
        params = ""
        if s.parameters:
            params = " <br/>opts: " + ", ".join(f"{k}={v}" for k, v in s.parameters.items())
        rows.append(
            f"| {s.id} | {s.type} | {comp}{params} | {', '.join(s.inputs) or '—'} | {', '.join(s.outputs) or '—'} |"
        )
    return "\n".join(rows)


def _artifacts_block(blueprint: Blueprint) -> str:
    if not blueprint.artifacts:
        return "- _none declared_"
    lines = []
    for aid, art in blueprint.artifacts.items():
        flags = []
        if art.final_output:
            flags.append("final output")
        if art.optional:
            flags.append("optional")
        suffix = f" ({', '.join(flags)})" if flags else ""
        lines.append(f"- `{aid}` — {art.type}, source: {art.source.value}{suffix}")
    return "\n".join(lines)


def _build_doc_variables(blueprint: Blueprint) -> Dict[str, str]:
    uc = blueprint.use_case
    bspec = _as_dict(blueprint.business_spec)
    tspec = _as_dict(blueprint.technical_spec)
    tos = _as_dict(blueprint.target_output_spec)
    dh = blueprint.governance.data_handling

    fields = tos.get("fields") or []
    runtime = tspec.get("runtime_interface") or "cli"
    run_cmd = (
        "python poc/run_poc.py" if "cli" in str(runtime).lower() else f"({runtime} entry point)"
    )

    return {
        # identity
        "use_case_name": uc.name,
        "use_case_id": uc.id,
        "domain": uc.domain or "_not specified_",
        "description": uc.description or "_not specified_",
        "knowledge_processes": _fmt_value(
            [k.value if hasattr(k, "value") else k for k in uc.knowledge_processes]
        ),
        # business
        "current_process": _field(bspec, "current_process"),
        "pain_points": _bullets(bspec.get("pain_points")),
        "proposed_solution": _field(bspec, "proposed_solution"),
        "intended_users": _fmt_value(bspec.get("intended_users")),
        "reviewers": _fmt_value(bspec.get("reviewers")),
        "stakeholders": _fmt_value(bspec.get("stakeholders")),
        "input_artifacts": _fmt_value(bspec.get("input_artifacts") or tspec.get("input_types")),
        "target_outputs": _fmt_value(bspec.get("target_outputs") or tspec.get("output_types")),
        "success_criteria": _bullets(bspec.get("success_criteria")),
        "expected_value": _bullets(bspec.get("expected_value")),
        "risks": _bullets(bspec.get("risks")),
        "poc_goal": _field(bspec, "poc_goal"),
        # technical
        "input_types": _fmt_value(tspec.get("input_types")),
        "input_formats": _fmt_value(tspec.get("input_formats")),
        "output_types": _fmt_value(tspec.get("output_types")),
        "language": _field(tspec, "language"),
        "domain_vocabulary": _fmt_value(tspec.get("domain_vocabulary")),
        "data_sources": _fmt_value(tspec.get("data_sources")),
        "model_provider": _field(tspec, "model_provider"),
        "model_preferences": _fmt_value(tspec.get("model_preferences")),
        "security_constraints": _fmt_value(tspec.get("security_constraints")),
        "integration_targets": _fmt_value(tspec.get("integration_targets")),
        "human_review": _fmt_value(tspec.get("human_review", tspec.get("human_review_required"))),
        "evaluation_requirements": _fmt_value(tspec.get("evaluation_requirements")),
        "runtime_interface": _fmt_value(runtime),
        "run_command": run_cmd,
        # target output
        "schema_name": _field(tos, "schema_name"),
        "fields_list": _bullets(fields),
        "field_count": str(len(fields)),
        "required_fields": _fmt_value(tos.get("required_fields")),
        "missing_value_policy": _field(tos, "missing_value_policy"),
        "validation_rules": _bullets(tos.get("validation_rules")),
        # governance
        "contains_personal_data": dh.contains_personal_data,
        "output_sensitivity": dh.output_sensitivity,
        "audit_log_required": "yes" if dh.audit_log_required else "no",
        # composed blocks
        "components_block": _components_block(blueprint),
        "workflow_table": _workflow_table(blueprint),
        "artifacts_block": _artifacts_block(blueprint),
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_docs(blueprint: Blueprint, output_dir: str | Path) -> List[Path]:
    """Generate the five documents into ``<output_dir>/docs/``.

    Returns the list of written paths. Templates use ``string.Template`` with
    ``safe_substitute`` so an unexpected placeholder never raises -- but the
    test suite asserts no ``${...}`` remains for the standard variable set.
    """
    variables = _build_doc_variables(blueprint)
    docs_dir = Path(output_dir) / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)

    written: List[Path] = []
    for name in DOC_NAMES:
        tmpl_path = TEMPLATES_DIR / f"{name}.md.tmpl"
        content = string.Template(tmpl_path.read_text(encoding="utf-8")).safe_substitute(variables)
        out_path = docs_dir / f"{name}.md"
        out_path.write_text(content, encoding="utf-8")
        written.append(out_path)
    return written
