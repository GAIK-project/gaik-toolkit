"""Option dictionaries a module forwards are checked by name before any work starts.

A name must be a parameter of the component it goes to, and a stage config comes
from the module's constructor, never from an option dictionary. No test reaches
a network or a model.
"""

from __future__ import annotations

import inspect
from types import SimpleNamespace

import pytest
from gaik.software_modules._options import checked_options

CONFIG = {"provider": "openai", "api_key": "test-key", "model": "test-model"}


def _target(path, *, dpi: int = 200, clean_output: bool = True):
    return path


def _open_target(**kwargs):
    return kwargs


def test_known_names_pass_and_a_new_dict_is_returned():
    given = {"dpi": 300}
    checked = checked_options(given, _target, what="parse_options")
    assert checked == {"dpi": 300} and checked is not given
    assert checked_options(None, _target, what="parse_options") == {}


def test_an_unknown_name_is_refused_with_the_allowed_ones():
    with pytest.raises(ValueError, match=r"unknown option 'dpii'.*allowed: clean_output, dpi"):
        checked_options({"dpii": 300}, _target, what="parse_options", set_by_module=("path",))


@pytest.mark.parametrize("key", ["config", "api_config", "openai_config"])
def test_a_stage_config_is_refused_even_where_any_name_is_taken(key):
    with pytest.raises(ValueError, match=f"'{key}' is not accepted here"):
        checked_options({key: CONFIG}, _open_target, what="parser_ctor")
    with pytest.raises(ValueError, match=f"'{key}' is not accepted here"):
        checked_options({key: CONFIG}, None, what="parser_ctor")


def test_a_parameter_the_module_sets_is_refused():
    with pytest.raises(ValueError, match="'path' is set by the module itself"):
        checked_options(
            {"path": "other.pdf"}, _target, what="parse_options", set_by_module=["path"]
        )


def test_a_target_that_takes_any_name_accepts_other_names():
    assert checked_options({"anything": 1}, _open_target, what="x") == {"anything": 1}


# -- DocumentsToStructuredData ---------------------------------------------------------


def _documents(monkeypatch):
    module = pytest.importorskip("gaik.software_modules.documents_to_structured_data.pipeline")
    if module.VisionParser is None:
        pytest.skip("the vision parser extra is not installed")
    pipeline = module.DocumentsToStructuredData(api_config=CONFIG)
    monkeypatch.setattr(pipeline, "_build_parser", lambda *a: pytest.fail("parsed"))
    return pipeline


@pytest.mark.parametrize(
    ("options", "message"),
    [
        ({"parser_ctor": {"openai_config": CONFIG}}, "parser_ctor: 'openai_config'"),
        ({"parser_ctor": {"api_key": "other"}}, "parser_ctor: unknown option 'api_key'"),
        ({"parse_options": {"pdf_path": "other.pdf"}}, "parse_options: 'pdf_path' is set"),
        ({"parse_options": {"dpii": 1}}, "parse_options: unknown option 'dpii'"),
        ({"extractor_ctor": {"config": CONFIG}}, "extractor_ctor: 'config'"),
        ({"extract_options": {"documents": ["x"]}}, "extract_options: 'documents' is set"),
    ],
)
def test_documents_module_refuses_an_option_before_parsing(monkeypatch, options, message):
    pipeline = _documents(monkeypatch)
    with pytest.raises(ValueError, match=message):
        pipeline.run(file_path="synthetic.pdf", user_requirements="Extract the total", **options)


def test_documents_module_names_the_parse_method_of_each_parser():
    module = pytest.importorskip("gaik.software_modules.documents_to_structured_data.pipeline")
    for choice, method in module._PARSE_METHOD.items():
        parser_class = {
            "vision_parser": module.VisionParser,
            "docling": module.DoclingParser,
            "pymupdf": module.PyMuPDFParser,
            "docx": module.DocxParser,
        }[choice]
        if parser_class is not None:
            assert callable(getattr(parser_class, method)), (choice, method)


# -- AudioToStructuredData -------------------------------------------------------------


def _audio(monkeypatch):
    module = pytest.importorskip("gaik.software_modules.audio_to_structured_data.pipeline")
    return module, module.AudioToStructuredData(api_config=CONFIG)


@pytest.mark.parametrize(
    ("options", "message"),
    [
        ({"transcriber_ctor": {"api_config": CONFIG}}, "transcriber_ctor: 'api_config'"),
        ({"transcriber_ctor": {"base_url": "x"}}, "transcriber_ctor: unknown option 'base_url'"),
        ({"transcribe_options": {"file_path": "other.mp3"}}, "'file_path' is set"),
        ({"extractor_ctor": {"config": CONFIG}}, "extractor_ctor: 'config'"),
    ],
)
def test_audio_module_refuses_an_option_before_transcribing(monkeypatch, options, message):
    module, pipeline = _audio(monkeypatch)
    real = module.Transcriber

    def no_transcriber(**kwargs):
        pytest.fail("a transcriber was built")

    # The checks read the real signatures; building one would mean they passed.
    no_transcriber.__signature__ = inspect.signature(real)
    no_transcriber.transcribe = real.transcribe
    monkeypatch.setattr(module, "Transcriber", no_transcriber)
    with pytest.raises(ValueError, match=message):
        pipeline.run(file_path="synthetic.mp3", user_requirements="Extract the total", **options)


def test_audio_module_passes_its_own_transcription_config_and_the_callers_options(
    monkeypatch, tmp_path
):
    module, pipeline = _audio(monkeypatch)
    seen = {}

    class StopError(Exception):
        pass

    def transcriber(**kwargs):
        seen.update(kwargs)
        return SimpleNamespace(transcribe=lambda **_: (_ for _ in ()).throw(StopError()))

    transcriber.transcribe = module.Transcriber.transcribe
    monkeypatch.setattr(module, "Transcriber", transcriber)
    with pytest.raises(StopError):
        pipeline.run(
            file_path="synthetic.mp3",
            user_requirements="Extract the total",
            transcriber_ctor={"language": "fi", "output_dir": str(tmp_path)},
        )
    assert seen["api_config"] is pipeline.transcription_config
    assert (seen["language"], seen["output_dir"]) == ("fi", str(tmp_path))
    assert seen["enhanced_transcript"] is False
