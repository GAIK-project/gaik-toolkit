"""Input limits: files over a limit are refused before parsing or any model call.

Every fixture is generated in ``tmp_path``; model clients, Docling converters and
media probes are replaced by fakes, so no test reaches a network or a model.
"""

from __future__ import annotations

import struct
import subprocess
import zipfile
import zlib
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pymupdf
import pytest
from gaik.software_components import input_limits
from gaik.software_components.input_limits import InputLimitError, InputLimits
from PIL import Image


def _pdf(path: Path, pages: int, *, width: float = 595, height: float = 842) -> Path:
    doc = pymupdf.open()
    for number in range(pages):
        page = doc.new_page(width=width, height=height)
        page.insert_text((72, 72), f"Page {number + 1} text")
    doc.save(path)
    doc.close()
    return path


def _png(path: Path, width: int, height: int) -> Path:
    Image.new("RGB", (width, height), "white").save(path)
    return path


def _png_header_only(path: Path, width: int, height: int) -> Path:
    """A PNG whose header claims ``width`` x ``height``; no real pixel data."""

    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(b""))
        + chunk(b"IEND", b"")
    )
    return path


# -- InputLimits itself ---------------------------------------------------------


def test_limit_error_is_a_value_error_naming_the_limit(tmp_path):
    path = tmp_path / "big.txt"
    path.write_bytes(b"x" * 2_000)

    with pytest.raises(ValueError) as caught:
        InputLimits(max_file_bytes=1_000).check_file_size(path)

    error = caught.value
    assert isinstance(error, InputLimitError)
    assert (error.limit, error.actual, error.maximum) == ("max_file_bytes", 2_000, 1_000)
    assert "big.txt" in str(error) and "max_file_bytes" in str(error)


def test_limits_must_be_positive_or_none():
    with pytest.raises(ValueError, match="max_pages"):
        InputLimits(max_pages=0)
    with pytest.raises(ValueError, match="max_table_rows"):
        InputLimits(max_table_rows=-1)
    assert InputLimits(max_pages=None).max_pages is None


def test_unlimited_switches_every_check_off(tmp_path):
    limits = InputLimits.unlimited()
    path = tmp_path / "file.bin"
    path.write_bytes(b"x" * 10)

    limits.check_file_size(path)
    limits.check_pages(10**9, "doc")
    limits.check_table_rows(10**9, "table")
    limits.check_image_pixels(10**6, 10**6, "image")
    limits.check_images(10**9, "doc")
    limits.check_media_seconds(10**9, "recording")


def test_defaults_accept_an_ordinary_document(tmp_path):
    pdf = _pdf(tmp_path / "report.pdf", pages=20)

    assert InputLimits().check_pdf(pdf) == 20


def test_zip_container_that_unpacks_to_too_much_is_refused(tmp_path):
    path = tmp_path / "packed.docx"
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("word/document.xml", b"0" * 2_000_000)
    assert path.stat().st_size < 100_000

    with pytest.raises(InputLimitError, match="unpacks") as caught:
        InputLimits(max_file_bytes=100_000).check_zip_container(path)
    assert caught.value.limit == "max_file_bytes"


def test_image_header_over_the_pixel_limit_is_refused_without_decoding(tmp_path):
    image = _png(tmp_path / "photo.png", 200, 100)

    with pytest.raises(InputLimitError) as caught:
        InputLimits(max_image_pixels=10_000).check_image_file(image)
    assert caught.value.limit == "max_image_pixels"
    assert caught.value.actual == 20_000


def test_image_too_large_for_pillow_to_open_is_refused(tmp_path):
    image = _png_header_only(tmp_path / "huge.png", 60_000, 60_000)

    with pytest.raises(InputLimitError) as caught:
        InputLimits().check_image_file(image)
    assert caught.value.limit == "max_image_pixels"


def test_media_probe_has_a_timeout_and_gives_up_when_it_passes(tmp_path, monkeypatch):
    seen = {}

    def slow_run(cmd, **kwargs):
        seen.update(kwargs)
        raise subprocess.TimeoutExpired(cmd, kwargs["timeout"])

    monkeypatch.setattr(input_limits.shutil, "which", lambda _name: "/usr/bin/ffprobe")
    monkeypatch.setattr(input_limits.subprocess, "run", slow_run)

    assert input_limits.probe_media_seconds(tmp_path / "a.mp3", timeout=5) is None
    assert seen["timeout"] == 5


