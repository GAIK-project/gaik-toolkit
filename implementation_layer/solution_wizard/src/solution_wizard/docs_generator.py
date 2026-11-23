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

import html
import re
import string
from pathlib import Path
from typing import Any, Dict, List

from .blueprint import Blueprint, external_services

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


_MD_SPECIAL = re.compile(r"([\\`*\[\]|!])")


def md_text(value: Any) -> str:
    """Blueprint text as Markdown shows it: one line, no markup, no raw HTML.

    The documents are generated from what users and the agent wrote; a viewer
    must show that text, not read it as headings, links, images, tables or
    HTML. Link, image, emphasis, code and table characters are escaped, and
    ``< > &`` become entities.
    """
    text = " ".join(str(value).split())
    text = _MD_SPECIAL.sub(r"\\\1", html.escape(text, quote=False))
    # A heading only starts a line; an underscore inside a word is plain text.
    return "\\" + text if text.startswith("#") else text


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _fmt_value(value: Any) -> str:
    if value is None or value == "":
        return "_not specified_"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, list):
        return ", ".join(md_text(v) for v in value) if value else "_none_"
    if isinstance(value, dict):
        if not value:
            return "_none_"
        return ", ".join(f"{md_text(k)}: {md_text(v)}" for k, v in value.items())
    return md_text(value)


def _bullets(value: Any) -> str:
    if isinstance(value, list):
        items = [md_text(v) for v in value if str(v).strip()]
    elif isinstance(value, dict):
        items = [f"**{md_text(k)}**: {md_text(v)}" for k, v in value.items()]
    elif value in (None, ""):
        items = []
    else:
        items = [md_text(value)]
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
        mid = md_text(getattr(m, "name", None) or getattr(m, "id", ""))
        reason = md_text(getattr(m, "reason", "") or "")
        lines.append(f"- **{mid}** (module){f' — {reason}' if reason else ''}")
    for b in comps.selected_building_blocks:
        lines.append(f"- **{md_text(b)}** (component)")
    for c in comps.custom_components:
        lines.append(f"- **{md_text(c)}** (custom)")
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
        comp = md_text(s.component) if s.component else "—"
        params = ""
        if s.parameters:
            params = " <br/>opts: " + ", ".join(
                f"{md_text(k)}={md_text(v)}" for k, v in s.parameters.items()
            )
        inputs = ", ".join(md_text(i) for i in s.inputs) or "—"
        outputs = ", ".join(md_text(o) for o in s.outputs) or "—"
        rows.append(
            f"| {md_text(s.id)} | {md_text(s.type)} | {comp}{params} | {inputs} | {outputs} |"
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
        lines.append(
            f"- {md_text(aid)} — {md_text(art.type)}, source: {md_text(art.source.value)}{suffix}"
        )
    return "\n".join(lines)


def external_services_block(blueprint: Blueprint) -> str:
    """One Markdown list item per external service, or "" when the blueprint has none.

    Used by the technical specification and by the PoC's README. The package and the
    variable names were checked by the blueprint model, so they go in code spans; the
    rest is text the user or the agent wrote.
    """
    items: list[str] = []
    for service in external_services(blueprint):
        lines = [f"- **{md_text(service.name)}**: {md_text(service.purpose)}"]
        if service.python_package:
            lines.append(f"  - Package: `{service.python_package}` (in `requirements.txt`)")
        keys = ", ".join(f"`{name}`" for name in service.env_vars)
        lines.append(f"  - Keys and settings in `.env`: {keys or '_none_'}")
        lines.append(f"  - Data sent to the service: {md_text(service.data_sent)}")
        lines.append(
            "  - Available: "
            + (
                "yes, the user provides the account and key"
                if service.user_can_provide
                else "not yet, an open item; the PoC runs without it"
            )
        )
        lines.append(f"  - Without it: {md_text(service.fallback)}")
        if service.docs_url:
            lines.append(f"  - Documentation: {md_text(service.docs_url)}")
        items.append("\n".join(lines))
    return "\n".join(items)


def _external_services_keys(blueprint: Blueprint) -> str:
    """The user guide's prerequisite line for the external services' keys."""
    services = external_services(blueprint)
    if not services:
        return "- External services: none."
    named = []
    for service in services:
        keys = ", ".join(f"`{name}`" for name in service.env_vars) or "no key"
        named.append(f"{keys} ({md_text(service.name)})")
    return (
        "- External services: set " + "; ".join(named) + " in `poc/.env`. Without a key "
        "the PoC skips that step, says so in its log, and runs the other steps."
    )


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

    fingerprint = blueprint.fingerprint()
    return {
        # identity
        "blueprint_line": (
            f"{md_text(fingerprint['blueprint_id'])}, version "
            f"{md_text(fingerprint['blueprint_version'])}, "
            f"SHA-256 {fingerprint['blueprint_sha256']}"
        ),
        "use_case_name": md_text(uc.name),
        "use_case_id": md_text(uc.id),
        "domain": md_text(uc.domain) if uc.domain else "_not specified_",
        "description": md_text(uc.description) if uc.description else "_not specified_",
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
        "external_services_block": external_services_block(blueprint)
        or "- _none: every step uses GAIK components_",
        "external_services_keys": _external_services_keys(blueprint),
        "human_review": _fmt_value(tspec.get("human_review", tspec.get("human_review_required"))),
        "evaluation_requirements": _fmt_value(tspec.get("evaluation_requirements")),
        "runtime_interface": _fmt_value(runtime),
        # Inside a ```bash block: one line, and no backtick that could end the block.
        "run_command": " ".join(str(run_cmd).split()).replace("`", "'"),
        # target output
        "schema_name": _field(tos, "schema_name"),
        "fields_list": _bullets(fields),
        "field_count": str(len(fields)),
        "required_fields": _fmt_value(tos.get("required_fields")),
        "missing_value_policy": _field(tos, "missing_value_policy"),
        "validation_rules": _bullets(tos.get("validation_rules")),
        # governance
        "contains_personal_data": md_text(dh.contains_personal_data),
        "output_sensitivity": md_text(dh.output_sensitivity),
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
