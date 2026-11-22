"""Per-section LangGraph subgraph: evidence_loader -> [curator] -> draft_writer
-> reviewer.

Faithful to the Lotus section-writer shape, minus cross-section dependencies.
Each section is drafted independently from the (optionally curated) evidence and
then mandatorily reviewed/repaired by the diff editor.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from gaik.software_components.source_material import (
    SourceMaterial,
    with_source_material_instruction,
)

from .._material import EvidenceSource
from ..models import _slug, _strip_title_heading
from .prompts import SECTION_WRITER_SYSTEM_PROMPT, build_curation_prompt, build_section_user_prompt
from .reviewer import review_and_polish
from .state import SectionWriterState

# Characters a file name cannot hold on every platform, and "%" itself.
_NOT_IN_A_FILE_NAME = re.compile(r'[<>:"/\\|?*%\x00-\x1f]')


def _file_stem(section_id: str) -> str:
    """A section id as a file name.

    A character that cannot be in a file name is written as ``%XX``, so the file
    stays in its folder and two different ids never share a file. Empty for an
    id of spaces only; cut at 150 characters, which a file name can always hold.
    """
    name = _NOT_IN_A_FILE_NAME.sub(lambda match: f"%{ord(match.group()):02X}", section_id)
    return name.strip()[:150]


def _usage_of(response: Any) -> dict:
    usage = getattr(response, "usage", None)
    if isinstance(usage, dict):
        return {k: v for k, v in usage.items() if isinstance(v, int)}
    return {}


def _merge_usage(left: dict, right: dict) -> dict:
    out = dict(left or {})
    for k, v in (right or {}).items():
        if isinstance(v, int):
            out[k] = out.get(k, 0) + v
    return out


def create_section_writer_graph(
    *,
    writer_client,
    writer_kwargs: dict,
    reviewer_client,
    reviewer_kwargs: dict,
    curate_evidence: bool,
    polish: bool,
    reporter,
    written_files: list[Path] | None = None,
):
    """The per-section graph. Each curated brief saved under ``output_dir`` is added
    to ``written_files``, so the caller knows which files this run wrote."""
    from langgraph.graph import END, StateGraph

    def evidence_loader(state: SectionWriterState) -> dict:
        title = state["title"]
        warnings = list(state.get("revision_warnings", []))
        if state.get("sample_report_provided") and not state.get("has_sample"):
            warnings.append(
                f"No matching sample section found for '{title}'; using generic format."
            )
            reporter.emit(f"[{title}] no matching sample section -> generic format")
        deps_ctx = state.get("dependencies_context") or {}
        if deps_ctx:
            reporter.emit(f"[{title}] context: {len(deps_ctx)} dependency section(s)")
        reporter.emit(
            f"[{title}] evidence loaded -> {'curation' if curate_evidence else 'drafting'}"
        )
        return {"active_evidence": state["evidence_pack"], "revision_warnings": warnings}

    def curator(state: SectionWriterState) -> dict:
        title = state["title"]
        blocks = SourceMaterial()
        system, user = build_curation_prompt(
            blocks=blocks,
            title=title,
            instructions=state["instructions"],
            evidence=state["evidence_pack"],
            report_description=state.get("report_description"),
        )
        response = writer_client.chat(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            **writer_kwargs,
        )
        brief = blocks.strip_echo(response.text or "").strip()
        usage = _merge_usage(state.get("usage", {}), _usage_of(response))

        out_dir = state.get("output_dir")
        if out_dir and brief:
            curated_dir = Path(out_dir) / "evidence" / "curated_sections"
            curated_dir.mkdir(parents=True, exist_ok=True)
            name = _file_stem(state.get("section_id") or "") or _slug(title)
            brief_path = curated_dir / f"{name}.md"
            brief_path.write_text(brief, encoding="utf-8")
            if written_files is not None:
                written_files.append(brief_path)

        reporter.emit(f"[{title}] curated evidence -> drafting")
        # The brief repeats source text, so it reaches the writer and the reviewer
        # in its own block, like a source.
        curated = [
            EvidenceSource(
                "curated brief",
                f"Curated facts for {title}, each with the file name of its source",
                brief,
            )
        ]
        return {
            "curated_brief": brief,
            "active_evidence": curated if brief else state["evidence_pack"],
            "usage": usage,
        }

    def draft_writer(state: SectionWriterState) -> dict:
        title = state["title"]
        evidence = state.get("active_evidence") or state["evidence_pack"]
        blocks = SourceMaterial()
        user = build_section_user_prompt(
            blocks=blocks,
            title=title,
            instructions=state["instructions"],
            evidence=evidence,
            sample_section=state.get("sample_section", ""),
            has_sample=bool(state.get("has_sample")),
            report_description=state.get("report_description"),
            additional_instructions=state.get("additional_instructions"),
            source_filenames=list(state.get("source_filenames") or []),
            report_language=state.get("report_language"),
            include_source_references=bool(state.get("include_source_references", True)),
            dependencies_context=state.get("dependencies_context") or {},
        )
        response = writer_client.chat(
            [
                {
                    "role": "system",
                    "content": with_source_material_instruction(SECTION_WRITER_SYSTEM_PROMPT),
                },
                {"role": "user", "content": user},
            ],
            **writer_kwargs,
        )
        # Only an echoed section title goes; a first sub-heading is the section's own.
        draft = _strip_title_heading(blocks.strip_echo(response.text or "").strip(), title)
        usage = _merge_usage(state.get("usage", {}), _usage_of(response))
        reporter.emit(f"[{title}] draft written ({len(draft.split())} words) -> reviewer")
        return {"draft": draft, "usage": usage}

    def reviewer_node(state: SectionWriterState) -> dict:
        title = state["title"]
        evidence = state.get("active_evidence") or state["evidence_pack"]
        text, applied, warnings = review_and_polish(
            draft=state["draft"],
            evidence=evidence,
            title=title,
            instructions=state["instructions"],
            sample_section=state.get("sample_section", ""),
            has_sample=bool(state.get("has_sample")),
            include_source_references=bool(state.get("include_source_references", True)),
            report_description=state.get("report_description"),
            additional_instructions=state.get("additional_instructions"),
            dependencies_context=state.get("dependencies_context") or {},
            client=reviewer_client,
            chat_kwargs=reviewer_kwargs,
            polish=polish,
            reporter=reporter,
            label=title,
        )
        all_warnings = list(state.get("revision_warnings", [])) + warnings
        reporter.emit(f"[{title}] done")
        return {"draft": text, "applied_edits": applied, "revision_warnings": all_warnings}

    workflow = StateGraph(SectionWriterState)
    workflow.add_node("evidence_loader", evidence_loader)
    if curate_evidence:
        workflow.add_node("curator", curator)
    workflow.add_node("draft_writer", draft_writer)
    workflow.add_node("reviewer", reviewer_node)

    workflow.set_entry_point("evidence_loader")
    if curate_evidence:
        workflow.add_edge("evidence_loader", "curator")
        workflow.add_edge("curator", "draft_writer")
    else:
        workflow.add_edge("evidence_loader", "draft_writer")
    workflow.add_edge("draft_writer", "reviewer")
    workflow.add_edge("reviewer", END)

    return workflow.compile()