def test_media_probe_reads_the_duration(tmp_path, monkeypatch):
    def run(cmd, **kwargs):
        return SimpleNamespace(returncode=0, stdout='{"format": {"duration": "12.5"}}')

    monkeypatch.setattr(input_limits.shutil, "which", lambda _name: "/usr/bin/ffprobe")
    monkeypatch.setattr(input_limits.subprocess, "run", run)

    assert input_limits.probe_media_seconds(tmp_path / "a.mp3") == 12.5


def test_docling_limits_pass_pages_and_size_to_docling():
    assert input_limits.docling_limits(InputLimits(max_pages=7, max_file_bytes=9)) == {
        "max_num_pages": 7,
        "max_file_size": 9,
    }
    assert input_limits.docling_limits(InputLimits.unlimited()) == {}


# -- local parsers --------------------------------------------------------------


def test_pymupdf_parser_refuses_a_pdf_with_too_many_pages(tmp_path):
    from gaik.software_components.parsers.pymypdf import PyMuPDFParser

    pdf = _pdf(tmp_path / "long.pdf", pages=3)

    with pytest.raises(InputLimitError) as caught:
        PyMuPDFParser(limits=InputLimits(max_pages=2)).parse_pdf(str(pdf))
    assert caught.value.limit == "max_pages"
    assert "Page 1" in PyMuPDFParser(limits=InputLimits(max_pages=3)).parse_pdf(str(pdf))


def test_pymupdf_parser_refuses_a_file_over_the_size_limit(tmp_path):
    from gaik.software_components.parsers.pymypdf import PyMuPDFParser

    pdf = _pdf(tmp_path / "doc.pdf", pages=1)

    with pytest.raises(InputLimitError, match="max_file_bytes"):
        PyMuPDFParser(limits=InputLimits(max_file_bytes=100)).parse_document(str(pdf))


def test_docx_parser_refuses_a_file_that_unpacks_to_too_much(tmp_path):
    from docx import Document
    from gaik.software_components.parsers.docx_parser import DocxParser

    path = tmp_path / "notes.docx"
    document = Document()
    document.add_paragraph("0" * 1_000_000)
    document.save(path)
    assert path.stat().st_size < 60_000

    with pytest.raises(InputLimitError, match="unpacks"):
        DocxParser(limits=InputLimits(max_file_bytes=60_000)).parse_docx(str(path))
    assert DocxParser().parse_docx(str(path)).startswith("000")


def test_spreadsheet_parser_refuses_a_csv_with_too_many_rows(tmp_path):
    from gaik.software_components.parsers.spreadsheet_parser import SpreadsheetParser

    path = tmp_path / "rows.csv"
    path.write_text("name,value\n" + "".join(f"r{i},{i}\n" for i in range(5)))

    with pytest.raises(InputLimitError) as caught:
        SpreadsheetParser(limits=InputLimits(max_table_rows=4)).parse_spreadsheet(path)
    assert caught.value.limit == "max_table_rows"
    assert "r4" in SpreadsheetParser(limits=InputLimits(max_table_rows=6)).parse_spreadsheet(path)


def test_spreadsheet_parser_refuses_a_sheet_with_too_many_rows(tmp_path):
    from gaik.software_components.parsers.spreadsheet_parser import SpreadsheetParser
    from openpyxl import Workbook

    path = tmp_path / "rows.xlsx"
    workbook = Workbook()
    for i in range(10):
        workbook.active.append([f"r{i}", i])
    workbook.save(path)

    with pytest.raises(InputLimitError, match="rows.xlsx / Sheet"):
        SpreadsheetParser(limits=InputLimits(max_table_rows=9)).parse_spreadsheet(path)


def test_text_rag_parser_refuses_a_pdf_with_too_many_pages(tmp_path):
    pytest.importorskip("langchain_core")
    from gaik.software_modules.RAG_workflow.text_parser import TextRagParser

    pdf = _pdf(tmp_path / "manual.pdf", pages=3)

    with pytest.raises(InputLimitError, match="max_pages"):
        TextRagParser(limits=InputLimits(max_pages=2)).convert_doc_to_chunks(pdf)


# -- vision parsers: no model call for a file over a limit ------------------------


def _vision_parser(monkeypatch, **kwargs):
    from gaik.software_components.parsers.vision import OpenAIConfig, VisionParser

    calls = []
    monkeypatch.setattr(VisionParser, "_initialize_client", lambda self: object())
    monkeypatch.setattr(
        VisionParser,
        "_parse_image",
        lambda self, image, page, previous_context, **kw: calls.append(page) or f"page {page}",
    )
    parser = VisionParser(OpenAIConfig(model="m", use_azure=False, api_key="k"), **kwargs)
    return parser, calls


