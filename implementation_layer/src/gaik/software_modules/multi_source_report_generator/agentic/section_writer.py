"""Per-section LangGraph subgraph: evidence_loader -> [curator] -> draft_writer
-> reviewer.

Faithful to the Lotus section-writer shape, minus cross-section dependencies.
Each section is drafted independently from the (optionally curated) evidence and
then mandatorily reviewed/repaired by the diff editor.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .prompts import SECTION_WRITER_SYSTEM_PROMPT, build_curation_prompt, build_section_user_prompt
from .reviewer import review_and_polish
from .state import SectionWriterState


def _slug(text: str, *, max_len: int = 40) -> str:
    keep = [c.lower() if c.isalnum() else "_" for c in text.strip()]
    s = "".join(keep)
    while "__" in s:
        s = s.replace("__", "_")
    return s.strip("_")[:max_len] or "section"


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


def _strip_leading_heading(text: str) -> str:
    """Drop a leading markdown heading line if the model emitted one anyway."""
    stripped = text.lstrip()
    if stripped.startswith("#"):
        lines = stripped.splitlines()
        return "\n".join(lines[1:]).lstrip()
    return text


def create_section_writer_graph(
    *,
    writer_client,
    writer_kwargs: dict,
    reviewer_client,
    reviewer_kwargs: dict,
    curate_evidence: bool,
    polish: bool,
    reporter,
):
    from langgraph.graph import END, StateGraph

    def evidence_loader(state: SectionWriterState) -> dict:
        title = state["title"]
        warnings = list(state.get("revision_warnings", []))
        if state.get("sample_report_provided") and not state.get("has_sample"):
            warnings.append(
                f"No matching sample section found for '{title}'; using generic format."
            )
            reporter.emit(f"[{title}] no matching sample section -> generic format")
        reporter.emit(
            f"[{title}] evidence loaded -> {'curation' if curate_evidence else 'drafting'}"
        )
        return {"active_evidence": state["evidence_pack"], "revision_warnings": warnings}

    def curator(state: SectionWriterState) -> dict:
        title = state["title"]
        system, user = build_curation_prompt(
            title=title,
            instructions=state["instructions"],
            evidence=state["evidence_pack"],
            report_description=state.get("report_description"),
        )
        response = writer_client.chat(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            **writer_kwargs,
        )
        brief = (response.text or "").strip()
        usage = _merge_usage(state.get("usage", {}), _usage_of(response))

        out_dir = state.get("output_dir")
        if out_dir and brief:
            curated_dir = Path(out_dir) / "evidence" / "curated_sections"
            curated_dir.mkdir(parents=True, exist_ok=True)
            (curated_dir / f"{_slug(title)}.md").write_text(brief, encoding="utf-8")

        reporter.emit(f"[{title}] curated evidence -> drafting")
        return {
            "curated_brief": brief,
            "active_evidence": brief or state["evidence_pack"],
            "usage": usage,
        }

    def draft_writer(state: SectionWriterState) -> dict:
        title = state["title"]
        evidence = state.get("active_evidence") or state["evidence_pack"]
        user = build_section_user_prompt(
            title=title,
            instructions=state["instructions"],
            evidence=evidence,
            sample_section=state.get("sample_section", ""),
            has_sample=bool(state.get("has_sample")),
            report_description=state.get("report_description"),
            report_language=state.get("report_language"),
            include_source_references=bool(state.get("include_source_references", True)),
        )
        response = writer_client.chat(
            [
                {"role": "system", "content": SECTION_WRITER_SYSTEM_PROMPT},
                {"role": "user", "content": user},
            ],
            **writer_kwargs,
        )
        draft = _strip_leading_heading((response.text or "").strip())
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
