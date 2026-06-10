"""Parallel section orchestrator for the agentic report workflow.

Builds a LangGraph that fans out one node per user-defined section (all from
START, joining at END) — sections are written independently and in parallel.
Each node invokes the per-section subgraph and merges its output into the shared
``ReportState``. The report is assembled in the user's original section order.
"""

from __future__ import annotations

from ..models import GeneratedSection, ReportSectionSpec
from .section_writer import _merge_usage, create_section_writer_graph
from .state import ReportState

_LANGGRAPH_HINT = (
    "The agentic report workflow requires 'langgraph'. Install it with:\n"
    '    pip install "gaik[multi-source-report-generator-agentic]"'
)


def _require_langgraph() -> None:
    try:
        import langgraph.graph  # noqa: F401
    except ImportError as exc:  # pragma: no cover - exercised only without langgraph
        raise ImportError(_LANGGRAPH_HINT) from exc


def _make_section_runner(index: int, spec: ReportSectionSpec, section_graph):
    def runner(state: ReportState) -> dict:
        matched = (state.get("matched_samples") or {}).get(spec.title)
        section_state = {
            "index": index,
            "title": spec.title,
            "instructions": spec.instructions,
            "evidence_pack": state["evidence_pack"],
            "active_evidence": state["evidence_pack"],
            "curated_brief": "",
            "sample_section": matched or "",
            "has_sample": matched is not None,
            "sample_report_provided": bool(state.get("sample_report_provided")),
            "output_dir": state.get("output_dir"),
            "report_description": state.get("report_description"),
            "report_language": state.get("report_language"),
            "include_source_references": bool(state.get("include_source_references", True)),
            "draft": "",
            "applied_edits": [],
            "revision_warnings": [],
            "usage": {},
        }
        result = section_graph.invoke(section_state)
        return {
            "section_content": {str(index): (result.get("draft") or "").strip()},
            "section_warnings": {str(index): list(result.get("revision_warnings", []))},
            "section_usage": {str(index): result.get("usage", {})},
        }

    return runner


def build_orchestrator_graph(specs: list[ReportSectionSpec], section_graph):
    _require_langgraph()
    from langgraph.graph import END, START, StateGraph

    graph = StateGraph(ReportState)
    for index, spec in enumerate(specs):
        node = f"sec_{index}"
        graph.add_node(node, _make_section_runner(index, spec, section_graph))
        graph.add_edge(START, node)
        graph.add_edge(node, END)
    return graph.compile()


def run_agentic_report(
    *,
    specs: list[ReportSectionSpec],
    evidence_items: list,
    evidence_pack: str,
    matched_samples: dict,
    sample_report_provided: bool,
    output_dir,
    report_title: str,
    report_description: str | None,
    report_language: str | None,
    include_source_references: bool,
    writer_client,
    writer_kwargs: dict,
    reviewer_client,
    reviewer_kwargs: dict,
    curate_evidence: bool,
    polish: bool,
    strict_review: bool,
    reporter,
) -> tuple[str, list[GeneratedSection], dict]:
    """Run sections in parallel, review each, and assemble the report.

    Returns ``(markdown, generated_sections, usage)``. When ``strict_review`` is
    True and any section has unresolved reviewer edits, raises **before** the
    caller writes the final report outputs.
    """
    _require_langgraph()

    section_graph = create_section_writer_graph(
        writer_client=writer_client,
        writer_kwargs=writer_kwargs,
        reviewer_client=reviewer_client,
        reviewer_kwargs=reviewer_kwargs,
        curate_evidence=curate_evidence,
        polish=polish,
        reporter=reporter,
    )

    titles = ", ".join(spec.title for spec in specs)
    reporter.emit(f"Writing {len(specs)} section(s) in parallel: {titles}")

    graph = build_orchestrator_graph(specs, section_graph)
    initial: ReportState = {
        "evidence_pack": evidence_pack,
        "report_description": report_description,
        "matched_samples": matched_samples,
        "sample_report_provided": sample_report_provided,
        "report_language": report_language,
        "include_source_references": include_source_references,
        "output_dir": str(output_dir) if output_dir is not None else None,
        "section_content": {},
        "section_warnings": {},
        "section_usage": {},
    }
    result = graph.invoke(initial)

    section_content = result.get("section_content", {})
    section_warnings = result.get("section_warnings", {})
    section_usage = result.get("section_usage", {})

    # strict_review gate — raise BEFORE the caller writes final report outputs.
    # Only unresolved reviewer edits count; informational warnings (e.g. "no
    # matching sample section") do not trigger this gate.
    if strict_review:
        unresolved = {
            k: [w for w in ws if w.startswith("Unresolved reviewer edit")]
            for k, ws in section_warnings.items()
        }
        unresolved = {k: ws for k, ws in unresolved.items() if ws}
        if unresolved:
            details = "; ".join(
                f"'{specs[int(k)].title}': {len(ws)} unresolved"
                for k, ws in sorted(unresolved.items())
            )
            raise RuntimeError(
                "strict_review=True: unresolved reviewer edits remain "
                f"({details}). No report outputs were written."
            )

    body_parts = [f"# {report_title}"]
    generated: list[GeneratedSection] = []
    total_usage: dict = {}
    for index, spec in enumerate(specs):
        key = str(index)
        body = (section_content.get(key) or "").strip()
        warnings = list(section_warnings.get(key, []))
        usage = section_usage.get(key, {})
        total_usage = _merge_usage(total_usage, usage)
        body_parts.append(f"## {spec.title}\n\n{body}")
        generated.append(
            GeneratedSection(
                title=spec.title,
                content_markdown=body,
                usage=usage or None,
                revision_warnings=warnings,
            )
        )

    reporter.emit("Assembling report in requested order -> report.md")
    markdown = "\n\n".join(body_parts).strip() + "\n"
    return markdown, generated, total_usage