def test_vision_parser_refuses_a_pdf_with_too_many_pages_before_any_model_call(
    tmp_path, monkeypatch
):
    parser, calls = _vision_parser(monkeypatch, limits=InputLimits(max_pages=2))
    pdf = _pdf(tmp_path / "scan.pdf", pages=3)

    with pytest.raises(InputLimitError, match="max_pages"):
        parser.convert_pdf(str(pdf))
    assert calls == []


def test_vision_parser_refuses_a_page_too_large_to_render(tmp_path, monkeypatch):
    parser, calls = _vision_parser(monkeypatch, limits=InputLimits(max_image_pixels=1_000_000))
    pdf = _pdf(tmp_path / "poster.pdf", pages=1, width=2_000, height=2_000)

    with pytest.raises(InputLimitError, match="page 1 at 200 DPI"):
        parser.convert_pdf(str(pdf), dpi=200)
    assert calls == []


def test_vision_parser_first_pages_converts_only_those_pages(tmp_path, monkeypatch):
    parser, calls = _vision_parser(monkeypatch, limits=InputLimits(max_pages=1))
    pdf = _pdf(tmp_path / "long.pdf", pages=5)

    assert parser.convert_pdf(str(pdf), clean_output=False, first_pages=1) == ["page 1"]
    assert calls == [1]


def test_vision_parser_refuses_an_image_over_the_pixel_limit(tmp_path, monkeypatch):
    parser, calls = _vision_parser(monkeypatch, limits=InputLimits(max_image_pixels=10_000))
    image = _png(tmp_path / "photo.png", 200, 200)

    with pytest.raises(InputLimitError, match="max_image_pixels"):
        parser.convert_image(image)
    assert calls == []


def test_shared_vision_content_refuses_a_page_too_large_to_render(tmp_path):
    from gaik.software_components.parsers.multimodal_parser.chat_content import (
        build_chat_document_content,
    )

    pdf = _pdf(tmp_path / "poster.pdf", pages=1, width=3_000, height=3_000)

    with pytest.raises(InputLimitError, match="poster.pdf, page 1"):
        build_chat_document_content([pdf], "prompt", limits=InputLimits(max_image_pixels=10**6))


def test_multimodal_parser_refuses_a_pdf_with_too_many_pages_before_the_call(tmp_path, monkeypatch):
    from gaik.software_components.parsers.multimodal_parser import MultimodalParser

    parser = MultimodalParser(
        api_config={"provider": "openai", "model": "m", "api_key": "k"},
        limits=InputLimits(max_pages=2),
    )
    monkeypatch.setattr(parser, "_call_shared", lambda *a: pytest.fail("model was called"))
    pdf = _pdf(tmp_path / "long.pdf", pages=3)

    with pytest.raises(InputLimitError, match="max_pages"):
        parser.parse(pdf)


def test_vision_extractor_counts_the_pages_of_all_files_before_the_call(tmp_path, monkeypatch):
    from gaik.software_components.vision_extractor import VisionExtractor

    extractor = VisionExtractor(
        api_config={"provider": "openai", "model": "m", "api_key": "k"},
        limits=InputLimits(max_pages=4),
    )
    monkeypatch.setattr(extractor, "_call_shared", lambda *a: pytest.fail("model was called"))
    files = [
        _pdf(tmp_path / "a.pdf", pages=2),
        _pdf(tmp_path / "b.pdf", pages=2),
        _png(tmp_path / "c.png", 10, 10),
    ]

    with pytest.raises(InputLimitError) as caught:
        extractor.suggest_requirements(file_paths=files)
    assert (caught.value.limit, caught.value.actual) == ("max_pages", 5)


def test_vision_extractor_refuses_an_image_over_the_pixel_limit(tmp_path, monkeypatch):
    from gaik.software_components.vision_extractor import VisionExtractor

    extractor = VisionExtractor(
        api_config={"provider": "openai", "model": "m", "api_key": "k"},
        limits=InputLimits(max_image_pixels=100),
    )
    monkeypatch.setattr(extractor, "_call_shared", lambda *a: pytest.fail("model was called"))

    with pytest.raises(InputLimitError, match="max_image_pixels"):
        extractor.suggest_requirements(file_paths=[_png(tmp_path / "c.png", 20, 20)])


# -- Docling-based parsers --------------------------------------------------------


