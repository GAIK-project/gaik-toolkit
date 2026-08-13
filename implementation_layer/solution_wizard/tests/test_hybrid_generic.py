"""Tests for the enhanced _generic template + pattern key + dynamic discovery (Parts 1b-1d, 2a-2b)."""

import ast
import json
import string
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from solution_wizard.blueprint import Blueprint
from solution_wizard.scaffolder import (
    _build_variables,
    _derive_pattern_key,
    _determine_pattern,
    scaffold_poc,
)

TEMPLATES_DIR = Path(__file__).parent.parent / "templates" / "poc"


def _hybrid_blueprint() -> Blueprint:
    """audio + document -> combine -> extract -> judge (no single module covers this)."""
    data = {
        "blueprint_version": "1.0",
        "use_case": {
            "id": "hybrid_uc",
            "name": "Hybrid UC",
            "description": "audio+doc->extract",
            "domain": "test",
        },
        "technical_spec": {
            "input_types": ["audio", "pdf"],
            "output_types": ["structured_json"],
            "language": "en",
        },
        "target_output_spec": {
            "schema_name": "HybridOut",
            "fields": ["field_alpha", "field_beta"],
            "required_fields": ["field_alpha"],
        },
        "components": {
            "selected_modules": [],
            "selected_building_blocks": [
                "Transcriber",
                "MultimodalParser",
                "Extractor",
                "LLMJudge",
            ],
            "custom_components": [],
        },
        "artifacts": {
            "src_audio": {"type": "audio", "source": "user_upload", "optional": False},
            "src_pdf": {"type": "pdf", "source": "user_upload", "optional": False},
            "transcript": {
                "type": "transcript",
                "source": "generated",
                "optional": False,
                "produced_by": "transcribe",
            },
            "parsed_text": {
                "type": "parsed_text",
                "source": "generated",
                "optional": False,
                "produced_by": "parse",
            },
            "structured_output": {
                "type": "structured_json",
                "source": "generated",
                "optional": False,
                "final_output": True,
                "produced_by": "extract",
            },
        },
        "workflow": {
            "steps": [
                {
                    "id": "rec_audio",
                    "name": "Record",
                    "type": "user_task",
                    "inputs": [],
                    "outputs": ["src_audio"],
                },
                {
                    "id": "upload_pdf",
                    "name": "Upload",
                    "type": "user_task",
                    "inputs": [],
                    "outputs": ["src_pdf"],
                },
                {
                    "id": "transcribe",
                    "name": "Transcribe",
                    "type": "automated_task",
                    "component": "Transcriber",
                    "inputs": ["src_audio"],
                    "outputs": ["transcript"],
                    "depends_on": ["rec_audio"],
                },
                {
                    "id": "parse",
                    "name": "Parse",
                    "type": "automated_task",
                    "component": "MultimodalParser",
                    "inputs": ["src_pdf"],
                    "outputs": ["parsed_text"],
                    "depends_on": ["upload_pdf"],
                },
                {
                    "id": "extract",
                    "name": "Extract",
                    "type": "automated_task",
                    "component": "Extractor",
                    "inputs": ["transcript", "parsed_text"],
                    "outputs": ["structured_output"],
                    "depends_on": ["transcribe", "parse"],
                },
                {
                    "id": "validate",
                    "name": "Validate",
                    "type": "automated_task",
                    "component": "LLMJudge",
                    "inputs": ["structured_output"],
                    "outputs": ["structured_output"],
                    "depends_on": ["extract"],
                },
            ]
        },
    }
    return Blueprint.model_validate(data)


# ---------------------------------------------------------------------------
# Pattern key
# ---------------------------------------------------------------------------


def test_hybrid_falls_to_generic():
    assert _determine_pattern(_hybrid_blueprint()) == "_generic"


def test_pattern_key_is_stable_and_directory_safe():
    bp = _hybrid_blueprint()
    k1 = _derive_pattern_key(bp)
    k2 = _derive_pattern_key(bp)
    assert k1 == k2
    assert k1.startswith("hybrid_")
    assert all(c.isalnum() or c == "_" for c in k1)


def test_pattern_key_excludes_llm_judge_from_name():
    key = _derive_pattern_key(_hybrid_blueprint())
    assert "llmjudge" not in key.lower()


def test_pattern_key_differs_for_different_topology():
    bp1 = _hybrid_blueprint()
    bp2 = _hybrid_blueprint()
    # Remove the parse step -> different shape -> different key
    bp2.workflow.steps = [s for s in bp2.workflow.steps if s.id != "parse"]
    assert _derive_pattern_key(bp1) != _derive_pattern_key(bp2)


# ---------------------------------------------------------------------------
# Generic template fills + parses
# ---------------------------------------------------------------------------


def test_generic_template_fills_and_parses():
    bp = _hybrid_blueprint()
    variables = _build_variables(bp, "_generic")
    tmpl = (TEMPLATES_DIR / "_generic" / "run_poc.py.tmpl").read_text()
    filled = string.Template(tmpl).safe_substitute(variables)
    ast.parse(filled)  # must be valid Python


