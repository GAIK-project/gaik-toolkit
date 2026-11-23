"""Tests for selection reference data (WP4).

Pattern classification is owned by the agent (SKILL.md), not by this module.
These tests cover only the reference data the agent consults: transformation
chains and the module-first map.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pytest
from solution_wizard.registry import _validate_entries, get_registry
from solution_wizard.selector import (
    CHAINS,
    module_for_pattern,
    modules_covering_inputs,
    transformation_chain,
)

# ---------------------------------------------------------------------------
# Registry loads and self-validates
# ---------------------------------------------------------------------------


def test_registry_loads_and_validates():
    reg = get_registry()
    # Floor rather than an exact count: entries are added by gaik-sync as gaik
    # grows, and an exact assertion turns every legitimate addition into a
    # failure. The floor still catches a truncated or half-written registry.
    assert len(reg.all()) >= 30


def test_registry_validation_catches_missing_keys():
    with pytest.raises(ValueError):
        _validate_entries([{"id": "x", "name": "X", "type": "software_component"}])


def test_registry_validation_catches_bad_type():
    entry = {
        "id": "x",
        "name": "X",
        "type": "widget",
        "input_artifact_types": [],
        "output_artifact_types": [],
        "required_parameters": [],
        "best_for": [],
        "known_limitations": [],
        "import_path": "",
        "source_path": "",
        "readme_path": "",
        "example_script_path": "",
    }
    with pytest.raises(ValueError):
        _validate_entries([entry])


# ---------------------------------------------------------------------------
# Transformation chains
# ---------------------------------------------------------------------------


def test_chain_audio_to_structured_non_empty():
    chain = transformation_chain("audio_to_structured")
    assert len(chain) > 0
    assert chain[0] == "audio_input"
    assert chain[-1] == "final_output"


def test_chain_rag_non_empty():
    chain = transformation_chain("rag")
    assert "document_collection" in chain
    assert "answer_with_citations" in chain


def test_chain_document_to_structured():
    chain = transformation_chain("document_to_structured")
    assert chain[0] == "document_input"
    assert "structured_json" in chain


def test_chain_unknown_pattern_returns_hybrid():
    chain = transformation_chain("nonexistent_pattern")
    assert chain == CHAINS["hybrid"]


def test_all_chains_non_empty():
    for pattern, chain in CHAINS.items():
        assert len(chain) >= 2, f"Chain '{pattern}' is too short"


# ---------------------------------------------------------------------------
# Module-first rule
# ---------------------------------------------------------------------------


def test_module_for_audio_to_structured():
    entry = module_for_pattern("audio_to_structured")
    assert entry is not None
    assert entry["name"] == "AudioToStructuredData"
    assert entry["type"] == "software_module"


def test_module_for_document_to_structured():
    entry = module_for_pattern("document_to_structured")
    assert entry is not None
    assert entry["name"] == "DocumentsToStructuredData"


def test_module_for_rag():
    entry = module_for_pattern("rag")
    assert entry is not None
    assert entry["name"] == "RAGWorkflow"


def test_no_module_for_vision_extraction():
    # No single module covers vision extraction -- composed from components
    assert module_for_pattern("vision_extraction") is None


def test_no_module_for_classification():
    assert module_for_pattern("classification") is None


def test_no_module_for_hybrid():
    assert module_for_pattern("hybrid") is None


# ---------------------------------------------------------------------------
# Registry fields used for agent-driven selection
# ---------------------------------------------------------------------------


def test_module_entry_has_required_llm_fields():
    """The fields the agent needs to reason about selection are present."""
    entry = module_for_pattern("audio_to_structured")
    for field in ("input_artifact_types", "output_artifact_types", "best_for", "known_limitations"):
        assert field in entry, f"Missing field: {field}"


def test_audio_module_declares_the_transcript_it_returns():
    """#145 — the entry declared only structured_json, so Rule 4 rejected any
    workflow handing the reviewer both the extracted record and the transcript
    it came from. AudioToStructuredData returns PipelineResult.transcription
    alongside extracted_fields; the registry has to say so."""
    entry = module_for_pattern("audio_to_structured")
    outputs = {t.lower() for t in entry["output_artifact_types"]}
    assert "structured_json" in outputs
    assert "transcript" in outputs
    assert "enhanced_transcript" in outputs


def test_module_entry_has_uses_components():
    entry = module_for_pattern("audio_to_structured")
    assert "uses_components" in entry
    assert len(entry["uses_components"]) > 0


# ---------------------------------------------------------------------------
# Multi-source cases: the module-first rule has to read every input
# ---------------------------------------------------------------------------


def test_multi_source_chain_ends_in_structured_output():
    chain = transformation_chain("multi_source_to_structured")
    assert chain[0] == "mixed_input"
    assert "structured_json" in chain
    assert chain[-1] == "final_output"


def test_no_single_module_covers_a_mixed_source_case():
    """A meeting delivered as audio + agenda PDF + participant JSON.

    The per-kind modules read one kind each, and the one module that reads a
    mix (MultiSourceReportGenerator) writes a narrative report, so it is not a
    match for a structured record. An empty list is the signal to compose.
    """
    # The inputs alone are covered — by the two report writers (gaik 0.8.2
    # added report_writer next to the legacy generator) — but nothing covers
    # them *and* produces a structured record.
    assert {m["id"] for m in modules_covering_inputs(["audio", "pdf", "text"])} == {
        "multi_source_report_generator",
        "report_writer",
    }
    assert modules_covering_inputs(["audio", "pdf", "text"], ["structured_json"]) == []
    assert module_for_pattern("multi_source_to_structured") is None


def test_audio_only_module_is_not_offered_for_a_mixed_case():
    """The misclassification this guards against: picking the audio module for
    a case that also has a PDF silently drops the PDF."""
    audio_only = modules_covering_inputs(["audio"])
    assert "audio_to_structured_data" in {m["id"] for m in audio_only}
    assert "audio_to_structured_data" not in {
        m["id"] for m in modules_covering_inputs(["audio", "pdf"])
    }


def test_the_mixed_reader_is_found_when_prose_output_is_wanted():
    """The report writers do read the whole mix — it is the output shape, not
    the inputs, that rules them out for structured records. ReportWriter is
    the default since gaik 0.8.2; the legacy generator stays selectable."""
    ids = {m["id"] for m in modules_covering_inputs(["audio", "pdf", "image"])}
    assert ids == {"multi_source_report_generator", "report_writer"}
    for module_id in ids:
        entry = get_registry().lookup_by_id(module_id)
        assert "structured_json" not in entry["output_artifact_types"], module_id


def test_input_coverage_is_case_insensitive_and_ignores_blanks():
    assert modules_covering_inputs([]) == []
    ids = {m["id"] for m in modules_covering_inputs([" PDF ", "docx"])}
    assert "documents_to_structured_data" in ids