class _FakeConverter:
    def __init__(self, document=None):
        self.calls = []
        self.document = document

    def convert(self, source, **kwargs):
        self.calls.append((source, kwargs))
        return SimpleNamespace(document=self.document)


def test_docling_rag_parser_refuses_a_long_pdf_before_docling_reads_it(tmp_path):
    pytest.importorskip("docling")
    from gaik.software_components.RAG.rag_parser_docling.parser import DoclingRagParser

    parser = DoclingRagParser.__new__(DoclingRagParser)
    parser.limits = InputLimits(max_pages=2)
    parser.converter = _FakeConverter()

    with pytest.raises(InputLimitError, match="max_pages"):
        parser._convert(str(_pdf(tmp_path / "long.pdf", pages=3)))
    assert parser.converter.calls == []

    parser._convert(str(_pdf(tmp_path / "short.pdf", pages=2)))
    assert parser.converter.calls[0][1]["max_num_pages"] == 2


def _picture(page: int, size: tuple[int, int]):
    image = Image.new("RGB", size)
    item = SimpleNamespace(label="picture", image=image, prov=[SimpleNamespace(page_no=page)])
    return item


def test_vision_rag_parser_refuses_too_many_images_before_describing_any(tmp_path):
    pytest.importorskip("docling")
    from gaik.software_components.RAG.rag_parser_vision.parser import VisionRagParser

    document = SimpleNamespace(
        pages=[1],
        iterate_items=lambda: [(_picture(1, (10, 10)), 0) for _ in range(3)],
    )
    parser = VisionRagParser.__new__(VisionRagParser)
    parser.limits = InputLimits(max_images=2)
    parser.verbose = False
    parser.converter = _FakeConverter(document)
    parser._describe_images = lambda images: pytest.fail("vision model was called")

    with pytest.raises(InputLimitError) as caught:
        parser._convert_with_vision(str(_pdf(tmp_path / "charts.pdf", pages=1)))
    assert (caught.value.limit, caught.value.actual) == ("max_images", 3)


def test_vision_plus_parser_refuses_an_embedded_image_over_the_pixel_limit(tmp_path):
    pytest.importorskip("docling")
    from gaik.software_components.parsers.visionPlus import VisionPlusParser

    document = SimpleNamespace(pages=[1], iterate_items=lambda: [(_picture(1, (300, 300)), 0)])
    parser = VisionPlusParser.__new__(VisionPlusParser)
    parser.limits = InputLimits(max_image_pixels=10_000)
    parser.verbose = False
    parser.converter = _FakeConverter(document)
    parser._describe_images = lambda images: pytest.fail("vision model was called")

    with pytest.raises(InputLimitError, match="image 1"):
        parser.parse_document(str(_pdf(tmp_path / "charts.pdf", pages=1)))


# -- components built on the parsers -------------------------------------------------


def test_classifier_keeps_the_limit_error_instead_of_wrapping_it(tmp_path, monkeypatch):
    from gaik.software_components.doc_classifier import classifier

    monkeypatch.setattr(classifier, "build_compat_client", lambda config: object())
    instance = classifier.DocumentClassifier({"model": "m"}, limits=InputLimits(max_pages=1))
    monkeypatch.setattr(instance, "_classify_with_llm", lambda *a: pytest.fail("model called"))
    pdf = _pdf(tmp_path / "contract.pdf", pages=2)

    with pytest.raises(InputLimitError, match="max_pages"):
        instance._classify_single_file(str(pdf), ["contract", "unknown"], None)


def test_classifier_vision_path_reads_only_the_first_page(tmp_path, monkeypatch):
    from gaik.software_components.doc_classifier import classifier

    calls = {}

    class FakeVisionParser:
        def __init__(self, openai_config, limits):
            calls["limits"] = limits

        def convert_pdf(self, path, **kwargs):
            calls["kwargs"] = kwargs
            return ["first page"]

    monkeypatch.setattr(classifier, "build_compat_client", lambda config: object())
    monkeypatch.setattr(classifier, "VisionParser", FakeVisionParser)
    instance = classifier.DocumentClassifier({"model": "m"})
    pdf = _pdf(tmp_path / "scan.pdf", pages=3)

    assert instance._extract_text(str(pdf), "vision") == "first page"
    assert calls["kwargs"]["first_pages"] == 1
    assert calls["kwargs"]["clean_output"] is False
    assert calls["limits"] is instance.limits


