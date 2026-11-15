"""A generated PoC does not call an unreadable LLMJudge response a pass.

gaik after 0.8.14 sets ``HallucinationReport.judge_error`` when the judge's
response could not be read, and its flag list is then empty because there is no
verdict. gaik 0.8.14 has neither ``judge_error`` nor ``passed``, and a generated
PoC may install either, so the PoC reads both with ``getattr``.
"""

import json
import sys
import textwrap
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from solution_wizard.blueprint import Blueprint  # noqa: E402
from solution_wizard.scaffolder import (  # noqa: E402
    _build_generic_judge_section,
    _build_variables,
)

ROOT = Path(__file__).parent.parent
HYBRID = ROOT / "templates" / "poc" / "hybrid_dataextractor_pymupdfparser_transcriber_831947a5"


class _OldReport:
    """HallucinationReport as gaik 0.8.14 returns it: flags only."""

    def __init__(self, flags, judge_error=None):
        self.flags = flags


class _NewReport(_OldReport):
    """HallucinationReport with judge_error and passed."""

    def __init__(self, flags, judge_error=None):
        super().__init__(flags)
        self.judge_error = judge_error

    @property
    def passed(self):
        return self.judge_error is None and not self.flags


def _fake_judge(monkeypatch, module_name: str, report) -> None:
    class LLMJudge:
        def __init__(self, config=None):
            pass

        def detect_hallucinations(self, source_text, extracted):
            return report

    module = types.ModuleType(module_name)
    module.LLMJudge = LLMJudge
    monkeypatch.setitem(sys.modules, module_name, module)


def _run_generic(tmp_path, monkeypatch, report) -> dict:
    _fake_judge(monkeypatch, "gaik.software_components.validators.llm_judge", report)
    namespace = {
        "extracted_fields": {"total": "10"},
        "source_text": "Total 10",
        "config": {},
        "get_stage_config": lambda config, stage: None,
        "output_dir": tmp_path,
        "json": json,
    }
    exec(textwrap.dedent(_build_generic_judge_section(True)), namespace)
    return json.loads((tmp_path / "validation.json").read_text(encoding="utf-8"))


def _run_module(tmp_path, monkeypatch, report) -> dict:
    _fake_judge(monkeypatch, "gaik.software_components.validators.llm_judge.llm_judge", report)
    blueprint = Blueprint.from_file(ROOT / "examples" / "incident_reporting_blueprint.json")
    section = _build_variables(blueprint, "audio_to_structured")["llm_judge_section"]
    transcription = types.SimpleNamespace(enhanced_transcript="Total 10", raw_transcript=None)
    namespace = {
        "result": types.SimpleNamespace(
            transcription=transcription, extracted_fields=[{"total": "10"}]
        ),
        "input_file": Path("note.wav"),
        "config": {},
        "get_stage_config": lambda config, stage: None,
        "output_dir": tmp_path,
        "json": json,
    }
    exec(textwrap.dedent(section), namespace)
    return json.loads((tmp_path / "note_validation.json").read_text(encoding="utf-8"))


RUNS = pytest.mark.parametrize("run", [_run_generic, _run_module], ids=["generic", "module"])


@RUNS
def test_an_unreadable_judge_response_is_not_a_pass(tmp_path, monkeypatch, run, capsys):
    result = run(tmp_path, monkeypatch, _NewReport([], "response is not JSON (12 characters)"))
    assert result["passed"] is False
    assert result["judge_error"] == "response is not JSON (12 characters)"
    out = capsys.readouterr().out
    assert "could not be read" in out and "check passed" not in out


@RUNS
def test_a_readable_verdict_without_flags_passes(tmp_path, monkeypatch, run, capsys):
    result = run(tmp_path, monkeypatch, _NewReport([]))
    assert result == {"hallucination_flags": [], "judge_error": None, "passed": True}
    assert "check passed" in capsys.readouterr().out


@RUNS
def test_on_gaik_0_8_14_an_empty_flag_list_still_passes(tmp_path, monkeypatch, run):
    result = run(tmp_path, monkeypatch, _OldReport([]))
    assert result == {"hallucination_flags": [], "judge_error": None, "passed": True}


def test_the_hybrid_template_reads_the_verdict_like_the_generated_sections():
    template = (HYBRID / "run_poc.py.tmpl").read_text(encoding="utf-8")
    assert 'judge_error = getattr(report, "judge_error", None)' in template
    assert '"passed": getattr(report, "passed", not report.flags),' in template
    assert "len(report.flags) == 0" not in template
