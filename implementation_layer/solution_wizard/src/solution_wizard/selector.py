"""Selection reference data -- transformation chains and the module-first map.

The agent (via SKILL.md) owns pattern classification and component selection.
It reads the registry fields (input_artifact_types, output_artifact_types,
best_for, known_limitations) and reasons from them directly -- there is no
deterministic classifier here.

This module provides two pieces of *reference data* the agent consults as
hints, not as gates:

  1. CHAINS / transformation_chain() -- the canonical ordered data states for
     each known pattern, so the agent structures workflows consistently.
  2. module_for_pattern() -- the module-first rule encoded as data: if a single
     GAIK module covers a pattern end-to-end, it is the preferred choice.

The agent may override either hint when the use case calls for it. Pattern
names below are conventions the agent uses in conversation; they are not a
fixed enum the agent must match exactly.

Adding a new component to the registry requires no changes here.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from .registry import Registry, get_registry


# ---------------------------------------------------------------------------
# Transformation chains per pattern
# Each entry is the ordered list of data states from input to final output.
# These are scaffolds the agent adapts -- not rigid templates.
# ---------------------------------------------------------------------------

CHAINS: Dict[str, List[str]] = {
    "audio_to_structured": [
        "audio_input",
        "raw_transcript",
        "enhanced_transcript",
        "structured_json",
        "validated_output",
        "final_output",
    ],
    "transcript_only": [
        "audio_input",
        "raw_transcript",
        "enhanced_transcript",
    ],
    "document_to_structured": [
        "document_input",
        "parsed_text",
        "structured_json",
        "validated_output",
        "final_output",
    ],
    "vision_extraction": [
        "image_input",
        "structured_json",
        "validated_output",
        "final_output",
    ],
    "rag": [
        "document_collection",
        "text_chunks",
        "vector_index",
        "retrieved_chunks",
        "answer_with_citations",
    ],
    "classification": [
        "document_input",
        "classification_result",
    ],
    # Several input kinds that belong to one case and must be processed
    # together (e.g. a meeting delivered as audio + agenda PDF + participant
    # JSON), ending in structured output. No single module covers this: the
    # per-kind modules take one input kind, and MultiSourceReportGenerator
    # writes a narrative report rather than a structured record. So this chain
    # is a compose-from-components scaffold.
    "multi_source_to_structured": [
        "mixed_input",
        "normalized_evidence",
        "structured_json",
        "validated_output",
        "final_output",
    ],
    "multi_source_report": [
        "source_files",
        "normalized_evidence",
        "report_sections",
        "markdown_report",
        "final_output",
    ],
    "hybrid": [
        "mixed_input",
        "intermediate_output",
        "structured_output",
    ],
}

# Maps each pattern to the single GAIK module that covers it end-to-end,
# where one exists. This is the module-first rule encoded as data.
_PATTERN_TO_MODULE: Dict[str, str] = {
    "audio_to_structured": "audio_to_structured_data",
    "document_to_structured": "documents_to_structured_data",
    "rag": "rag_workflow",
    "multi_source_report": "multi_source_report_generator",
}


def modules_covering_inputs(
    input_types: List[str],
    output_types: Optional[List[str]] = None,
    registry: Optional[Registry] = None,
) -> List[Dict]:
    """Registry modules that can read **every** given input type.

    Pass ``output_types`` to also require the shape the case needs, which is the
    other half of the module-first rule.

    The module-first rule is only safe when the module can actually read all of
    the case's inputs. A case delivered as audio + PDF + JSON has no such
    module: each per-kind module takes one kind, and the one module that reads
    a mix (MultiSourceReportGenerator) writes a narrative report instead of a
    structured record. An empty list therefore means "compose from components",
    not "no match, pick the closest" — picking the closest silently drops the
    inputs it cannot read, which is how a three-source meeting case ends up
    classified as audio-only (#141 follow-up).
    """
    reg = registry or get_registry()
    wanted = {t.strip().lower() for t in input_types if t and t.strip()}
    if not wanted:
        return []
    produces = {t.strip().lower() for t in (output_types or []) if t and t.strip()}
    out: List[Dict] = []
    for entry in reg.modules():
        covered = {t.lower() for t in entry.get("input_artifact_types", [])}
        if not wanted <= covered:
            continue
        if produces:
            emitted = {t.lower() for t in entry.get("output_artifact_types", [])}
            if not produces & emitted:
                continue
        out.append(entry)
    return out


def transformation_chain(pattern: str) -> List[str]:
    """Return the canonical ordered data states for a pattern (a hint).

    Falls back to the generic 'hybrid' chain for unknown patterns.
    """
    return CHAINS.get(pattern, CHAINS["hybrid"])


def module_for_pattern(pattern: str, registry: Optional[Registry] = None) -> Optional[Dict]:
    """Return the registry entry for the module that covers this pattern, or None.

    None means no single module covers the pattern end-to-end, so the agent
    should compose a pipeline from individual components.
    """
    module_id = _PATTERN_TO_MODULE.get(pattern)
    if not module_id:
        return None
    if registry is None:
        registry = get_registry()
    return registry.lookup_by_id(module_id)