def test_source_normalizer_checks_every_file_before_converting_any(tmp_path, monkeypatch):
    from gaik.software_components.source_normalizer import SourceNormalizer

    small = tmp_path / "notes.txt"
    small.write_text("short note")
    big = _pdf(tmp_path / "big.pdf", pages=3)
    normalizer = SourceNormalizer(limits=InputLimits(max_pages=2))
    monkeypatch.setattr(normalizer, "_convert", lambda path: pytest.fail("converted"))

    with pytest.raises(InputLimitError, match="big.pdf"):
        normalizer.normalize([small, big])


# -- transcribers ----------------------------------------------------------------------


class _FakeAudio:
    def __init__(self, seconds: float) -> None:
        self.ms = int(seconds * 1000)

    def __len__(self) -> int:
        return self.ms


def _transcriber(**kwargs):
    from gaik.software_components.transcriber.transcriber import Transcriber

    return Transcriber(
        {"use_azure": False, "api_key": "test-key"},
        transcription_model="gpt-4o-transcribe",
        **kwargs,
    )


def test_transcriber_refuses_a_file_over_the_size_limit(tmp_path):
    audio = tmp_path / "meeting.mp3"
    audio.write_bytes(b"\x00" * 2_000)
    transcriber = _transcriber(output_dir=tmp_path / "w", limits=InputLimits(max_media_bytes=1_000))

    with patch.object(transcriber, "_transcribe_input_remote") as remote:
        with pytest.raises(InputLimitError, match="max_media_bytes"):
            transcriber.transcribe(audio)
    remote.assert_not_called()


def test_transcriber_refuses_a_recording_longer_than_the_limit(tmp_path, monkeypatch):
    audio = tmp_path / "meeting.mp3"
    audio.write_bytes(b"\x00" * 64)
    transcriber = _transcriber(output_dir=tmp_path / "w", limits=InputLimits(max_media_seconds=60))
    monkeypatch.setattr(input_limits, "probe_media_seconds", lambda path, timeout: 61.0)

    with patch.object(transcriber, "_transcribe_input_remote") as remote:
        with pytest.raises(InputLimitError, match="max_media_seconds"):
            transcriber.transcribe(audio)
    remote.assert_not_called()


def test_transcriber_uses_the_decoded_length_when_the_probe_cannot_read_it(tmp_path, monkeypatch):
    audio = tmp_path / "meeting.mp3"
    audio.write_bytes(b"\x00" * 64)
    transcriber = _transcriber(output_dir=tmp_path / "w", limits=InputLimits(max_media_seconds=60))
    monkeypatch.setattr(input_limits, "probe_media_seconds", lambda path, timeout: None)

    with (
        patch(
            "gaik.software_components.transcriber.transcriber.AudioSegment.from_file",
            return_value=_FakeAudio(seconds=90),
        ),
        patch.object(transcriber, "_transcribe_input_remote") as remote,
    ):
        with pytest.raises(InputLimitError, match="max_media_seconds"):
            transcriber.transcribe(audio)
    remote.assert_not_called()


def test_video_audio_extraction_has_a_timeout(tmp_path, monkeypatch):
    from gaik.software_components.transcriber import whisper_local

    def slow_run(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd, kwargs["timeout"])

    monkeypatch.setattr(whisper_local.shutil, "which", lambda _name: "/usr/bin/ffmpeg")
    monkeypatch.setattr(whisper_local.subprocess, "run", slow_run)

    with pytest.raises(RuntimeError, match="longer than 3 s"):
        whisper_local.extract_audio_from_video(tmp_path / "clip.mp4", timeout=3)


def test_parallel_transcriber_refuses_a_long_recording_before_extracting_audio(
    tmp_path, monkeypatch
):
    from gaik.software_components.parallel_transcriber import ParallelTranscriber, pipeline

    video = tmp_path / "lecture.mp4"
    video.write_bytes(b"\x00" * 64)
    transcriber = ParallelTranscriber(
        {"use_azure": False, "api_key": "k"}, limits=InputLimits(max_media_seconds=3600)
    )
    monkeypatch.setattr(input_limits, "probe_media_seconds", lambda path, timeout: 7 * 3600.0)
    monkeypatch.setattr(pipeline, "has_video_stream", lambda _p: pytest.fail("probed streams"))

    with pytest.raises(InputLimitError, match="max_media_seconds"):
        transcriber.transcribe(video)


