"""How the report writer, the curator and the reviewer receive source text.

Every source, every earlier section and the format reference reaches a model in
its own ``<source_material>`` block (:mod:`gaik.software_components.source_material`),
labelled with the file name or section the citations use, while the task, the
section instructions and the review goals stay outside the blocks. Shared by the
single-call path (``pipeline.py``) and the agentic path (``agentic/``), so neither
imports the other.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from gaik.software_components.source_material import SourceMaterial, clean_label

TRUNCATED_NOTE = "[... evidence truncated ...]"


@dataclass(frozen=True)
class EvidenceSource:
    """One source's text for a model call.

    ``label`` is the file name the citations use (never a path), ``heading`` the
    line shown before its block, e.g. ``Source 1: notes.txt (text)``.
    ``truncated`` marks the last source kept under ``max_evidence_chars``.
    """

    label: str
    heading: str
    text: str
    truncated: bool = False


Evidence = str | list[EvidenceSource]
"""The evidence of a call: a list of sources, or one text (for example a curated brief)."""


def render_evidence(blocks: SourceMaterial, evidence: Evidence, *, label: str = "evidence") -> str:
    """The evidence as one labelled block per source; a plain text is one block."""
    if isinstance(evidence, str):
        return blocks.wrap(evidence, label=label)
    parts: list[str] = []
    for source in evidence:
        parts.append(
            f"{clean_label(source.heading)}\n{blocks.wrap(source.text, label=source.label)}"
        )
        if source.truncated:
            parts.append(TRUNCATED_NOTE)
    return "\n\n".join(parts)


def render_sections(blocks: SourceMaterial, sections: Mapping[str, str]) -> str:
    """Finished sections, one block each, labelled with the mapping's key."""
    return "\n\n".join(blocks.wrap(text, label=title) for title, text in sections.items())


def source_list(filenames: list[str]) -> str:
    """The file names the citations may use, each cleaned to one line."""
    return ", ".join(clean_label(name) for name in filenames)
