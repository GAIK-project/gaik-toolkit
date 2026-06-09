"""Unit tests for the multi_source_report_generator module.

All tests run without external API calls: the LLM client is faked by
monkeypatching ``pipeline.create_llm_client``.
"""

from __future__ import annotations

import inspect

import pytest
from gaik.software_modules.multi_source_report_generator import (
    MultiSourceReportGenerator,
    ReportSectionSpec,
)
from gaik.software_modules.multi_source_report_generator import pipeline as msrg

# ---------------------------------------------------------------------------
# Fake LLM
# ---------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, text: str):
        self.text = text
        self.model = "fake"
        self.provider = "fake"
        self.usage = {"prompt_tokens": 2, "completion_tokens": 1, "total_tokens": 3}


class _FakeClient:
    def __init__(self):
        self.calls: list[tuple] = []

    def chat(self, messages, **kwargs):
        self.calls.append((messages, kwargs))
        # The whole report is written in ONE call. Reconstruct a full report from
        # the requested title + sections so tests can assert structure/splitting.
        user = messages[-1]["content"]
        title = "Report"
        titles: list[str] = []
        for line in user.splitlines():
            if line.startswith("Report title:"):
                title = line.split(":", 1)[1].strip()
            elif line.strip().startswith("1. Heading:") or ". Heading:" in line:
                titles.append(line.split("Heading:", 1)[1].strip())
        parts = [f"# {title}"]
        for t in titles:
            parts.append(f"## {t}")
            parts.append(f"Body for {t}.")
        return _FakeResponse("\n\n".join(parts))


@pytest.fixture
def fake_llm(monkeypatch):
    client = _FakeClient()
    monkeypatch.setattr(msrg, "create_llm_client", lambda config: client)
    return client


def _gen() -> MultiSourceReportGenerator:
    # Explicit api_config avoids loading real credentials.
    return MultiSourceReportGenerator(api_config={"use_azure": False, "api_key": "x", "model": "m"})


# ---------------------------------------------------------------------------
# Public API shape
# ---------------------------------------------------------------------------


def test_pipeline_import_and_construct():
    gen = MultiSourceReportGenerator(api_config={"use_azure": False, "api_key": "x", "model": "m"})
    assert gen is not None


def test_constructor_follows_gaik_convention():
    params = inspect.signature(MultiSourceReportGenerator.__init__).parameters
    assert set(params) - {"self"} == {"api_config", "use_azure"}


def test_run_is_public_method_without_input_sources():
    params = inspect.signature(MultiSourceReportGenerator.run).parameters
    assert "input_paths" in params
    assert "input_sources" not in params  # not part of V1 API


# ---------------------------------------------------------------------------
# Section normalization
# ---------------------------------------------------------------------------


def test_sections_normalize_from_dicts_and_dataclasses():
    specs = msrg._normalize_sections(
        [{"title": "A", "instructions": "do A"}, ReportSectionSpec("B", "do B")]
    )
    assert [s.title for s in specs] == ["A", "B"]
    assert all(isinstance(s, ReportSectionSpec) for s in specs)


def test_empty_sections_raise():
    with pytest.raises(ValueError):
        msrg._normalize_sections([])


def test_section_missing_title_raises():
    with pytest.raises(ValueError):
        msrg._normalize_sections([{"instructions": "no title"}])


# ---------------------------------------------------------------------------
# Input collection / routing
# ---------------------------------------------------------------------------


def test_folder_input_expands_recursively_and_filters(tmp_path):
    (tmp_path / "a.txt").write_text("alpha", encoding="utf-8")
    (tmp_path / "nested").mkdir()
    (tmp_path / "nested" / "b.md").write_text("# beta", encoding="utf-8")
    (tmp_path / "ignore.xyz").write_text("nope", encoding="utf-8")

    files = msrg._collect_input_files([tmp_path])
    names = {f.name for f in files}
    assert names == {"a.txt", "b.md"}  # .xyz filtered out


def test_empty_input_paths_raise():
    with pytest.raises(ValueError):
        msrg._collect_input_files([])


