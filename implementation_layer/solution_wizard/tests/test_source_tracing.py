"""The wizard knows SourceTracing: registry entry, reference card, validation and scaffolding."""

import ast
import importlib
import inspect
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from solution_wizard.blueprint import Blueprint
from solution_wizard.registry import get_reference_cards, get_registry
from solution_wizard.scaffolder import _determine_pattern, scaffold_poc, validate_generated_python
from solution_wizard.validator import validate

WIZARD = Path(__file__).parent.parent
REPO = WIZARD.parent.parent
EXAMPLES = WIZARD / "examples"


def _entry() -> dict:
    entry = get_registry().lookup_by_name("SourceTracing")
    assert entry is not None, "SourceTracing is not in the registry"
    return entry


def _card() -> dict:
    card = get_reference_cards().get("SourceTracing")
    assert card is not None, "SourceTracing has no reference card"
    return card


def _blueprint_with_source_tracing() -> Blueprint:
    """The document extraction example with a SourceTracing step after the extraction."""
    data = json.loads((EXAMPLES / "document_extraction_blueprint.json").read_text(encoding="utf-8"))
    data["artifacts"]["purchase_order_json"]["final_output"] = False
    data["artifacts"]["trace_report"] = {
        "type": "validation_report",
        "source": "generated",
        "optional": False,
        "final_output": True,
        "produced_by": "trace_po_fields",
    }
    data["components"]["selected_building_blocks"].append("SourceTracing")
    data["workflow"]["steps"].append(
        {
            "id": "trace_po_fields",
            "name": "Trace each value to its quote in the source",
            "type": "automated_task",
            "component": "SourceTracing",
            "inputs": ["source_pdf", "purchase_order_json"],
            "outputs": ["trace_report"],
            "parameters": {"source": "text"},
            "depends_on": ["extract_po_fields"],
        }
    )
    return Blueprint.model_validate(data)


# ---------------------------------------------------------------------------
# Registry entry
# ---------------------------------------------------------------------------


def test_registry_entry_points_at_real_files_and_a_real_extra():
    entry = _entry()

    assert entry["type"] == "software_component"
    assert entry["install_extra"] == "source-tracing"
    for key in ("source_path", "readme_path", "example_script_path"):
        assert (REPO / entry[key]).exists(), f"{key} does not exist: {entry[key]}"
    assert importlib.import_module(entry["import_path"]).SourceTracing
    pyproject = (REPO / "pyproject.toml").read_text(encoding="utf-8")
    assert re.search(r"^source-tracing = \[", pyproject, re.MULTILINE)


def test_source_tracing_works_around_extractors_and_is_never_subsumed():
    entry = _entry()
    assert not entry.get("subsumes")
    assert not entry["uses_components"]
    # No module lists it as an internal component, and no card declares it subsumed.
    for other in get_registry().all():
        assert "SourceTracing" not in other.get("uses_components", [])
    cards = get_reference_cards()
    for name in cards.names():
        assert "SourceTracing" not in (cards.get(name).get("subsumes") or [])


def test_registry_entry_takes_extracted_values_and_a_source():
    entry = _entry()

    assert "structured_json" in entry["input_artifact_types"]
    assert {"text", "transcript", "pdf"} <= set(entry["input_artifact_types"])
    assert "validation_report" in entry["output_artifact_types"]
    assert entry["known_limitations"] and entry["best_for"]


# ---------------------------------------------------------------------------
# Reference card
# ---------------------------------------------------------------------------


def test_card_recipe_matches_the_real_api():
    card = _card()
    module = importlib.import_module("gaik.software_components.source_tracing")
    cls = module.SourceTracing

    assert "from gaik.software_components.source_tracing import" in card["import"]
    assert card["construct"] == "tracing = SourceTracing()"
    # The first call is augment(); the rest of the recipe uses real methods.
    assert re.search(r"\.\s*(\w+)\s*\(", card["call"]).group(1) == "augment"
    for method in re.findall(r"tracing\.(\w+)\(", card["call"]):
        assert callable(getattr(cls, method, None)), f"SourceTracing.{method} does not exist"
    assert callable(module.transcript_used)
    assert "transcript_used" in card["call"]


def test_card_options_are_real_parameters():
    card = _card()
    cls = importlib.import_module("gaik.software_components.source_tracing").SourceTracing
    params = set(inspect.signature(cls.__init__).parameters) | set(
        inspect.signature(cls.augment).parameters
    )

    options = {o["name"]: o for o in card["options"]}
    assert set(options) <= params
    assert options["source"]["selection_relevant"] is True
    assert set(options["source"]["values"]) == {"text", "files"}


