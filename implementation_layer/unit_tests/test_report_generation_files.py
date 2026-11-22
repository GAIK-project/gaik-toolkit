"""Files the report modules read and write: ids, byte order marks, drives, reused folders.

Offline: the model client is a fake.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest
from gaik.software_components.knowledge_curator.models import KnowledgeBase, SectionSpec
from gaik.software_components.report_synthesizer import Report
from gaik.software_components.source_normalizer.paths import SourcePathError
from gaik.software_modules.multi_source_report_generator import (
    MultiSourceReportGenerator,
    load_report_config,
    save_report_config,
)
from gaik.software_modules.multi_source_report_generator import pipeline as msrg
from gaik.software_modules.report_writer import ReportSpec
from gaik.software_modules.report_writer import spec as spec_module

BOM = "﻿"


class _Response:
    def __init__(self, text: str):
        self.text = text
        self.usage = {"total_tokens": 3}


class _Client:
    """Writes the requested sections, or raises once ``fail`` is set."""

    def __init__(self):
        self.fail = False

    def chat(self, messages, **kwargs):
        if self.fail:
            raise RuntimeError("model unavailable")
        user = messages[-1]["content"]
        titles = [
            line.split("Heading:", 1)[1].strip()
            for line in user.splitlines()
            if ". Heading:" in line
        ]
        draft_title = next(
            (
                ln.split(":", 1)[1].strip()
                for ln in user.splitlines()
                if ln.startswith("Report section to write:")
            ),
            None,
        )
        if draft_title:
            return _Response(f"Body of {draft_title}.")
        return _Response("# R\n\n" + "\n\n".join(f"## {t}\n\nBody of {t}." for t in titles))

    def chat_parsed(self, messages, response_format, **kwargs):
        return response_format()


@pytest.fixture
def client(monkeypatch):
    fake = _Client()
    monkeypatch.setattr(msrg, "create_llm_client", lambda config: fake)
    return fake


def _gen() -> MultiSourceReportGenerator:
    return MultiSourceReportGenerator(api_config={"use_azure": False, "api_key": "x", "model": "m"})


# -- section ids in agentic mode -------------------------------------------------------


def test_agentic_mode_takes_section_ids_langgraph_reserves(tmp_path, client):
    pytest.importorskip("langgraph")
    (tmp_path / "notes.txt").write_text("The roof is old.", encoding="utf-8")
    result = _gen().run(
        input_paths=[tmp_path / "notes.txt"],
        sections=[
            {"id": "part:1", "title": "Roof", "instructions": "Describe the roof."},
            {"id": "a|b", "title": "Summary", "instructions": "Sum up.", "depends_on": ["part:1"]},
        ],
        report_title="R",
        agentic=True,
    )
    assert [s.title for s in result.sections] == ["Roof", "Summary"]
    assert "Body of Roof." in result.markdown


def test_single_call_mode_still_takes_any_section_id(tmp_path, client):
    (tmp_path / "notes.txt").write_text("The roof is old.", encoding="utf-8")
    result = _gen().run(
        input_paths=[tmp_path / "notes.txt"],
        sections=[{"id": "part:1", "title": "Roof", "instructions": "Describe the roof."}],
        report_title="R",
    )
    assert result.sections[0].title == "Roof"


# -- a UTF-8 byte order mark -----------------------------------------------------------


def test_files_saved_with_a_byte_order_mark_load(tmp_path):
    (tmp_path / "notes.txt").write_text("x", encoding="utf-8")
    spec = ReportSpec(
        title="T",
        sections=[SectionSpec(id="roof", title="Roof")],
        sources={"primary": [tmp_path / "notes.txt"]},
    )
    spec_path = spec.save(tmp_path / "report_spec.json")
    spec_path.write_text(BOM + spec_path.read_text(encoding="utf-8"), encoding="utf-8")
    assert ReportSpec.load(spec_path).title == "T"

    knowledge = tmp_path / "knowledge"
    knowledge.mkdir()
    (knowledge / "roof.json").write_text(
        BOM + json.dumps({"section_id": "roof", "units": [], "missing": [], "conflicts": []}),
        encoding="utf-8",
    )
    assert KnowledgeBase.load(knowledge).sections[0].section_id == "roof"

    report = tmp_path / "report"
    (report / "sections").mkdir(parents=True)
    (report / "report.md").write_text(BOM + "# T\n\n## Roof\n\nOld.\n", encoding="utf-8")
    (report / "sections" / "01_roof.md").write_text(BOM + "## Roof\n\nOld.\n", encoding="utf-8")
    (report / "review_log.json").write_text(BOM + "[]", encoding="utf-8")
    loaded = Report.load(report)
    assert loaded.title == "T" and loaded.sections[0].title == "Roof"

    config = save_report_config(
        tmp_path / "config.json", input_paths=[tmp_path / "notes.txt"], sections=[{"title": "A"}]
    )
    config.write_text(BOM + config.read_text(encoding="utf-8"), encoding="utf-8")
    assert load_report_config(config)["sections"] == [{"title": "A"}]


def test_a_text_source_with_a_byte_order_mark_has_no_stray_character(tmp_path):
    path = tmp_path / "notes.txt"
    path.write_text(BOM + "The roof is old.", encoding="utf-8")
    item = _gen()._build_evidence_item(
        path,
        index=1,
        parser_choice="auto",
        parser_options={},
        transcriber_options={},
        image_options={},
    )
    assert item.content_markdown == "The roof is old."


# -- ReportSpec.save on another drive ----------------------------------------------------


def test_spec_save_with_a_source_on_another_drive_names_the_file(tmp_path, monkeypatch):
    def relpath(path, start=None):
        raise ValueError("path is on mount 'D:', start on mount 'C:'")

    monkeypatch.setattr(spec_module.os.path, "relpath", relpath)
    spec = ReportSpec(
        title="T",
        sections=[SectionSpec(id="roof", title="Roof")],
        sources={"primary": [tmp_path / "survey.pdf"]},
    )
    with pytest.raises(
        SourcePathError,
        match=r"survey\.pdf is on another drive than the spec file report_spec\.json",
    ):
        spec.save(tmp_path / "report_spec.json")
    assert not (tmp_path / "report_spec.json").exists()


# -- a reused output folder -------------------------------------------------------------


def _run(tmp_path: Path, sections: list[str], **kwargs):
    return _gen().run(
        input_paths=[tmp_path / "notes.txt"],
        sections=[{"title": t, "instructions": "Write it."} for t in sections],
        report_title="R",
        output_dir=tmp_path / "out",
        **kwargs,
    )


def test_a_rerun_removes_only_its_own_unchanged_files_of_the_run_before(tmp_path, client, caplog):
    (tmp_path / "notes.txt").write_text("The roof is old.", encoding="utf-8")
    out = tmp_path / "out"
    _run(tmp_path, ["Roof", "Walls", "Windows"])
    assert sorted(p.name for p in (out / "sections").iterdir()) == [
        "01_roof.md",
        "02_walls.md",
        "03_windows.md",
    ]
    # Files the user owns, and one the user changed after the first run.
    (out / "sections" / "notes_to_self.md").write_text("Mine.", encoding="utf-8")
    (out / "my_summary.txt").write_text("Mine.", encoding="utf-8")
    (out / "sections" / "03_windows.md").write_text(
        "## Windows\n\nEdited by hand.\n", encoding="utf-8"
    )

    with caplog.at_level(logging.INFO, logger=msrg.__name__):
        _run(tmp_path, ["Roof"], include_evidence_index=False)

    names = sorted(p.name for p in (out / "sections").iterdir())
    assert names == ["01_roof.md", "03_windows.md", "notes_to_self.md"]
    assert (out / "sections" / "03_windows.md").read_text(encoding="utf-8").endswith("hand.\n")
    assert (out / "my_summary.txt").exists()
    assert not (out / "evidence_index.json").exists()
    assert (out / "report.md").exists() and (out / "usage.json").exists()
    assert "Removed 2 file(s)" in caplog.text
    assert "keeps 2 section or brief file(s)" in caplog.text
    assert "Kept 1 file(s) of the previous run that were changed" in caplog.text
    # Log lines name no file.
    assert "windows" not in caplog.text.lower() and "notes_to_self" not in caplog.text
    record = json.loads((out / msrg.OUTPUT_RECORD).read_text(encoding="utf-8"))
    assert sorted(record["files"]) == [
        "evidence/normalized_sources.md",
        "report.md",
        "sections/01_roof.md",
        "usage.json",
    ]


def test_a_failed_rerun_removes_nothing(tmp_path, client):
    (tmp_path / "notes.txt").write_text("The roof is old.", encoding="utf-8")
    out = tmp_path / "out"
    _run(tmp_path, ["Roof", "Walls"])
    before = sorted(p.relative_to(out).as_posix() for p in out.rglob("*") if p.is_file())
    client.fail = True
    with pytest.raises(RuntimeError):
        _run(tmp_path, ["Roof"])
    assert sorted(p.relative_to(out).as_posix() for p in out.rglob("*") if p.is_file()) == before


def test_a_rerun_without_a_record_removes_nothing(tmp_path, client):
    (tmp_path / "notes.txt").write_text("The roof is old.", encoding="utf-8")
    out = tmp_path / "out"
    _run(tmp_path, ["Roof", "Walls"])
    (out / msrg.OUTPUT_RECORD).unlink()  # as written by a gaik before the record
    _run(tmp_path, ["Roof"])
    assert (out / "sections" / "02_walls.md").exists()


def test_an_edited_record_cannot_remove_a_file_outside_the_folder(tmp_path, client):
    (tmp_path / "notes.txt").write_text("The roof is old.", encoding="utf-8")
    outside = tmp_path / "precious.txt"
    outside.write_text("keep", encoding="utf-8")
    out = tmp_path / "out"
    _run(tmp_path, ["Roof"])
    digest = msrg._digest(outside)
    (out / msrg.OUTPUT_RECORD).write_text(
        json.dumps({"files": {"../precious.txt": digest, str(outside): digest}}), encoding="utf-8"
    )
    _run(tmp_path, ["Roof"])
    assert outside.read_text(encoding="utf-8") == "keep"


def test_an_agentic_rerun_removes_an_unchanged_brief_it_did_not_write(tmp_path, client):
    pytest.importorskip("langgraph")
    (tmp_path / "notes.txt").write_text("The roof is old.", encoding="utf-8")
    out = tmp_path / "out"
    _run(tmp_path, ["Roof", "Walls"], agentic=True, curate_evidence=True)
    briefs = out / "evidence" / "curated_sections"
    assert sorted(p.name for p in briefs.iterdir()) == ["roof.md", "walls.md"]
    _run(tmp_path, ["Roof"], agentic=True, curate_evidence=True)
    assert sorted(p.name for p in briefs.iterdir()) == ["roof.md"]


# -- the default progress sink ------------------------------------------------------------


def test_the_default_progress_print_names_no_file(tmp_path, client, capsys):
    (tmp_path / "Matti_Virtanen_lab_results.txt").write_text("Values.", encoding="utf-8")
    _gen().run(
        input_paths=[tmp_path / "Matti_Virtanen_lab_results.txt"],
        sections=[{"title": "Summary", "instructions": "Sum up."}],
    )
    printed = capsys.readouterr().out
    assert "Normalizing [1/1]: file " in printed and ".txt (text)" in printed
    assert "Virtanen" not in printed


def test_a_progress_callback_still_gets_the_file_name(tmp_path, client):
    (tmp_path / "site_notes.txt").write_text("Values.", encoding="utf-8")
    messages: list[str] = []
    _gen().run(
        input_paths=[tmp_path / "site_notes.txt"],
        sections=[{"title": "Summary", "instructions": "Sum up."}],
        progress_callback=messages.append,
    )
    assert "Normalizing [1/1]: site_notes.txt (text)" in messages


# -- the record cannot remove a file this run wrote, or anything outside the folder ------


def _link_dir(link: Path, target: Path) -> None:
    """A link to a folder: a symbolic link, or a junction where Windows refuses one."""
    import os
    import sys

    try:
        os.symlink(target, link, target_is_directory=True)
    except OSError:
        if sys.platform != "win32":
            raise
        import _winapi

        _winapi.CreateJunction(str(target), str(link))


def _files(out: Path) -> dict[str, bytes]:
    return {
        p.relative_to(out).as_posix(): p.read_bytes()
        for p in out.rglob("*")
        if p.is_file() and p.name != msrg.OUTPUT_RECORD
    }


def test_another_spelling_in_the_record_never_removes_a_file_this_run_wrote(tmp_path, client):
    (tmp_path / "notes.txt").write_text("The roof is old.", encoding="utf-8")
    out = tmp_path / "out"
    _run(tmp_path, ["Roof"])
    before = _files(out)
    digests = {rel: msrg._digest(out / rel) for rel in before}
    aliases = {}
    for rel, digest in digests.items():
        for alias in (f"./{rel}", rel.upper(), rel.replace("/", "\\"), f"sections/../{rel}"):
            aliases[alias] = digest
    aliases["report.md\x00.txt"] = digests["report.md"]
    aliases[msrg.OUTPUT_RECORD] = "0" * 64
    (out / msrg.OUTPUT_RECORD).write_text(json.dumps({"files": aliases}), encoding="utf-8")

    result = _run(tmp_path, ["Roof"])

    assert _files(out) == before
    assert result.markdown_path.exists()
    assert (out / msrg.OUTPUT_RECORD).exists()


def test_the_record_removes_only_names_the_generator_writes(tmp_path, client):
    (tmp_path / "notes.txt").write_text("The roof is old.", encoding="utf-8")
    out = tmp_path / "out"
    _run(tmp_path, ["Roof"])
    (out / "my_summary.txt").write_text("Mine.", encoding="utf-8")
    (out / "evidence" / "extra.md").write_text("Mine.", encoding="utf-8")
    record = json.loads((out / msrg.OUTPUT_RECORD).read_text(encoding="utf-8"))
    record["files"]["my_summary.txt"] = msrg._digest(out / "my_summary.txt")
    record["files"]["evidence/extra.md"] = msrg._digest(out / "evidence" / "extra.md")
    (out / msrg.OUTPUT_RECORD).write_text(json.dumps(record), encoding="utf-8")

    _run(tmp_path, ["Roof"])

    assert (out / "my_summary.txt").exists() and (out / "evidence" / "extra.md").exists()


def test_the_record_cannot_remove_a_file_through_a_folder_linked_out(tmp_path, client):
    (tmp_path / "notes.txt").write_text("The roof is old.", encoding="utf-8")
    out = tmp_path / "out"
    _run(tmp_path, ["Roof"])
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / "keep.md").write_text("Precious.", encoding="utf-8")
    _link_dir(out / "evidence" / "curated_sections", elsewhere)
    record = json.loads((out / msrg.OUTPUT_RECORD).read_text(encoding="utf-8"))
    record["files"]["evidence/curated_sections/keep.md"] = msrg._digest(elsewhere / "keep.md")
    (out / msrg.OUTPUT_RECORD).write_text(json.dumps(record), encoding="utf-8")

    _run(tmp_path, ["Roof"])

    assert (elsewhere / "keep.md").read_text(encoding="utf-8") == "Precious."


def test_a_record_that_is_a_link_is_neither_read_nor_written(tmp_path, client, symlink):
    (tmp_path / "notes.txt").write_text("The roof is old.", encoding="utf-8")
    out = tmp_path / "out"
    _run(tmp_path, ["Roof", "Walls"])
    outside = tmp_path / "outside.json"
    outside.write_text((out / msrg.OUTPUT_RECORD).read_text(encoding="utf-8"), encoding="utf-8")
    (out / msrg.OUTPUT_RECORD).unlink()
    symlink(out / msrg.OUTPUT_RECORD, outside)
    kept = outside.read_text(encoding="utf-8")

    _run(tmp_path, ["Roof"])

    assert outside.read_text(encoding="utf-8") == kept
    assert (out / "sections" / "02_walls.md").exists()


def test_a_section_folder_in_another_case_gives_no_false_warning(tmp_path, client, caplog):
    (tmp_path / "notes.txt").write_text("The roof is old.", encoding="utf-8")
    out = tmp_path / "out"
    (out / "Sections").mkdir(parents=True)
    with caplog.at_level(logging.INFO, logger=msrg.__name__):
        _run(tmp_path, ["Roof"])
        _run(tmp_path, ["Roof"])
    assert "keeps" not in caplog.text and "Kept" not in caplog.text


def test_only_a_changed_file_is_reported_as_changed(tmp_path, client, caplog):
    (tmp_path / "notes.txt").write_text("The roof is old.", encoding="utf-8")
    out = tmp_path / "out"
    _run(tmp_path, ["Roof"])
    (out / "evidence_index.json").write_text("[]", encoding="utf-8")
    with caplog.at_level(logging.INFO, logger=msrg.__name__):
        _run(tmp_path, ["Roof"], include_evidence_index=False)
    assert (out / "evidence_index.json").read_text(encoding="utf-8") == "[]"
    assert "Kept 1 file(s) of the previous run that were changed" in caplog.text
    assert "keeps 0" not in caplog.text and "section or brief" not in caplog.text


def test_a_second_different_report_replaces_the_first_ones_generated_files(tmp_path, client):
    # One output folder holds one report, the one written last: a different report
    # written into it removes the first one's unchanged section files.
    (tmp_path / "notes.txt").write_text("The roof is old.", encoding="utf-8")
    out = tmp_path / "out"
    _run(tmp_path, ["Roof", "Walls"])
    (out / "sections" / "02_walls.md").write_text("## Walls\n\nMy edit.\n", encoding="utf-8")
    _run(tmp_path, ["Budget"])
    assert sorted(p.name for p in (out / "sections").iterdir()) == ["01_budget.md", "02_walls.md"]
    assert "## Budget" in (out / "report.md").read_text(encoding="utf-8")


def test_a_failed_agentic_rerun_keeps_the_earlier_report_and_removes_nothing(tmp_path, client):
    pytest.importorskip("langgraph")
    (tmp_path / "notes.txt").write_text("The roof is old.", encoding="utf-8")
    out = tmp_path / "out"
    _run(tmp_path, ["Roof", "Walls"], agentic=True, curate_evidence=True)
    report = (out / "report.md").read_bytes()
    names = sorted(_files(out))

    def failing_parsed(messages, response_format, **kwargs):
        raise RuntimeError("reviewer unavailable")

    client.chat_parsed = failing_parsed  # the curator writes its briefs, then review fails
    with pytest.raises(RuntimeError):
        _run(tmp_path, ["Roof"], agentic=True, curate_evidence=True)

    assert sorted(_files(out)) == names
    assert (out / "report.md").read_bytes() == report


def test_a_section_folder_in_another_case_is_still_cleaned_up(tmp_path, client):
    (tmp_path / "notes.txt").write_text("The roof is old.", encoding="utf-8")
    out = tmp_path / "out"
    (out / "Sections").mkdir(parents=True)
    _run(tmp_path, ["Roof", "Walls"])
    record = json.loads((out / msrg.OUTPUT_RECORD).read_text(encoding="utf-8"))
    assert "sections/02_walls.md" in record["files"]
    _run(tmp_path, ["Roof"])
    assert not (out / "sections" / "02_walls.md").exists()


def test_the_record_removes_nothing_through_a_folder_linked_inside_the_folder(tmp_path, client):
    (tmp_path / "notes.txt").write_text("The roof is old.", encoding="utf-8")
    out = tmp_path / "out"
    _run(tmp_path, ["Roof", "Walls"])
    (out / "sections").rename(out / "real_sections")
    _link_dir(out / "sections", out / "real_sections")

    _run(tmp_path, ["Roof"])

    assert (out / "real_sections" / "02_walls.md").exists()