def test_missing_input_path_raises():
    with pytest.raises(FileNotFoundError):
        msrg._collect_input_files(["does/not/exist.txt"])


# ---------------------------------------------------------------------------
# Evidence building
# ---------------------------------------------------------------------------


def test_text_and_markdown_become_evidence_items(tmp_path):
    (tmp_path / "a.txt").write_text("alpha content", encoding="utf-8")
    (tmp_path / "b.md").write_text("# Beta", encoding="utf-8")
    gen = _gen()
    files = msrg._collect_input_files([tmp_path])
    items = [
        gen._build_evidence_item(
            f,
            index=i,
            parser_choice="auto",
            parser_options={},
            transcriber_options={},
            image_options={},
        )
        for i, f in enumerate(files, start=1)
    ]
    types = {it.source_type for it in items}
    assert types == {"text", "markdown"}
    assert any("alpha content" in it.content_markdown for it in items)


def test_evidence_pack_includes_source_metadata(tmp_path):
    (tmp_path / "doc.txt").write_text("hello", encoding="utf-8")
    gen = _gen()
    files = msrg._collect_input_files([tmp_path])
    items = [
        gen._build_evidence_item(
            files[0],
            index=1,
            parser_choice="auto",
            parser_options={},
            transcriber_options={},
            image_options={},
        )
    ]
    pack = gen._assemble_evidence_pack(items, max_evidence_chars=None)
    assert "Source 1: doc.txt" in pack
    assert "Type: text" in pack
    assert "hello" in pack


def test_evidence_truncation_respects_max_chars(tmp_path):
    (tmp_path / "big.txt").write_text("x" * 5000, encoding="utf-8")
    gen = _gen()
    files = msrg._collect_input_files([tmp_path])
    items = [
        gen._build_evidence_item(
            files[0],
            index=1,
            parser_choice="auto",
            parser_options={},
            transcriber_options={},
            image_options={},
        )
    ]
    pack = gen._assemble_evidence_pack(items, max_evidence_chars=200)
    assert len(pack) <= 200 + len("\n\n[... evidence truncated ...]")
    assert "evidence truncated" in pack


# ---------------------------------------------------------------------------
# Excel / CSV helpers
# ---------------------------------------------------------------------------


def test_csv_to_markdown_no_optional_deps(tmp_path):
    csv_path = tmp_path / "t.csv"
    csv_path.write_text("a,b\n1,2\n3,4\n", encoding="utf-8")
    md = msrg._csv_to_markdown(csv_path)
    assert "| a | b |" in md
    assert "| 1 | 2 |" in md
    assert "| --- | --- |" in md


def test_xlsx_helper_skips_or_parses(tmp_path):
    xlsx_path = tmp_path / "t.xlsx"
    try:
        from openpyxl import Workbook
    except ImportError:
        xlsx_path.write_bytes(b"not a real xlsx")
        md = msrg._xlsx_to_markdown(xlsx_path)
        assert "openpyxl not installed" in md
        return
    wb = Workbook()
    ws = wb.active
    ws.append(["h1", "h2"])
    ws.append([1, 2])
    wb.save(str(xlsx_path))
    md = msrg._xlsx_to_markdown(xlsx_path)
    assert "| h1 | h2 |" in md


# ---------------------------------------------------------------------------
# Image structured-extraction serialization
# ---------------------------------------------------------------------------


def test_dict_to_markdown_serializes_vision_extractor_output():
    md = msrg._dict_to_markdown({"observer_name": "Jane", "details": {"area": "roof"}})
    assert "**Observer Name:** Jane" in md
    assert "**Details:**" in md
    assert "```json" in md


# ---------------------------------------------------------------------------
# End-to-end with a fake LLM (no API)
# ---------------------------------------------------------------------------