def test_card_covers_the_four_hosts_and_the_verdicts():
    card = _card()
    recipe = card["call"]

    assert "check_text" in recipe and "check_pdf" in recipe
    assert "DocumentsToStructuredData" in recipe and "AudioToStructuredData" in recipe
    for verdict in ("verified", "check", "reworded", "unchecked"):
        assert verdict in card["returns"]
    assert "never a subsumed component" in card["note"] or "changes none" in card["note"]


# ---------------------------------------------------------------------------
# A blueprint with a SourceTracing step
# ---------------------------------------------------------------------------


def test_blueprint_with_a_source_tracing_step_validates_without_errors():
    result = validate(_blueprint_with_source_tracing())

    assert result.ok, result.summary()
    assert not [w for w in result.warnings if "SourceTracing" in str(w)]


def test_blueprint_with_an_unknown_component_is_still_rejected():
    bp = _blueprint_with_source_tracing()
    bp.workflow.steps[-1].component = "SourceTracingX"

    result = validate(bp)

    assert not result.ok


def _with_source_tracing(filename: str, *extra_blocks: str) -> Blueprint:
    """An example blueprint with a SourceTracing step after its module step."""
    data = json.loads((EXAMPLES / filename).read_text(encoding="utf-8"))
    module = data["components"]["selected_modules"][0]["name"]
    steps = data["workflow"]["steps"]
    step = next(s for s in steps if s.get("component") in (module, "Extractor", "DataExtractor"))
    produced = step["outputs"][0]
    data["artifacts"][produced]["final_output"] = False
    data["artifacts"]["trace_report"] = {
        "type": "validation_report",
        "source": "generated",
        "optional": False,
        "final_output": True,
        "produced_by": "trace_values",
    }
    data["components"]["selected_building_blocks"] += ["SourceTracing", *extra_blocks]
    data["workflow"]["steps"].append(
        {
            "id": "trace_values",
            "name": "Trace each value to its quote in the source",
            "type": "automated_task",
            "component": "SourceTracing",
            "inputs": [produced],
            "outputs": ["trace_report"],
            "parameters": {"source": "text"},
            "depends_on": [step["id"]],
        }
    )
    return Blueprint.model_validate(data)


def test_document_extraction_keeps_its_fixed_template_and_traces_the_values(tmp_path):
    bp = _blueprint_with_source_tracing()
    assert _determine_pattern(bp) == "document_to_structured"

    result = scaffold_poc(bp, tmp_path)
    poc = result["poc_dir"]
    run_poc = (poc / "run_poc.py").read_text(encoding="utf-8")

    assert result["template_wired"] is True
    assert validate_generated_python(poc) is None
    assert "gaik[source-tracing]" in (poc / "requirements.txt").read_text(encoding="utf-8")
    # The evidence is requested before the run, checked after it, and checked before the judge.
    asked = run_poc.index('tracing.augment(schema, user_requirements, source="text")')
    ran = run_poc.index("result = pipeline.run(")
    checked = run_poc.index("tracing.check_text(")
    written = run_poc.index("_result.json")
    assert asked < ran < checked < written
    assert "result.parsed_documents" in run_poc[checked : checked + 200]
    assert "result.extracted_fields = clean_fields" in run_poc


def test_audio_extraction_keeps_its_fixed_template_and_traces_the_transcript(tmp_path):
    bp = _with_source_tracing("incident_reporting_blueprint.json")
    assert _determine_pattern(bp) == "audio_to_structured"

    poc = scaffold_poc(bp, tmp_path)["poc_dir"]
    run_poc = (poc / "run_poc.py").read_text(encoding="utf-8")

    assert validate_generated_python(poc) is None
    assert "transcript_used(result)" in run_poc
    assert run_poc.index("tracing.augment(") < run_poc.index("pipeline.run(")
    # The judge, when it is also selected, runs after the tracing, on the cleaned fields.
    assert run_poc.index("tracing.check_text(") < run_poc.index("LLMJudge hallucination")


def test_a_pipeline_without_source_tracing_is_unchanged(tmp_path):
    for name in ("document_extraction_blueprint.json", "incident_reporting_blueprint.json"):
        bp = Blueprint.from_file(EXAMPLES / name)
        poc = scaffold_poc(bp, tmp_path / name)["poc_dir"]
        run_poc = (poc / "run_poc.py").read_text(encoding="utf-8")

        assert "SourceTracing" not in run_poc and "tracing" not in run_poc


