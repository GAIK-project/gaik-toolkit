"""Inputs and outputs of the report generators (issues #145 and #199), offline."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from gaik.software_components.knowledge_curator.models import KnowledgeBase, SectionKnowledge
from gaik.software_components.report_synthesizer.models import Report
from gaik.software_modules.multi_source_report_generator import pipeline as msrg
from gaik.software_modules.multi_source_report_generator.agentic.reviewer import (
    Correction,
    _apply_corrections,
    _find_search_string,
)
from gaik.software_modules.report_writer.spec import ReportSpec

_PASSAGE = "The roof membrane was replaced in 2019 after a leak over the stairwell."


def _gen() -> msrg.MultiSourceReportGenerator:
    return msrg.MultiSourceReportGenerator(
        api_config={"use_azure": False, "api_key": "x", "model": "m"}
    )


# -- #145 item 1: a loose reviewer match never lands on a shifted span --------


@pytest.mark.parametrize("offset", range(0, 80, 3))
@pytest.mark.parametrize(
    "search",
    [
        _PASSAGE.replace("roof ", "roof  "),  # a double space
        _PASSAGE.replace("membrane", "membrame"),  # a one-letter typo
        _PASSAGE.replace("membrane", "membrne"),  # a letter left out
        _PASSAGE.replace("membrane", "membrrane"),  # a letter added
        _PASSAGE.replace("stairwell", "stairwel"),  # one of a double letter left out
        _PASSAGE.upper(),
    ],
)
def test_a_loose_edit_replaces_exactly_its_passage(offset, search):
    text = "x" * offset + "Intro. " + _PASSAGE + " Outro sentence follows here."
    new, done, failed = _apply_corrections(
        text, [Correction(search=search, replace="REPLACED.", reason="r")]
    )
    assert not failed
    assert done[0]["search"] == _PASSAGE
    assert new == "x" * offset + "Intro. REPLACED. Outro sentence follows here."


@pytest.mark.parametrize("search", ["X" + _PASSAGE[1:], _PASSAGE[:-1] + "!", _PASSAGE + "!"])
def test_a_fuzzy_edit_never_lands_beside_its_passage(search):
    # A difference in the first or last character fits the passage with or without the
    # character next to it equally well.
    text = "Intro. " + _PASSAGE + " Outro."
    assert _find_search_string(text, search) in (None, _PASSAGE)


def test_a_loose_edit_keeps_the_space_at_its_end():
    assert _find_search_string("Apple pie. Pineapple.", "apple ") == "Apple "
    new, _, failed = _apply_corrections(
        "Apple pie.", [Correction(search="apple ", replace="Pear ", reason="r")]
    )
    assert new == "Pear pie." and not failed


def test_a_loose_edit_ignores_quote_and_dash_styles():
    text = "He said “yes” — then left the building."
    new, done, _ = _apply_corrections(
        text, [Correction(search='he said "yes" - then left', replace="He agreed", reason="r")]
    )
    assert new == "He agreed the building." and done


def test_a_loose_edit_that_fits_two_spans_is_left_unresolved():
    text = f"{_PASSAGE}\n\n{_PASSAGE.replace('2019', '2020')}"
    search = _PASSAGE.replace("2019", "2021")
    new, done, failed = _apply_corrections(
        text, [Correction(search=search, replace="X", reason="r")]
    )
    assert new == text and not done and len(failed) == 1


def test_a_fuzzy_edit_is_refused_when_a_second_span_also_fits():
    first = "The roof membrane was replaced in 2019 after a leak."
    text = f"{first} Later: The roof membrane was replaced in 2018 after a leaks."
    search = "The roof membrane was replaced in 2017 after a leak."
    assert _find_search_string(text, search) is None


# -- #145 item 2: .xls is refused before any source is read -------------------


def test_an_xls_source_is_refused_before_anything_is_read(tmp_path):
    (tmp_path / "a_notes.txt").write_text("notes", encoding="utf-8")
    (tmp_path / "b_old.xls").write_bytes(b"\xd0\xcf\x11\xe0")
    with pytest.raises(ValueError, match=r"b_old\.xls.*save it as \.xlsx"):
        msrg._collect_input_files([tmp_path])
    assert ".xls" not in msrg.SUPPORTED_EXTENSIONS


# -- #145 item 3: docling's text_content is the evidence ----------------------


def test_docling_text_content_is_used_as_markdown():
    result = {"file_path": "report.pdf", "text_content": "# Report\n\nBody."}
    assert msrg._coerce_markdown(result) == "# Report\n\nBody."


# -- #145 item 4: DOCX keeps headings, order and empty cells ------------------


def test_docx_source_keeps_headings_order_and_empty_cells(tmp_path):
    docx = pytest.importorskip("docx")
    doc = docx.Document()
    doc.add_heading("Costs", level=1)
    doc.add_paragraph("Costs by year.")
    table = doc.add_table(rows=2, cols=3)
    for cell, value in zip(table.rows[0].cells, ["Item", "Year", "Cost"], strict=True):
        cell.text = value
    for cell, value in zip(table.rows[1].cells, ["Roof", "", "4500"], strict=True):
        cell.text = value
    doc.add_heading("Next steps", level=1)
    doc.add_paragraph("Inspect the wall.")
    path = tmp_path / "costs.docx"
    doc.save(path)

    text = _gen()._parse_docx(path)
    assert "# Costs" in text and "# Next steps" in text
    assert text.index("4500") < text.index("Next steps")
    assert "| Roof |  | 4500 |" in text


# -- #145 item 8: CSV/XLSX cells with '|' or a line break stay in their cell --


def test_table_cells_with_pipes_and_line_breaks_stay_in_place():
    rows = [["Item", "Note"], ["Roof", "Repaired 2019 | partial"], ["Wall", "line one\nline two"]]
    lines = msrg._rows_to_markdown_table(rows).splitlines()
    assert len(lines) == 4
    assert lines[2] == "| Roof | Repaired 2019 \\| partial |"
    assert lines[3] == "| Wall | line one line two |"


# -- #145 also seen (a): a section id with ':' is refused up front ------------


def test_a_section_id_with_a_colon_is_refused():
    for bad in ("risks:2026", "risks|2026"):
        with pytest.raises(ValueError, match="must not contain"):
            msrg._normalize_sections([{"title": "Risks", "id": bad}])
    assert msrg._normalize_sections([{"title": "Risks", "id": "risks 2026/a"}])[0].id


# -- #145 also seen (b): ReportSpec.save with a source on another drive -------


def test_spec_save_names_a_source_on_another_drive(tmp_path, monkeypatch):
    spec = ReportSpec(
        title="T",
        sections=[{"id": "s", "title": "S"}],
        sources={"primary": [tmp_path / "notes.txt"]},
    )

    def other_drive(*_args, **_kwargs):
        raise ValueError("path is on mount 'Z:', start on mount 'C:'")

    monkeypatch.setattr(os.path, "relpath", other_drive)
    with pytest.raises(msrg.SourcePathError, match="notes.txt is on another drive"):
        spec.save(tmp_path / "spec.json")


# -- #145 also seen (c): files saved with a UTF-8 BOM load --------------------


def test_spec_knowledge_and_report_files_with_a_bom_load(tmp_path):
    (tmp_path / "notes.txt").write_text("n", encoding="utf-8")
    spec = ReportSpec(
        title="T",
        sections=[{"id": "s", "title": "S"}],
        sources={"primary": [tmp_path / "notes.txt"]},
    )
    path = spec.save(tmp_path / "spec.json")
    path.write_text(path.read_text(encoding="utf-8"), encoding="utf-8-sig")
    assert ReportSpec.load(path).title == "T"

    knowledge = tmp_path / "knowledge"
    knowledge.mkdir()
    (knowledge / "s.json").write_text(
        SectionKnowledge(section_id="s", units=[], missing=[], conflicts=[]).model_dump_json(),
        encoding="utf-8-sig",
    )
    assert KnowledgeBase.load(knowledge).sections[0].section_id == "s"

    report = tmp_path / "report"
    (report / "sections").mkdir(parents=True)
    (report / "report.md").write_text("# Title\n\n## S\n\nBody.\n", encoding="utf-8-sig")
    (report / "sections" / "01_s.md").write_text("## S\n\nBody.\n", encoding="utf-8-sig")
    (report / "review_log.json").write_text("{}", encoding="utf-8-sig")
    loaded = Report.load(report)
    assert loaded.title == "Title"
    assert loaded.sections[0].title == "S"


# -- #145 also seen (d): a reused output_dir drops the previous run's files ---


def test_a_reused_output_dir_keeps_only_this_runs_files(tmp_path):
    gen = _gen()
    out = tmp_path / "out"

    def write(titles, usage):
        sections = [msrg.GeneratedSection(title=t, content_markdown="Body.") for t in titles]
        gen._write_outputs(
            out,
            report_title="R",
            markdown="# R",
            sections=sections,
            evidence_items=[],
            evidence_pack="",
            usage=usage,
            include_evidence_index=not usage,
        )

    write(["Alpha", "Beta", "Gamma"], {})
    (out / "report.docx").write_bytes(b"old")
    write(["Alpha"], {"total_tokens": 1})

    assert sorted(p.name for p in (out / "sections").iterdir()) == ["01_alpha.md"]
    assert not (out / "evidence_index.json").exists()
    assert not (out / "report.docx").exists()
    assert (out / "usage.json").exists()


# -- #199 item 1: save_report_config writes what load_report_config reads -----


def _save(config: Path, **paths) -> Path:
    return msrg.save_report_config(
        config, sections=[{"title": "Summary", "instructions": "Summarize."}], **paths
    )


def test_save_report_config_refuses_a_path_outside_its_folder(tmp_path):
    (tmp_path / "inputs").mkdir()
    config = tmp_path / "configs" / "report.json"
    with pytest.raises(msrg.SourcePathError, match="outside the folder"):
        _save(config, input_paths=[tmp_path / "inputs"])
    with pytest.raises(msrg.SourcePathError, match="outside the folder"):
        _save(config, input_paths=[config.parent], output_dir=tmp_path / "out")
    assert not config.exists()


def _link_or_skip(link: Path, target: Path) -> None:
    try:
        link.symlink_to(target, target_is_directory=target.is_dir())
    except OSError:
        pytest.skip("symbolic links are not available")


def test_save_report_config_keeps_a_links_name_and_refuses_one_leading_out(tmp_path):
    inside = tmp_path / "configs"
    (inside / "real").mkdir(parents=True)
    _link_or_skip(inside / "alias", inside / "real")
    config = _save(inside / "report.json", input_paths=[inside / "alias"])
    assert json.loads(config.read_text(encoding="utf-8"))["input_paths"] == ["alias"]
    assert msrg.load_report_config(config)["input_paths"] == [(inside / "real").resolve()]

    (tmp_path / "elsewhere").mkdir()
    _link_or_skip(inside / "out_link", tmp_path / "elsewhere")
    with pytest.raises(msrg.SourcePathError, match="outside the folder"):
        _save(inside / "other.json", input_paths=[inside / "out_link"])
