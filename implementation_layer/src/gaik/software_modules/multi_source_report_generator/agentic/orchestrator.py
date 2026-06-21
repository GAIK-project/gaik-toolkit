"""Section orchestrator for the agentic report workflow.

Sections are written in dependency-ordered **layers**. Sections with no
dependencies form layer 0 and run in parallel; each subsequent layer runs after
the previous one completes (a join barrier), so a dependent section receives the
finalized (reviewed + polished) content of its dependencies as context.

With no ``depends_on`` anywhere this collapses to a single layer —
``START → all sections (parallel) → END`` — i.e. the original behavior.

The report is always assembled in the user's original section order.
"""

from __future__ import annotations

import re

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


def build_phases(specs: list[ReportSectionSpec]) -> list[list[ReportSectionSpec]]:
    """Topologically levelize sections into dependency layers (Kahn).

    Layer 0 = sections with no dependencies; each later layer = sections whose
    dependencies are all in earlier layers. Order within a layer follows the
    user's original section order. Raises ``ValueError`` on a dependency cycle.
    """
    by_id = {spec.id: spec for spec in specs}
    remaining = {spec.id: len(spec.depends_on) for spec in specs}
    dependents: dict[str, list[str]] = {spec.id: [] for spec in specs}
    for spec in specs:
        for dep in spec.depends_on:
            dependents[dep].append(spec.id)

    phases: list[list[ReportSectionSpec]] = []
    placed: set[str] = set()
    while len(placed) < len(specs):
        layer_ids = [s.id for s in specs if s.id not in placed and remaining[s.id] == 0]
        if not layer_ids:
            cyclic = sorted(s.id for s in specs if s.id not in placed)
            raise ValueError(f"Cyclic section dependencies among: {cyclic}")
        phases.append([by_id[i] for i in layer_ids])
        for i in layer_ids:
            placed.add(i)
            for child in dependents[i]:
                remaining[child] -= 1
    return phases


def _make_section_runner(spec: ReportSectionSpec, section_graph, id_to_title: dict[str, str]):
    def runner(state: ReportState) -> dict:
        matched = (state.get("matched_samples") or {}).get(spec.title)

        # Resolve this section's dependency context from the finalized content
        # of completed layers (available because of the join barrier).
        section_content = state.get("section_content", {})
        dep_blocks = []
        for dep in spec.depends_on:
            content = (section_content.get(dep) or "").strip()
            if content:
                dep_blocks.append(f"## {id_to_title.get(dep, dep)}\n\n{content}")
        dependencies_context = "\n\n".join(dep_blocks)

        section_state = {
            "section_id": spec.id,
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
            "additional_instructions": state.get("additional_instructions"),
            "source_filenames": list(state.get("source_filenames") or []),
            "report_language": state.get("report_language"),
            "include_source_references": bool(state.get("include_source_references", True)),
            "dependencies_context": dependencies_context,
            "draft": "",
            "applied_edits": [],
            "revision_warnings": [],
            "usage": {},
        }
        result = section_graph.invoke(section_state)
        return {
            "section_content": {spec.id: (result.get("draft") or "").strip()},
            "section_warnings": {spec.id: list(result.get("revision_warnings", []))},
            "section_usage": {spec.id: result.get("usage", {})},
        }

    return runner


def _make_join_node(
    reporter, completed_layer: int, next_layer: list[ReportSectionSpec], total: int
):
    def join(state: ReportState) -> dict:
        reporter.emit(
            f"Phase {completed_layer + 1}/{total} complete -> Phase {completed_layer + 2}"
        )
        titles = ", ".join(s.title for s in next_layer)
        reporter.emit(
            f"Phase {completed_layer + 2}/{total} — writing {len(next_layer)} "
            f"section(s) in parallel: {titles}"
        )
        return {}

    return join


def build_orchestrator_graph(
    phases: list[list[ReportSectionSpec]],
    section_graph,
    id_to_title: dict[str, str],
    reporter,
):
    _require_langgraph()
    from langgraph.graph import END, START, StateGraph

    graph = StateGraph(ReportState)
    for layer in phases:
        for spec in layer:
            graph.add_node(f"sec_{spec.id}", _make_section_runner(spec, section_graph, id_to_title))

    # Single layer: identical to the original parallel fan-out (no barriers).
    if len(phases) == 1:
        for spec in phases[0]:
            graph.add_edge(START, f"sec_{spec.id}")
            graph.add_edge(f"sec_{spec.id}", END)
        return graph.compile()

    total = len(phases)
    for j in range(total - 1):
        graph.add_node(f"join_{j}", _make_join_node(reporter, j, phases[j + 1], total))

    for spec in phases[0]:
        graph.add_edge(START, f"sec_{spec.id}")
        graph.add_edge(f"sec_{spec.id}", "join_0")

    for li in range(1, total):
        join_in = f"join_{li - 1}"
        for spec in phases[li]:
            graph.add_edge(join_in, f"sec_{spec.id}")
            if li < total - 1:
                graph.add_edge(f"sec_{spec.id}", f"join_{li}")
            else:
                graph.add_edge(f"sec_{spec.id}", END)
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
    additional_instructions: str | None = None,
    report_language: str | None,
    include_source_references: bool,
    source_filenames: list,
    writer_client,
    writer_kwargs: dict,
    reviewer_client,
    reviewer_kwargs: dict,
    curate_evidence: bool,
    polish: bool,
    strict_review: bool,
    reporter,
) -> tuple[str, list[GeneratedSection], dict]:
    """Run sections in dependency layers, review each, and assemble the report.

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

    phases = build_phases(specs)
    id_to_title = {spec.id: spec.title for spec in specs}

    if len(phases) == 1:
        titles = ", ".join(spec.title for spec in specs)
        reporter.emit(f"Writing {len(specs)} section(s) in parallel: {titles}")
    else:
        first = ", ".join(spec.title for spec in phases[0])
        reporter.emit(
            f"Phase 1/{len(phases)} — writing {len(phases[0])} section(s) in parallel: {first}"
        )

    graph = build_orchestrator_graph(phases, section_graph, id_to_title, reporter)
    initial: ReportState = {
        "evidence_pack": evidence_pack,
        "source_filenames": source_filenames,
        "report_description": report_description,
        "additional_instructions": additional_instructions,
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
            sid: [w for w in ws if w.startswith("Unresolved reviewer edit")]
            for sid, ws in section_warnings.items()
        }
        unresolved = {sid: ws for sid, ws in unresolved.items() if ws}
        if unresolved:
            details = "; ".join(
                f"'{id_to_title.get(sid, sid)}': {len(ws)} unresolved"
                for sid, ws in sorted(unresolved.items())
            )
            raise RuntimeError(
                "strict_review=True: unresolved reviewer edits remain "
                f"({details}). No report outputs were written."
            )

    body_parts = [f"# {report_title}"]
    generated: list[GeneratedSection] = []
    total_usage: dict = {}
    for spec in specs:
        body = (section_content.get(spec.id) or "").strip()
        # Strip any leading heading the LLM echoed despite being told not to,
        # so the orchestrator-added "## title" below is never duplicated.
        body = re.sub(r"^#{1,6}\s+.*\n*", "", body, count=1).strip()
        warnings = list(section_warnings.get(spec.id, []))
        usage = section_usage.get(spec.id, {})
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
