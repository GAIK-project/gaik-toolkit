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
    transformation_chain,
)


# ---------------------------------------------------------------------------
# Registry loads and self-validates
# ---------------------------------------------------------------------------


def test_registry_loads_and_validates():
    reg = get_registry()
    assert len(reg.all()) == 10


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


def test_module_entry_has_uses_components():
    entry = module_for_pattern("audio_to_structured")
    assert "uses_components" in entry
    assert len(entry["uses_components"]) > 0