def test_generic_skeleton_has_per_step_blocks_with_cards():
    variables = _build_variables(_hybrid_blueprint(), "_generic")
    skeleton = variables["generic_pipeline_skeleton"]
    assert "Step: transcribe  (Transcriber)" in skeleton
    assert "Step: parse  (MultimodalParser)" in skeleton
    assert "Step: extract  (Extractor)" in skeleton
    # Reference call patterns present
    assert "Reference call pattern:" in skeleton
    assert "from gaik.software_components.transcriber import" in skeleton
    # Output variables pre-declared with blueprint artifact names
    assert "transcript = None" in skeleton
    assert "parsed_text = None" in skeleton


def test_generic_input_loaders_per_upload_artifact():
    variables = _build_variables(_hybrid_blueprint(), "_generic")
    loaders = variables["generic_input_loaders"]
    assert "src_audio_path" in loaders
    assert "src_pdf_path" in loaders


def test_generic_judge_uses_contract_variables_not_result():
    variables = _build_variables(_hybrid_blueprint(), "_generic")
    judge = variables["llm_judge_section_generic"]
    assert "extracted_fields" in judge
    assert "source_text" in judge
    # Must NOT reference the module-only result object
    assert "result.transcription" not in judge
    assert "result.parsed_documents" not in judge


def test_scaffold_hybrid_endtoend(tmp_path):
    bp = _hybrid_blueprint()
    info = scaffold_poc(bp, tmp_path)
    assert info["pattern"] == "_generic"
    assert info["template_wired"] is False
    assert info["pattern_key"].startswith("hybrid_")
    assert "template_save_path" in info
    # run_poc.py is valid Python
    run_poc = (info["poc_dir"] / "run_poc.py").read_text()
    ast.parse(run_poc)
    # Contract variables present
    assert "extracted_fields = None" in run_poc
    assert "source_text" in run_poc


# ---------------------------------------------------------------------------
# Card-only components (wireable via a reference card, absent from the registry)
# ---------------------------------------------------------------------------

_CARD_ONLY_NAME = "FictionalCardOnlyParser"
_CARD_ONLY_EXTRA = "fictional-parser"
_CARD_ONLY_CARD = {
    "import": "from gaik.software_components.fictional import FictionalCardOnlyParser",
    "construct": "parser = FictionalCardOnlyParser()",
    "call": "parsed_text = parser.parse(str(input_path))",
    "returns": "str (markdown)",
    "install_extra": _CARD_ONLY_EXTRA,
}


@pytest.fixture
def card_only_component(tmp_path, monkeypatch):
    """Expose a synthetic component that has a reference card but no registry entry.

    These tests must exercise the card-only code path itself, not whichever real
    component happens to be unregistered today. Naming a real one couples the
    test to a registry that gaik-sync keeps editing: both of these tests used
    MultimodalParser, and when it gained a registry entry they kept passing while
    silently resolving through the registry and testing nothing. The assert below
    is the guard -- if this name is ever added to the registry, the fixture fails
    loudly instead of the tests going vacuous again.
    """
    from solution_wizard import registry as registry_mod

    cards_path = tmp_path / "cards.json"
    cards_path.write_text(json.dumps({_CARD_ONLY_NAME: _CARD_ONLY_CARD}), encoding="utf-8")
    cards = registry_mod.ReferenceCards(cards_path)
    monkeypatch.setattr(registry_mod, "get_reference_cards", lambda: cards)

    assert not registry_mod.get_registry().exists(_CARD_ONLY_NAME), (
        f"{_CARD_ONLY_NAME} must stay out of the registry for these tests to mean anything"
    )
    return _CARD_ONLY_NAME


def _blueprint_with_parser(component_name: str) -> Blueprint:
    """The hybrid blueprint with its parse step rewired to `component_name`."""
    bp = _hybrid_blueprint()
    bp.components.selected_building_blocks = [
        component_name if b == "MultimodalParser" else b
        for b in bp.components.selected_building_blocks
    ]
    next(s for s in bp.workflow.steps if s.id == "parse").component = component_name
    return bp


def test_validator_accepts_card_only_component(card_only_component):
    """Rule 3 must accept a step whose component exists only as a reference card."""
    from solution_wizard.validator import validate

    result = validate(_blueprint_with_parser(card_only_component))
    rule3 = [e for e in result.errors if e.rule == 3 and card_only_component in e.message]
    assert not rule3


def test_validator_rejects_component_in_neither_registry_nor_cards(card_only_component):
    """Negative control: without a card *or* a registry entry, rule 3 must fire.

    Without this, test_validator_accepts_card_only_component would still pass if
    rule 3 stopped checking components altogether.
    """
    from solution_wizard.validator import validate

    result = validate(_blueprint_with_parser("NotAComponentAnywhere"))
    rule3 = [e for e in result.errors if e.rule == 3 and "NotAComponentAnywhere" in e.message]
    assert rule3