def test_run_writes_report_and_sections(tmp_path, fake_llm):
    (tmp_path / "src.txt").write_text("Important fact: the sky is blue.", encoding="utf-8")
    out = tmp_path / "out"
    gen = _gen()
    result = gen.run(
        input_paths=[tmp_path / "src.txt"],
        sections=[
            {"title": "Background", "instructions": "Describe context."},
            {"title": "Findings", "instructions": "List findings."},
        ],
        report_title="My Report",
        output_dir=out,
    )

    # the whole report is written in a SINGLE call
    assert len(fake_llm.calls) == 1
    # result + files
    assert result.markdown_path == out / "report.md"
    assert (out / "report.md").exists()
    assert (out / "sections" / "01_background.md").exists()
    assert (out / "sections" / "02_findings.md").exists()
    assert (out / "evidence_index.json").exists()
    assert (out / "evidence" / "normalized_sources.md").exists()
    # content
    assert "# My Report" in result.markdown
    assert "## Background" in result.markdown
    assert "Body for Background." in result.markdown
    # per-section breakdown derived from the single report
    assert [s.title for s in result.sections] == ["Background", "Findings"]
    # usage from the single call
    assert result.usage.get("total_tokens") == 3


def test_sample_report_is_passed_as_format_template(tmp_path, fake_llm):
    (tmp_path / "src.txt").write_text("Fact: revenue rose 10%.", encoding="utf-8")
    sample = tmp_path / "sample.md"
    sample.write_text(
        "# Example\n## Overview\nShort intro.\n## Details\nBullet points.", encoding="utf-8"
    )

    _gen().run(
        input_paths=[tmp_path / "src.txt"],
        sections=[{"title": "Overview", "instructions": "Write the overview."}],
        sample_report_path=sample,
    )

    # the sample content reaches the LLM prompt as a style example
    assert len(fake_llm.calls) == 1
    user_prompt = fake_llm.calls[0][0][-1]["content"]
    assert "FORMAT REFERENCE" in user_prompt
    assert "## Details" in user_prompt
    assert "Bullet points." in user_prompt


def test_sample_report_unsupported_type_raises(tmp_path, fake_llm):
    (tmp_path / "src.txt").write_text("x", encoding="utf-8")
    bad_sample = tmp_path / "sample.xlsx"
    bad_sample.write_bytes(b"not supported as a sample")
    with pytest.raises(ValueError):
        _gen().run(
            input_paths=[tmp_path / "src.txt"],
            sections=[{"title": "A", "instructions": "a"}],
            sample_report_path=bad_sample,
        )


def test_run_empty_sections_raises(tmp_path, fake_llm):
    (tmp_path / "src.txt").write_text("x", encoding="utf-8")
    with pytest.raises(ValueError):
        _gen().run(input_paths=[tmp_path / "src.txt"], sections=[])


def test_run_no_supported_files_raises(tmp_path, fake_llm):
    (tmp_path / "x.unsupported").write_text("x", encoding="utf-8")
    with pytest.raises((ValueError, FileNotFoundError)):
        _gen().run(
            input_paths=[tmp_path / "x.unsupported"],
            sections=[{"title": "A", "instructions": "a"}],
        )


# ---------------------------------------------------------------------------
# VisionParser.convert_image (additive method)
# ---------------------------------------------------------------------------


def test_visionparser_convert_image(tmp_path, monkeypatch):
    pytest.importorskip("fitz")  # PyMuPDF, required to import vision.py
    pytest.importorskip("openai")
    from gaik.software_components.parsers.vision import VisionParser

    parser = VisionParser({"model": "gpt-4.1", "use_azure": False, "api_key": "x"})

    captured = {}

    def fake_parse_image(image_bytes, *, page, previous_context):
        captured["bytes"] = image_bytes
        captured["page"] = page
        captured["previous_context"] = previous_context
        return "IMAGE-MARKDOWN"

    monkeypatch.setattr(parser, "_parse_image", fake_parse_image)

    img = tmp_path / "x.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n")
    out = parser.convert_image(str(img))

    assert out == "IMAGE-MARKDOWN"
    assert captured["bytes"] == b"\x89PNG\r\n\x1a\n"
    assert captured["page"] == 1
    assert captured["previous_context"] is None
    # existing public API is unchanged
    assert hasattr(parser, "convert_pdf")