def test_extra_blocks_the_template_does_not_inject_still_fall_back_to_generic(tmp_path):
    # A DocumentClassifier is not covered, so the fixed template would drop it: the generic
    # template (labelled blocks with the card recipes) is used, SourceTracing included.
    bp = _with_source_tracing("document_extraction_blueprint.json", "DocumentClassifier")
    assert _determine_pattern(bp) == "_generic"

    poc = scaffold_poc(bp, tmp_path)["poc_dir"]
    run_poc = (poc / "run_poc.py").read_text(encoding="utf-8")

    assert validate_generated_python(poc) is None
    assert "Step: trace_values  (SourceTracing)" in run_poc
    assert "tracing.augment(" in run_poc and "tracing.check_text(" in run_poc


def test_a_rag_blueprint_does_not_get_the_extraction_template_slot(tmp_path):
    # RAG has no extraction step: SourceTracing is not injected there, so the fixed RAG
    # template (which would silently drop it) is not used.
    data = json.loads((EXAMPLES / "rag_workflow_blueprint.json").read_text(encoding="utf-8"))
    data["components"]["selected_building_blocks"].append("SourceTracing")
    bp = Blueprint.model_validate(data)

    assert _determine_pattern(bp) != "rag"


def test_scaffold_without_source_tracing_keeps_the_fixed_template(tmp_path):
    bp = Blueprint.from_file(EXAMPLES / "document_extraction_blueprint.json")

    assert _determine_pattern(bp) == "document_to_structured"
    assert scaffold_poc(bp, tmp_path)["template_wired"] is True


# ---------------------------------------------------------------------------
# SKILL.md guidance
# ---------------------------------------------------------------------------

SKILL = (WIZARD / "SKILL.md").read_text(encoding="utf-8")


def _step3() -> str:
    start = SKILL.index("**Step 3 -- Add review aids when appropriate")
    return SKILL[start : SKILL.index("**Step 4 -- Configure component options**")]


def test_skill_asks_once_and_recommends_both_review_aids():
    step3 = _step3()

    assert "**Ask once**" in step3 and "recommended" in step3
    for option in (
        "Source tracing and LLM judge",
        "Source tracing only",
        "LLM judge only",
        "Neither",
    ):
        assert option in step3


def test_skill_defaults_to_the_judge_when_nobody_can_answer():
    step3 = _step3()

    assert "No user to answer" in step3
    assert "add `LLMJudge` when `human_review == yes`" in step3
    assert "ask for evidence" in step3 or "asks for evidence" in step3


def test_skill_orders_the_aids_and_skips_report_patterns():
    step3 = _step3()

    assert "extraction → `SourceTracing` → `LLMJudge` → the `human_review` step" in step3
    assert "multi_source_report" in step3 and "Skip this step entirely" in step3
    assert "AnswerGenerator.citations" in step3  # RAG is unchanged


def test_skill_separates_evidence_from_confidence_and_from_rag_citations():
    assert "include_verification" in SKILL and "not evidence" in SKILL
    assert "on extracted field values" in SKILL and "add `SourceTracing`" in SKILL
    assert "The blueprint's `traceability` section is a different thing" in SKILL


def test_skill_lists_source_tracing_in_the_component_table_and_composition():
    assert "| SourceTracing | component |" in SKILL
    assert "→ `SourceTracing` after the extraction step" in SKILL
    # The review aids are chosen in Phase 5, not as a Round 2 question.
    assert "do not ask which review aids" in SKILL


def test_skill_describes_the_fixed_templates_and_the_generic_fallback():
    step3 = _step3()

    assert "inject `SourceTracing`" in step3
    assert "The schema must exist" in step3 and "`_generic` template" in step3


def test_the_diagram_and_document_generators_handle_the_new_step(tmp_path):
    from solution_wizard.bpmn_generator import generate_bpmn
    from solution_wizard.docs_generator import generate_docs
    from solution_wizard.visualizer import generate_mermaid

    bp = _blueprint_with_source_tracing()

    assert "trace_po_fields" in generate_bpmn(bp)
    assert "trace_po_fields" in generate_mermaid(bp)
    written = generate_docs(bp, tmp_path)
    assert written
    assert any("SourceTracing" in path.read_text(encoding="utf-8") for path in written)
