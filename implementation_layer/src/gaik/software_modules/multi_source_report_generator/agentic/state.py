"""LangGraph state definitions for the agentic report workflow.

Generalized from the Lotus building-inspection tool's ``state_definitions``:
parallel section nodes write into one ``ReportState`` via merge reducers; each
section is drafted/reviewed inside its own ``SectionWriterState`` subgraph.
"""

from __future__ import annotations

from typing import Annotated, Any, TypedDict


def merge_dicts(left: dict | None, right: dict | None) -> dict:
    """Reducer for keys written concurrently by parallel section nodes."""
    out = dict(left or {})
    out.update(right or {})
    return out


class ReportState(TypedDict, total=False):
    # --- inputs (set once, read-only during the run) ---
    evidence_pack: str
    report_description: str | None
    # title -> matched sample-section markdown (or None when no match / no sample)
    matched_samples: dict[str, Any]
    sample_report_provided: bool
    report_language: str | None
    include_source_references: bool
    output_dir: str | None

    # --- outputs (written by parallel section nodes, merged) ---
    section_content: Annotated[dict[str, str], merge_dicts]
    section_warnings: Annotated[dict[str, list], merge_dicts]
    section_usage: Annotated[dict[str, dict], merge_dicts]


class SectionWriterState(TypedDict, total=False):
    index: int
    title: str
    instructions: str
    evidence_pack: str
    # The evidence the writer/reviewer actually use: the curated brief when
    # curation is on, otherwise the full evidence pack.
    active_evidence: str
    curated_brief: str
    sample_section: str
    has_sample: bool
    sample_report_provided: bool
    output_dir: str | None
    report_description: str | None
    report_language: str | None
    include_source_references: bool
    draft: str
    applied_edits: list
    revision_warnings: list
    usage: dict
