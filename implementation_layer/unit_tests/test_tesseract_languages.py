"""Offline tests for the Tesseract language filter in software_components._tesseract.

Docling 2.132 and later refuses Tesseract OCR while one of its default languages has
no traineddata; gaik passes it only the installed ones. ``tesseract --list-langs`` is
faked, so no test needs a Tesseract install.
"""

from __future__ import annotations

import logging
import subprocess

import pytest
from gaik.software_components import _tesseract
from gaik.software_components._tesseract import (
    installed_tesseract_cli_languages,
    with_installed_languages,
)
from pydantic import BaseModel

DEBIAN_ENG_ONLY = (
    'List of available languages in "/usr/share/tesseract-ocr/5/tessdata/" (2):\neng\nosd\n'
)


class _Options(BaseModel):
    lang: list[str] = ["eng", "spa", "fra", "deu"]
    force_full_page_ocr: bool = False


def _fake_list_langs(monkeypatch, stdout: str = "", returncode: int = 0, raises=None):
    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if raises is not None:
            raise raises
        return subprocess.CompletedProcess(cmd, returncode, stdout=stdout, stderr="")

    monkeypatch.setattr(_tesseract.subprocess, "run", fake_run)
    return calls


def test_list_langs_reads_the_languages_under_the_header(monkeypatch):
    calls = _fake_list_langs(monkeypatch, DEBIAN_ENG_ONLY)

    assert installed_tesseract_cli_languages() == {"eng", "osd"}
    assert calls == [["tesseract", "--list-langs"]]


@pytest.mark.parametrize(
    "fake",
    [
        {"raises": FileNotFoundError("tesseract")},
        {"raises": subprocess.TimeoutExpired("tesseract", 30)},
        {"returncode": 1, "stdout": "eng\n"},
    ],
)
def test_list_langs_is_unknown_when_tesseract_cannot_list(monkeypatch, fake):
    _fake_list_langs(monkeypatch, **fake)

    assert installed_tesseract_cli_languages() is None


def test_only_the_installed_default_languages_are_kept_in_order(caplog):
    with caplog.at_level(logging.WARNING, logger=_tesseract.__name__):
        options = with_installed_languages(
            _Options, {"osd", "deu", "eng"}, force_full_page_ocr=True
        )

    assert options.lang == ["eng", "deu"]
    assert options.force_full_page_ocr is True
    [record] = caplog.records
    assert record.levelno == logging.WARNING
    assert "no traineddata for spa, fra" in record.getMessage()
    assert "uses eng, deu" in record.getMessage()


@pytest.mark.parametrize(
    "installed",
    [None, set(), {"fin", "osd"}, {"eng", "spa", "fra", "deu", "fin"}],
    ids=["unknown", "empty", "no-default-language", "all-installed"],
)
def test_docling_default_stays_when_nothing_or_everything_matches(installed, caplog):
    with caplog.at_level(logging.WARNING, logger=_tesseract.__name__):
        options = with_installed_languages(_Options, installed)

    assert options.lang == ["eng", "spa", "fra", "deu"]
    assert caplog.records == []


def _fake_tesseract_cli(monkeypatch, listing: str):
    """Fake the Tesseract CLI for gaik's language list and for Docling's own engine.

    Both call ``subprocess.run(["tesseract", "--list-langs"], ...)``: gaik with
    ``text=True``, Docling for bytes. Docling reads the version through ``Popen``.
    """
    from docling.models.stages.ocr import tesseract_ocr_cli_model

    def fake_run(cmd, **kwargs):
        assert cmd[-1] == "--list-langs", cmd
        out = listing if kwargs.get("text") else listing.encode()
        return subprocess.CompletedProcess(cmd, 0, stdout=out, stderr=out[:0])

    class FakePopen:
        def __init__(self, cmd, **kwargs):
            assert cmd[-1] == "--version", cmd

        def communicate(self):
            return b"tesseract 5.5.0\n", b""

        def wait(self):
            return 0

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(tesseract_ocr_cli_model, "Popen", FakePopen)
    return tesseract_ocr_cli_model.TesseractOcrCliModel


def _start_docling_engine(engine_cls, options):
    from docling.datamodel.accelerator_options import AcceleratorOptions

    return engine_cls(
        enabled=True,
        artifacts_path=None,
        options=options,
        accelerator_options=AcceleratorOptions(),
    )


def test_docling_engine_starts_when_only_english_is_installed(monkeypatch):
    pytest.importorskip("docling")
    from gaik.software_components.RAG.rag_parser_docling.parser import _build_ocr_options

    engine_cls = _fake_tesseract_cli(monkeypatch, DEBIAN_ENG_ONLY)
    options = _build_ocr_options("tesseract_cli")

    engine = _start_docling_engine(engine_cls, options)
    assert engine.options.lang == ["eng"]


def test_no_installed_default_language_leaves_doclings_default_and_error(monkeypatch):
    """With none of the defaults installed, Docling's own error explains the install."""
    pytest.importorskip("docling")
    from docling.datamodel.pipeline_options import TesseractCliOcrOptions
    from docling.exceptions import OcrLanguageNotSupportedError
    from gaik.software_components.RAG.rag_parser_docling.parser import _build_ocr_options

    engine_cls = _fake_tesseract_cli(monkeypatch, "List of available languages (2):\nfin\nosd\n")
    options = _build_ocr_options("tesseract_cli")

    assert options.lang == TesseractCliOcrOptions.model_fields["lang"].default
    with pytest.raises(OcrLanguageNotSupportedError, match="'eng'"):
        _start_docling_engine(engine_cls, options)


def test_rag_parser_tesseract_cli_options_skip_missing_languages(monkeypatch):
    pytest.importorskip("docling")
    from docling.datamodel.pipeline_options import TesseractCliOcrOptions
    from gaik.software_components.RAG.rag_parser_docling.parser import _build_ocr_options

    _fake_list_langs(monkeypatch, DEBIAN_ENG_ONLY)
    options = _build_ocr_options("tesseract_cli")

    assert isinstance(options, TesseractCliOcrOptions)
    assert options.lang == ["eng"]


def test_rag_parser_tesserocr_options_skip_missing_languages(monkeypatch):
    pytest.importorskip("docling")
    from docling.datamodel.pipeline_options import TesseractOcrOptions
    from gaik.software_components.RAG.rag_parser_docling import parser as rag_parser

    monkeypatch.setattr(rag_parser, "installed_tesserocr_languages", lambda: {"eng", "fra"})
    options = rag_parser._build_ocr_options("tesseract")

    assert isinstance(options, TesseractOcrOptions)
    assert options.lang == ["eng", "fra"]


def test_docling_parser_tesseract_cli_keeps_full_page_ocr(monkeypatch):
    pytest.importorskip("docling")
    from docling.datamodel.pipeline_options import OcrMode
    from gaik.software_components.parsers import docling as docling_parser

    if not docling_parser.DOCLING_IMPORT_SUCCESS:
        pytest.skip("docling's pipeline options did not import")
    _fake_list_langs(monkeypatch, DEBIAN_ENG_ONLY)
    parser = docling_parser.DoclingParser.__new__(docling_parser.DoclingParser)
    parser.pipeline_options = docling_parser.PdfPipelineOptions()

    parser._set_ocr_engine("tesseract_cli")

    assert parser.pipeline_options.ocr_options.lang == ["eng"]
    assert parser.pipeline_options.ocr_options.mode == OcrMode.FULL_PAGE