def test_pip_requirements_falls_back_to_card_install_extra(card_only_component):
    """requirements.txt must pick up install_extra from the card when the registry has no entry."""
    from solution_wizard.registry import get_registry

    lines = get_registry().pip_requirements(["Transcriber", card_only_component])
    assert "gaik[transcriber]" in lines  # resolved via the registry
    assert f"gaik[{_CARD_ONLY_EXTRA}]" in lines  # resolved via the card fallback


def test_same_graph_different_order_same_key():
    """Blueprints with the same dependency graph but different step list order → same key."""
    import copy

    bp1 = _hybrid_blueprint()
    bp2 = _hybrid_blueprint()
    # Reverse the step list -- depends_on graph is the same
    bp2.workflow.steps = list(reversed(bp2.workflow.steps))

    assert _derive_pattern_key(bp1) == _derive_pattern_key(bp2)


def _blueprint_with_extra_block(extra: str) -> Blueprint:
    """AudioToStructuredData module + an extra building block."""
    data = {
        "blueprint_version": "1.0",
        "use_case": {"id": "mixed", "name": "Mixed", "description": "x", "domain": "test"},
        "technical_spec": {
            "input_types": ["audio"],
            "output_types": ["structured_json"],
            "language": "en",
        },
        "target_output_spec": {},
        "components": {
            "selected_modules": [
                {
                    "id": "audio_to_structured_data",
                    "name": "AudioToStructuredData",
                    "reason": "test",
                }
            ],
            "selected_building_blocks": [extra],
            "custom_components": [],
        },
        "artifacts": {
            "src": {"type": "audio", "source": "user_upload", "optional": False},
            "out": {
                "type": "structured_json",
                "source": "generated",
                "optional": False,
                "final_output": True,
                "produced_by": "step_a",
            },
        },
        "workflow": {
            "steps": [
                {
                    "id": "step_a",
                    "name": "A",
                    "type": "automated_task",
                    "component": "AudioToStructuredData",
                    "inputs": ["src"],
                    "outputs": ["out"],
                },
            ]
        },
    }
    return Blueprint.model_validate(data)


def test_multiple_selected_modules_falls_to_generic():
    """Two selected modules (e.g. audio + document) must not silently drop one."""
    data = {
        "blueprint_version": "1.0",
        "use_case": {"id": "multi_mod", "name": "Multi", "description": "x", "domain": "test"},
        "technical_spec": {
            "input_types": ["audio", "pdf"],
            "output_types": ["structured_json"],
            "language": "en",
        },
        "target_output_spec": {},
        "components": {
            "selected_modules": [
                {
                    "id": "audio_to_structured_data",
                    "name": "AudioToStructuredData",
                    "reason": "audio",
                },
                {
                    "id": "documents_to_structured_data",
                    "name": "DocumentsToStructuredData",
                    "reason": "doc",
                },
            ],
            "selected_building_blocks": [],
            "custom_components": [],
        },
        "artifacts": {
            "src": {"type": "audio", "source": "user_upload", "optional": False},
            "out": {
                "type": "structured_json",
                "source": "generated",
                "optional": False,
                "final_output": True,
                "produced_by": "step_a",
            },
        },
        "workflow": {
            "steps": [
                {
                    "id": "step_a",
                    "name": "A",
                    "type": "automated_task",
                    "component": "AudioToStructuredData",
                    "inputs": ["src"],
                    "outputs": ["out"],
                },
            ]
        },
    }
    bp = Blueprint.model_validate(data)
    assert _determine_pattern(bp) == "_generic"


def test_module_plus_llm_judge_only_uses_fixed_pattern():
    """AudioToStructuredData + LLMJudge (injected separately) → fixed pattern, not _generic."""
    bp = _blueprint_with_extra_block("LLMJudge")
    assert _determine_pattern(bp) == "audio_to_structured"


def test_module_plus_extra_component_falls_to_generic():
    """AudioToStructuredData + DocumentClassifier (not in module) → _generic."""
    bp = _blueprint_with_extra_block("DocumentClassifier")
    assert _determine_pattern(bp) == "_generic"


def test_dynamic_discovery_finds_promoted_template(tmp_path, monkeypatch):
    """If a template exists at templates/poc/<pattern_key>/, _determine_pattern returns it."""
    import solution_wizard.scaffolder as scaffolder_mod

    bp = _hybrid_blueprint()
    key = _derive_pattern_key(bp)

    # Point TEMPLATES_DIR at a temp dir containing a fake promoted template
    fake_templates = tmp_path / "poc"
    (fake_templates / key).mkdir(parents=True)
    (fake_templates / key / "run_poc.py.tmpl").write_text("# promoted template\n")
    monkeypatch.setattr(scaffolder_mod, "TEMPLATES_DIR", fake_templates)

    assert scaffolder_mod._determine_pattern(bp) == key
