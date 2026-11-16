"""The registry and reference cards describe what the gaik in this repo does (#149, #199, #198)."""

import importlib
import inspect
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from solution_wizard.registry import get_registry

REPO = Path(__file__).resolve().parents[3]
CARDS = json.loads(
    (Path(__file__).parent.parent / "registries" / "component_reference_cards.json").read_text(
        encoding="utf-8"
    )
)


def _option(card: str, name: str) -> dict:
    return next(o for o in CARDS[card]["options"] if o["name"] == name)


def _limitations(name: str) -> str:
    return " ".join(get_registry().lookup_by_name(name)["known_limitations"])


def test_answer_generator_prompt_card_matches_the_prompt_check():
    from gaik.software_components.RAG.answer_generator.generator import _validate_custom_prompt

    effect = _option("AnswerGenerator", "prompt")["effect"]
    with pytest.raises(ValueError):
        _validate_custom_prompt("Question: {query}")
    assert "ValueError" in effect
    assert "KeyError" not in effect and "silently drops" not in effect


def test_spreadsheet_parser_entry_says_numbers_keep_their_format():
    from gaik.software_components.parsers.spreadsheet_parser.spreadsheet_parser import _number

    assert _number(0.25, "0%") == "25%"
    text = get_registry().lookup_by_name("SpreadsheetParser")["quality_tradeoffs"]
    assert "lossless for cell values" not in text["speed_vs_accuracy"]
    assert "number format" in text["speed_vs_accuracy"]


def test_report_loaders_and_source_path_error_are_described():
    from gaik.software_modules.multi_source_report_generator import load_report_config
    from gaik.software_modules.report_writer import ReportSpec

    assert "root" in inspect.signature(ReportSpec.load).parameters
    assert "root" in inspect.signature(load_report_config).parameters

    writer = CARDS["ReportWriter"]
    # The import line a PoC copies stays the one every supported release has.
    assert "SourcePathError" not in writer["import"]
    assert "root=" in writer["call_from_spec_file"]
    assert "SourcePathError" in writer["call_from_spec_file"]
    assert "ReportSpec.load(path, root=" in _limitations("ReportWriter")

    generator = CARDS["MultiSourceReportGenerator"]
    assert "SourcePathError" not in generator["import"]
    assert "load_report_config(path, root=" in generator["note"]
    assert "load_report_config(path, root=" in _limitations("MultiSourceReportGenerator")


@pytest.mark.parametrize("card", ["ReportWriter", "MultiSourceReportGenerator"])
def test_card_imports_resolve(card):
    statement = CARDS[card]["import"]
    module, names = statement.removeprefix("from ").split(" import ")
    loaded = importlib.import_module(module)
    for name in names.split(","):
        assert hasattr(loaded, name.strip()), name


def test_judge_card_names_the_eu_default_location():
    source = (
        REPO / "implementation_layer/src/gaik/software_components/validators/llm_judge/llm_judge.py"
    ).read_text(encoding="utf-8")
    assert 'location or "eu"' in source and 'location="global"' in source
    effect = _option("LLMJudge", "use_vertexai")["effect"]
    assert "default 'global'" not in effect
    assert "'eu'" in effect and "'global'" in effect
    # The validated release a PoC installs has the EU default; the card says so.
    assert "Unset, the judge calls the EU multi-region 'eu'" in effect


def _card_class(name: str):
    """The class a card's import line names, or None when its extra is not installed."""
    module, names = CARDS[name]["import"].removeprefix("from ").split(" import ", 1)
    if name not in [part.strip() for part in names.split(",")]:
        return None
    try:
        return getattr(importlib.import_module(module), name, None)
    except ImportError:
        return None


def test_every_component_that_takes_input_limits_says_so_on_its_card_and_entry():
    takes_limits = []
    for name in CARDS:
        cls = _card_class(name)
        if cls is not None and "limits" in inspect.signature(cls.__init__).parameters:
            takes_limits.append(name)
    assert {"PyMuPDFParser", "VisionExtractor", "ParallelTranscriber"} <= set(takes_limits)

    for name in takes_limits:
        effect = _option(name, "limits")["effect"]
        assert "InputLimitError" in effect and "limits=" in effect, name
        assert "InputLimitError" in _limitations(name), name
        assert "limits" in get_registry().lookup_by_name(name)["optional_parameters"], name


def test_whisper_local_cap_card_says_the_six_hour_input_limit_applies_too():
    cap = _option("ParallelTranscriber", "whisper_local_max_audio_minutes")
    assert "max_media_seconds" in cap["effect"]
    assert "max_media_seconds" in cap["infer_from"]