def test_parallel_transcriber_checks_the_measured_length_before_chunking(tmp_path, monkeypatch):
    from gaik.software_components.parallel_transcriber import ParallelTranscriber, pipeline
    from gaik.software_components.parallel_transcriber.config import TranscriptionConfig

    audio = tmp_path / "long.mp3"
    audio.write_bytes(b"\x00" * 64)
    transcriber = ParallelTranscriber(
        {"use_azure": False, "api_key": "k"},
        TranscriptionConfig(max_single_file_mb=0.00001),
        limits=InputLimits(max_media_seconds=3600),
    )
    monkeypatch.setattr(input_limits, "probe_media_seconds", lambda path, timeout: None)
    monkeypatch.setattr(pipeline, "has_video_stream", lambda _p: False)
    monkeypatch.setattr(pipeline, "has_audio_stream", lambda _p: True)
    monkeypatch.setattr(pipeline, "get_audio_duration", lambda _p: 2 * 3600.0)
    monkeypatch.setattr(pipeline, "split_audio", lambda *a, **k: pytest.fail("chunked"))

    with pytest.raises(InputLimitError, match="max_media_seconds"):
        transcriber.transcribe(audio)


def test_audio_duration_probe_has_a_timeout(tmp_path, monkeypatch):
    from gaik.software_components.parallel_transcriber import ffmpeg

    seen = {}

    def run(cmd, **kwargs):
        seen.update(kwargs)
        return SimpleNamespace(stdout="1.5\n")

    audio = tmp_path / "a.mp3"
    audio.write_bytes(b"\x00")
    monkeypatch.setattr(ffmpeg.subprocess, "run", run)

    assert ffmpeg.get_audio_duration(audio) == 1.5
    assert seen["timeout"] == ffmpeg.FFPROBE_TIMEOUT_SECONDS


# -- tabular agent ------------------------------------------------------------------------


def test_tabular_agent_refuses_a_file_over_the_size_limit_when_created(tmp_path):
    pytest.importorskip("duckdb")
    from gaik.software_components.tabular_agent import TabularAgent

    path = tmp_path / "sales.csv"
    path.write_text("region,amount\n" + "north,1\n" * 200)

    with pytest.raises(InputLimitError, match="max_file_bytes"):
        TabularAgent(path, limits=InputLimits(max_file_bytes=100))


def test_tabular_agent_refuses_a_csv_with_too_many_rows(tmp_path):
    pytest.importorskip("duckdb")
    from gaik.software_components.tabular_agent import TabularAgent

    path = tmp_path / "sales.csv"
    path.write_text("region,amount\n" + "".join(f"r{i},{i}\n" for i in range(6)))

    with TabularAgent(path, limits=InputLimits(max_table_rows=5)) as agent:
        with pytest.raises(InputLimitError, match="max_table_rows"):
            agent.table_names  # noqa: B018 - loading happens on first use
    with TabularAgent(path, limits=InputLimits(max_table_rows=6)) as agent:
        assert agent.run_sql("SELECT count(*) AS n FROM sales") == [{"n": 6}]


def test_tabular_agent_refuses_a_sheet_with_too_many_rows(tmp_path):
    pytest.importorskip("duckdb")
    from gaik.software_components.tabular_agent import TabularAgent
    from openpyxl import Workbook

    path = tmp_path / "sales.xlsx"
    workbook = Workbook()
    workbook.active.append(["region", "amount"])
    for i in range(6):
        workbook.active.append([f"r{i}", i])
    workbook.save(path)

    with TabularAgent(path, limits=InputLimits(max_table_rows=6)) as agent:
        with pytest.raises(InputLimitError, match="sales.xlsx / Sheet"):
            agent.table_names  # noqa: B018 - loading happens on first use


def test_tabular_agent_writes_sheet_rows_to_a_private_directory(tmp_path, monkeypatch):
    pytest.importorskip("duckdb")
    import os
    import stat
    import tempfile

    from gaik.software_components.tabular_agent import TabularAgent, loader
    from openpyxl import Workbook

    path = tmp_path / "sales.xlsx"
    workbook = Workbook()
    workbook.active.append(["region", "amount"])
    workbook.active.append(["north", 1])
    workbook.save(path)

    made = []
    real = tempfile.TemporaryDirectory

    def recording(*args, **kwargs):
        directory = real(*args, **kwargs)
        made.append((directory.name, stat.S_IMODE(os.stat(directory.name).st_mode)))
        return directory

    monkeypatch.setattr(loader.tempfile, "TemporaryDirectory", recording)
    with TabularAgent(path) as agent:
        assert agent.table_names

    assert made and all(mode == 0o700 for _, mode in made)
    assert not any(os.path.exists(name) for name, _ in made)
