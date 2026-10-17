"""Offline tests of the generate-structured-reports skill's helper scripts.

The helper drives gaik's ReportWriter. Here `normalize` and `rebuild` are the real module
methods, which make no model call for text sources; `curate` and `synthesize` are replaced by a
fake that writes the same files the module writes. No test makes a network or model call.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
from pathlib import Path

import pytest

pytest.importorskip("gaik.software_modules.report_writer")
pymupdf = pytest.importorskip("pymupdf")

from gaik.software_components.draft_reviewer.models import Edit  # noqa: E402
from gaik.software_components.knowledge_curator.models import (  # noqa: E402
    Conflict,
    DroppedUnit,
    FactUnit,
    SectionKnowledge,
    SourceRef,
)
from gaik.software_components.report_synthesizer.models import (  # noqa: E402
    ReportSection,
    ReviewEntry,
)
from gaik.software_modules.report_writer import (  # noqa: E402
    KnowledgeBase,
    NormalizedSources,
    Report,
    ReportWriter,
)

SKILL_DIR = (
    Path(__file__).resolve().parents[1]
    / "no-code-assets"
    / "agent-skills"
    / "skills"
    / "generate-structured-reports"
)
SECRET = "sk-test-secret-0123456789"
CONFIG = {"provider": "azure", "model": "test-model", "api_key": SECRET}


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, SKILL_DIR / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


rr = _load("run_report")
REAL_LOAD_CONFIG = rr.load_config
tts = _load("template_to_spec")


class FakeWriter(ReportWriter):
    """The real normalize and rebuild; curate and synthesize write fixed files."""

    calls: list[tuple[str, bool | None]] = []

    def curate(self, spec, workspace, *, progress_callback=None):
        FakeWriter.calls.append(("curate", None))
        ws = Path(workspace)
        sources = NormalizedSources.load(ws / "normalized")
        first = sources.sources[0]
        quote = next(line for line in first.text.splitlines() if line.strip())
        sections = []
        for section in spec.sections:
            if section.depends_on:
                continue
            sections.append(
                SectionKnowledge(
                    section_id=section.id,
                    units=[
                        FactUnit(
                            id=f"{section.id}-01",
                            topic="fact",
                            time_qualifier=None,
                            summary=quote,
                            quote=quote,
                            source=SourceRef(file=first.file, locator=None),
                            source_class=first.source_class,
                            confidence="high",
                        )
                    ],
                    missing=list(section.required_items[1:]),
                    conflicts=[],
                )
            )
        knowledge = KnowledgeBase(
            sections=sections,
            usage={"prompt_tokens": 11},
            dropped=[
                DroppedUnit(
                    section_id=sections[0].section_id,
                    topic="t",
                    summary="s",
                    quote="not in any source",
                    file=first.file,
                    reason="quote not found in source",
                )
            ],
        )
        shutil.rmtree(ws / "knowledge", ignore_errors=True)
        knowledge.save(ws / "knowledge")
        return knowledge

    def synthesize(self, spec, workspace, *, progress_callback=None):
        FakeWriter.calls.append(("synthesize", spec.settings.docx))
        report = Report(
            title=spec.title,
            sections=[
                ReportSection(id=s.id, title=s.title, text=f"Text of {s.id}. (missing: x)")
                for s in spec.sections
            ],
            review_log=[
                ReviewEntry(
                    section_id=spec.sections[0].id,
                    applied=[],
                    unresolved=[Edit(search="Text", replace="T", reason="not found")],
                )
            ],
            usage={"total_tokens": 42},
        )
        # Like the module: save inside synthesize, Word export included when the spec asks.
        report.save(Path(workspace) / "report", docx=spec.settings.docx)
        return report

    def run(self, *args, **kwargs):  # the single-call route must be unreachable
        raise AssertionError("ReportWriter.run() was called")


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    FakeWriter.calls = []
    monkeypatch.setattr(rr, "load_config", lambda provider: dict(CONFIG))
    monkeypatch.setattr(rr, "make_writer", lambda config: FakeWriter(config))
    monkeypatch.setattr(rr, "pandoc_problem", lambda: None)


def write_spec(root: Path, **overrides) -> Path:
    inputs = root / "inputs"
    inputs.mkdir(parents=True, exist_ok=True)
    (inputs / "site_notes.txt").write_text(
        "The supply-air unit vibrates and the housing is rusty.\nRoof inspected 2024.\n",
        encoding="utf-8",
    )
    (inputs / "old_report.md").write_text(
        "# Renovation 1998\n\nMechanical ventilation installed in 1998.\n", encoding="utf-8"
    )
    spec = {
        "title": "Condition assessment",
        "language": "English",
        "sections": [
            {
                "id": "building_services",
                "title": "Building services",
                "instructions": "Ventilation, water and sewer.",
                "required_items": ["ventilation system and its age", "latest sewer inspection"],
            },
            {"id": "summary", "title": "Summary", "depends_on": ["building_services"]},
        ],
        "instructions": "No source has automatic priority.",
        "sources": {"primary": ["inputs/site_notes.txt", "inputs/old_report.md"]},
        "settings": {"docx": False},
    }
    spec.update(overrides)
    path = root / "report_spec.json"
    path.write_text(json.dumps(spec, indent=2), encoding="utf-8")
    return path


def run(capsys, *argv) -> tuple[int, dict]:
    code = rr.main([*argv, "--json"])
    out = capsys.readouterr().out
    return code, json.loads(out)


def cli(capsys, command, spec, ws, *extra):
    return run(capsys, command, "--spec", str(spec), "--workspace", str(ws), *extra)


def full_run(capsys, spec, ws, *extra):
    for command in ("normalize", "curate", "synthesize"):
        code, out = cli(capsys, command, spec, ws, *extra)
        assert code == 0, out
    return out


# ── Contract with gaik ───────────────────────────────────────────────


def test_source_types_match_the_normalizer():
    from gaik.software_components.source_normalizer import source_normalizer

    assert source_normalizer._TYPES == rr.SOURCE_TYPES


def test_helper_never_reaches_single_call_or_an_agentic_flag():
    # Inspect the calls themselves, not the wording: the docstring may name run() to say it
    # is never called. Behaviour is also covered: FakeWriter.run() raises in every test.
    import ast

    tree = ast.parse((SKILL_DIR / "scripts" / "run_report.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        assert not (isinstance(node.func, ast.Attribute) and node.func.attr == "run")
        for keyword in node.keywords:
            assert keyword.arg not in ("agentic", "use_agentic")
            if keyword.arg == "mode":  # model_dump(mode="json") is fine
                assert getattr(keyword.value, "value", None) != "single_call"


# ── A whole run ─────────────────────────────────────────────────────


def test_a_full_offline_run_keeps_what_the_module_does_not_save(tmp_path, capsys):
    spec, ws = write_spec(tmp_path), tmp_path / "ws"
    code, pre = cli(capsys, "preflight", spec, ws)
    assert code == 0 and not pre["errors"]

    out = full_run(capsys, spec, ws)

    assert ("synthesize", False) in FakeWriter.calls
    assert out["usage"] == {"total_tokens": 42}
    assert out["current"] is True
    assert out["export"] == {"status": "off"}
    assert out["missing_markers"] == 2
    assert out["unresolved_review_edits"] == {
        "building_services": [{"search": "Text", "reason": "not found"}]
    }
    curation = json.loads((ws / "diagnostics" / "curation.json").read_text(encoding="utf-8"))
    assert curation["usage"] == {"prompt_tokens": 11}
    assert curation["dropped"][0]["reason"] == "quote not found in source"
    # KnowledgeBase.load() reads every JSON file in knowledge/: diagnostics must not be there.
    assert sorted(p.name for p in (ws / "knowledge").iterdir()) == ["building_services.json"]
    assert KnowledgeBase.load(ws / "knowledge").dropped == []


def test_progress_goes_to_stderr_and_stdout_stays_json(tmp_path, capsys):
    spec, ws = write_spec(tmp_path), tmp_path / "ws"
    rr.main(["normalize", "--spec", str(spec), "--workspace", str(ws), "--json"])
    captured = capsys.readouterr()
    assert json.loads(captured.out)["ok"] is True


def test_a_stage_does_not_replace_its_output_unless_asked(tmp_path, capsys):
    spec, ws = write_spec(tmp_path), tmp_path / "ws"
    assert cli(capsys, "normalize", spec, ws)[0] == 0
    code, out = cli(capsys, "normalize", spec, ws)
    assert code == rr.EXIT_INPUT and out["error"]["category"] == "would-replace"
    assert cli(capsys, "normalize", spec, ws, "--replace")[0] == 0


# ── Word export ─────────────────────────────────────────────────────


def test_a_failed_word_export_keeps_the_report_and_its_usage(tmp_path, capsys, monkeypatch):
    import pypandoc

    def fail(*args, **kwargs):
        raise OSError(f"pandoc exploded with {SECRET}")

    monkeypatch.setattr(pypandoc, "convert_file", fail)
    spec, ws = write_spec(tmp_path, settings={"docx": True}), tmp_path / "ws"
    (ws / "report").mkdir(parents=True)
    (ws / "report" / "report.docx").write_bytes(b"an earlier run")

    out = full_run(capsys, spec, ws, "--replace")

    assert ("synthesize", False) in FakeWriter.calls  # export was split off
    assert out["usage"] == {"total_tokens": 42}
    assert out["export"]["status"] == "failed"
    assert SECRET not in out["export"]["reason"]
    assert (ws / "report" / "report.md").is_file()
    assert not (ws / "report" / "report.docx").exists()


def test_a_successful_word_export_goes_through_rebuild(tmp_path, capsys, monkeypatch):
    import pypandoc

    monkeypatch.setattr(
        pypandoc,
        "convert_file",
        lambda src, fmt, outputfile: Path(outputfile).write_bytes(b"docx"),
    )
    spec, ws = write_spec(tmp_path, settings={"docx": True}), tmp_path / "ws"
    out = full_run(capsys, spec, ws)
    assert out["export"]["status"] == "ok"
    assert (ws / "report" / "report.docx").read_bytes() == b"docx"


def test_missing_pandoc_blocks_synthesis_but_not_curation(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(rr, "pandoc_problem", lambda: "the Pandoc program is not installed")
    spec, ws = write_spec(tmp_path, settings={"docx": True}), tmp_path / "ws"
    assert cli(capsys, "preflight", spec, ws)[0] == rr.EXIT_INPUT
    assert cli(capsys, "normalize", spec, ws)[0] == 0
    assert cli(capsys, "curate", spec, ws)[0] == 0
    code, out = cli(capsys, "synthesize", spec, ws)
    assert code == rr.EXIT_INPUT and "Pandoc" in out["error"]["message"]
    assert ("synthesize", False) not in FakeWriter.calls


def test_rebuild_makes_no_model_call_and_warns(tmp_path, capsys):
    spec, ws = write_spec(tmp_path), tmp_path / "ws"
    full_run(capsys, spec, ws)
    calls = list(FakeWriter.calls)
    section = next((ws / "report" / "sections").glob("01_*.md"))
    section.write_text("## Building services\n\nEdited by hand.\n", encoding="utf-8")

    code, out = cli(capsys, "rebuild", spec, ws)

    assert code == 0 and FakeWriter.calls == calls
    assert "Edited by hand." in (ws / "report" / "report.md").read_text(encoding="utf-8")
    assert any("review log" in w for w in out["warnings"])


# ── Knowledge validation ────────────────────────────────────────────


def _edit_knowledge(ws: Path, change) -> None:
    path = ws / "knowledge" / "building_services.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    change(data)
    path.write_text(json.dumps(data), encoding="utf-8")


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        (lambda d: d["units"][0].update(quote="Words no source contains."), "quote not found"),
        (lambda d: d["units"].append(dict(d["units"][0])), "duplicate fact-unit ids"),
        (
            lambda d: d["conflicts"].append(
                Conflict(
                    topic="age", description="d", status="unresolved", unit_ids=["nope"]
                ).model_dump()
            ),
            "unknown units",
        ),
        (lambda d: d["units"][0].update(source_class="secondary"), "does not match the class"),
        (lambda d: d["units"][0]["source"].update(file="other.pdf"), "not a source"),
    ],
)
def test_edited_knowledge_is_checked_before_writing(tmp_path, capsys, change, expected):
    spec, ws = write_spec(tmp_path), tmp_path / "ws"
    for command in ("normalize", "curate"):
        assert cli(capsys, command, spec, ws)[0] == 0
    _edit_knowledge(ws, change)

    code, out = cli(capsys, "validate-knowledge", spec, ws)
    assert code == rr.EXIT_EVIDENCE
    assert any(expected in p for p in out["problems"]), out["problems"]

    code, out = cli(capsys, "synthesize", spec, ws)
    assert code == rr.EXIT_EVIDENCE
    assert not [c for c in FakeWriter.calls if c[0] == "synthesize"]


# ── Preflight ───────────────────────────────────────────────────────


def _pdf(path: Path, pages: list[str]) -> Path:
    doc = pymupdf.open()
    for text in pages:
        page = doc.new_page()
        if text:
            page.insert_text((72, 72), text)
    doc.save(path)
    return path


def test_preflight_catches_what_the_module_catches_late(tmp_path, capsys):
    spec_path = write_spec(
        tmp_path,
        sections=[
            {"id": "a", "title": "A", "depends_on": ["b"]},
            {"id": "b", "title": "B", "depends_on": ["a"]},
        ],
    )
    code, out = cli(capsys, "preflight", spec_path, tmp_path / "ws")
    assert code == rr.EXIT_INPUT
    assert any("cycle" in e for e in out["errors"])
    assert any("at least one section must be written" in e for e in out["errors"])


def test_preflight_checks_the_source_files(tmp_path, capsys, monkeypatch):
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    _pdf(inputs / "scan.pdf", ["", ""])
    _pdf(inputs / "mixed.pdf", ["A page with a real text layer on it.", ""])
    (inputs / "slides.pptx").write_bytes(b"x")
    (tmp_path / "other").mkdir()
    (tmp_path / "other" / "site_notes.txt").write_text("copy", encoding="utf-8")
    (inputs / "talk.mp3").write_bytes(b"x")
    spec_path = write_spec(
        tmp_path,
        sources={
            "primary": [
                "inputs/site_notes.txt",
                "other/site_notes.txt",
                "inputs/scan.pdf",
                "inputs/mixed.pdf",
                "inputs/slides.pptx",
                "inputs/talk.mp3",
            ]
        },
        instructions="",
        sections=[
            {"id": "s", "title": "S", "required_items": ["info", "the roof covering and its age"]}
        ],
    )
    monkeypatch.setattr(rr, "load_config", lambda provider: {**CONFIG, "provider": "anthropic"})
    code, out = cli(capsys, "preflight", spec_path, tmp_path / "ws", "--provider", "anthropic")

    assert code == rr.EXIT_INPUT
    errors, warnings = " | ".join(out["errors"]), " | ".join(out["warnings"])
    assert "site_notes.txt: listed more than once" in errors
    assert "scan.pdf: no page has a text layer" in errors
    assert "slides.pptx" in errors
    assert "Recordings need an OpenAI or Azure OpenAI provider" in errors
    assert "mixed.pdf: pages [2] have no text layer" in warnings
    assert "'info' is too vague" in warnings
    assert "report instructions are empty" in warnings


def test_preflight_rejects_a_sample_report_that_needs_a_model(tmp_path, capsys):
    (tmp_path / "sample.mp3").write_bytes(b"x")
    spec_path = write_spec(tmp_path, sample_report="sample.mp3")
    code, out = cli(capsys, "preflight", spec_path, tmp_path / "ws")
    assert code == rr.EXIT_INPUT
    assert any("sample report must be DOCX" in e for e in out["errors"])


# ── The per-stage run record ────────────────────────────────────────


def test_a_changed_source_stays_flagged_until_its_stage_is_rerun(tmp_path, capsys):
    spec, ws = write_spec(tmp_path), tmp_path / "ws"
    full_run(capsys, spec, ws)
    (tmp_path / "inputs" / "site_notes.txt").write_text("Changed notes.\n", encoding="utf-8")

    code, pre = cli(capsys, "preflight", spec, ws)
    assert any("normalize: source site_notes.txt changed" in s for s in pre["stale"])

    # Writing again on the old knowledge must not make the report look current.
    code, out = cli(capsys, "synthesize", spec, ws, "--replace")
    assert code == 0 and out["current"] is False
    record = json.loads((ws / "diagnostics" / "run_record.json").read_text(encoding="utf-8"))
    assert any("site_notes.txt changed" in w for w in record["stages"]["synthesize"]["warnings"])
    assert cli(capsys, "preflight", spec, ws)[1]["stale"]

    code, out = cli(capsys, "normalize", spec, ws, "--replace")
    assert cli(capsys, "preflight", spec, ws)[1]["stale"]  # curate and synthesize still old
    out = full_run(capsys, spec, ws, "--replace")
    assert out["current"] is True
    assert cli(capsys, "preflight", spec, ws)[1]["stale"] == []


def test_a_writing_setting_flags_only_synthesis(tmp_path, capsys):
    spec, ws = write_spec(tmp_path), tmp_path / "ws"
    full_run(capsys, spec, ws)
    data = json.loads(spec.read_text(encoding="utf-8"))
    data["settings"]["review_attempts"] = 2
    spec.write_text(json.dumps(data), encoding="utf-8")

    stale = cli(capsys, "preflight", spec, ws)[1]["stale"]
    assert stale and all(s.startswith("synthesize:") for s in stale)


def test_a_changed_runtime_model_flags_the_stages_that_used_it(tmp_path, capsys, monkeypatch):
    spec, ws = write_spec(tmp_path), tmp_path / "ws"
    full_run(capsys, spec, ws)
    monkeypatch.setenv("GAIK_REPORT_CURATOR_MODEL", "newer-model")
    monkeypatch.setenv("GAIK_REPORT_WRITER_MODEL", "newer-model")

    stale = cli(capsys, "preflight", spec, ws, "--check-provider")[1]["stale"]
    stages = {s.split(":")[0] for s in stale}
    assert stages == {"curate", "synthesize"}  # normalize used no model for text sources


def test_an_in_place_sample_edit_is_detected(tmp_path, capsys):
    (tmp_path / "sample.md").write_text("# Old style\n\nShort.\n", encoding="utf-8")
    spec, ws = write_spec(tmp_path, sample_report="sample.md"), tmp_path / "ws"
    assert full_run(capsys, spec, ws)["current"] is True
    (tmp_path / "sample.md").write_text("# New style\n\nLonger.\n", encoding="utf-8")

    stale = cli(capsys, "preflight", spec, ws)[1]["stale"]
    assert any("sample report file changed" in s for s in stale)

    code, out = cli(capsys, "update-sample", spec, ws)
    assert code == 0
    assert "New style" in (ws / "sample_report.md").read_text(encoding="utf-8")
    assert cli(capsys, "synthesize", spec, ws, "--replace")[1]["current"] is True


def test_update_sample_matches_the_module_and_keeps_the_old_file_on_failure(
    tmp_path, capsys, monkeypatch
):
    from gaik.software_components import source_normalizer

    (tmp_path / "sample.md").write_text("# Sample\n", encoding="utf-8")
    spec_path = write_spec(
        tmp_path,
        sample_report="sample.md",
        models={"vision": "v-model", "transcription": "t-model"},
        settings={"docx": False, "transcription_language": "fi"},
    )
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "sample_report.md").write_text("previous", encoding="utf-8")
    built = {}
    real = source_normalizer.SourceNormalizer

    class Spy(real):
        def __init__(self, config=None, **kwargs):
            built.update(kwargs)
            super().__init__(config, **kwargs)

        def to_markdown(self, path):
            raise RuntimeError("conversion failed")

    monkeypatch.setattr(source_normalizer, "SourceNormalizer", Spy)
    code, out = cli(capsys, "update-sample", spec_path, ws)

    assert code == rr.EXIT_STAGE
    assert built == {"vision_model": "v-model", "transcription_model": "t-model", "language": "fi"}
    assert (ws / "sample_report.md").read_text(encoding="utf-8") == "previous"


def test_no_credentials_are_written(tmp_path, capsys):
    spec, ws = write_spec(tmp_path), tmp_path / "ws"
    full_run(capsys, spec, ws)
    for path in (ws / "diagnostics").glob("*.json"):
        assert SECRET not in path.read_text(encoding="utf-8"), path.name
    record = json.loads((ws / "diagnostics" / "run_record.json").read_text(encoding="utf-8"))
    assert record["stages"]["curate"]["models"] == {"provider": "azure", "curator": "gpt-6-luna"}
    assert record["stages"]["synthesize"]["models"] == {
        "provider": "azure",
        "writer": "gpt-6-luna",
        "reviewer": "gpt-6.1-sol",
    }


# ── Template to outline ─────────────────────────────────────────────


def test_a_markdown_template_becomes_a_reviewable_outline():
    markdown = (
        "Kuntoarvio\n==========\n\n"
        "Rakenteet ja vesikatto\n----------------------\n"
        "Describe the roof. Include:\n- roof covering and its age\n- attic ventilation\n\n"
        "## Talotekniikka\n"
        "- The 2019 camera inspection found two cracks in the main sewer line.\n"
        "- Ventilation was renewed in 2021.\n\n"
        "## Talotekniikka\nAgain.\n\n"
        "## ???\nOdd heading.\n\n"
        "## Yhteenveto\nThe main findings. [insert summary]\n"
    )
    result = tts.outline(markdown, "t.md")

    assert result["title"] == "Kuntoarvio"
    ids = [s["id"] for s in result["sections"]]
    assert ids == [
        "rakenteet_ja_vesikatto",
        "talotekniikka",
        "talotekniikka_2",
        "section_4",
        "yhteenveto",
    ]
    roof, services = result["sections"][0], result["sections"][1]
    assert {i["kind"] for i in roof["candidate_required_items"]} == {"checklist"}
    assert {i["kind"] for i in services["candidate_required_items"]} == {"unclear"}
    summary = result["sections"][-1]
    assert (
        summary["suggest_derived"] and "rakenteet_ja_vesikatto" in summary["suggested_depends_on"]
    )
    assert summary["placeholders"] == ["[insert summary]"]
    assert any("titled 'Talotekniikka'" in d["message"] for d in result["diagnostics"])


def test_slugs_are_ascii_ids():
    assert tts.slug("Yhteenveto ja jatkotoimet") == "yhteenveto_ja_jatkotoimet"
    assert tts.slug("Työmaan äänitys, öljy & Ålands") == "tyomaan_aanitys_oljy_alands"
    assert tts.slug("Straße / Æble") == "strasse_aeble"
    assert tts.slug("???") == ""


def test_a_template_without_headings_is_an_error(tmp_path):
    (tmp_path / "flat.md").write_text("Just a paragraph.\n", encoding="utf-8")
    assert tts.main([str(tmp_path / "flat.md"), "--out", str(tmp_path / "o.json")]) == 2


def test_a_word_template_is_read_through_the_docx_parser(tmp_path):
    docx = pytest.importorskip("docx")
    document = docx.Document()
    document.add_heading("Inspection report", level=1)
    document.add_heading("Findings", level=2)
    document.add_paragraph("List every defect found.")
    document.add_heading("Recommendations", level=2)
    document.add_paragraph("Repairs in order of urgency.")
    document.save(tmp_path / "template.docx")

    out = tmp_path / "outline.json"
    assert tts.main([str(tmp_path / "template.docx"), "--out", str(out)]) == 0
    result = json.loads(out.read_text(encoding="utf-8"))
    assert result["title"] == "Inspection report"
    assert [s["id"] for s in result["sections"]] == ["findings", "recommendations"]
    assert result["sections"][1]["suggested_depends_on"] == ["findings"]


# ── The report structure, agreed after normalization ────────────────


def _structure(path: Path, structure) -> Path:
    path.write_text(json.dumps(structure, ensure_ascii=False), encoding="utf-8")
    return path


def test_set_sections_writes_the_accepted_structure_into_the_spec(tmp_path, capsys):
    spec = write_spec(tmp_path, sections=[{"id": "draft", "title": "Draft"}])
    before = json.loads(spec.read_text(encoding="utf-8"))
    structure = _structure(
        tmp_path / "structure.json",
        [
            {"title": "Vesikatto", "prompt": "Roofing material and condition."},
            {
                "title": "Talotekniikka",
                "prompt": "Heating, ventilation, water and sewer.",
                "required_items": ["ventilation system and its age"],
            },
            {
                "title": "Yhteenveto",
                "prompt": "The main findings.",
                "summary_of": ["Vesikatto", "talotekniikka"],
            },
        ],
    )

    code, out = cli(capsys, "set-sections", spec, tmp_path / "ws", "--structure", str(structure))

    assert code == 0, out
    after = json.loads(spec.read_text(encoding="utf-8"))
    assert [s["id"] for s in after["sections"]] == ["vesikatto", "talotekniikka", "yhteenveto"]
    assert after["sections"][1]["required_items"] == ["ventilation system and its age"]
    assert after["sections"][2]["depends_on"] == ["vesikatto", "talotekniikka"]
    assert after["sections"][0]["instructions"] == "Roofing material and condition."
    # everything else is left exactly as written, relative paths included
    assert {k: v for k, v in after.items() if k != "sections"} == {
        k: v for k, v in before.items() if k != "sections"
    }
    assert out["sections"][2]["summary_of"] == ["Vesikatto", "Talotekniikka"]


@pytest.mark.parametrize(
    ("structure", "expected"),
    [
        ([], "at least one section"),
        ([{"title": "Summary", "prompt": "x", "summary_of": ["Summary"]}], "summarize itself"),
        (
            [
                {"title": "A", "prompt": "x", "summary_of": ["B"]},
                {"title": "B", "prompt": "y", "summary_of": ["A"]},
            ],
            "at least one section must be written from the sources",
        ),
        ([{"title": "A", "prompt": "x"}, {"title": "a", "prompt": "y"}], "Two sections are titled"),
        ([{"title": "A", "prompt": ""}], "has no prompt"),
        ([{"title": "A", "prompt": "x", "summary_of": ["Nope"]}], "which is not a section"),
        ([{"prompt": "x"}], "has no title"),
    ],
)
def test_set_sections_refuses_a_broken_structure_and_changes_nothing(
    tmp_path, capsys, structure, expected
):
    spec = write_spec(tmp_path)
    before = spec.read_text(encoding="utf-8")
    path = _structure(tmp_path / "structure.json", structure)

    code, out = cli(capsys, "set-sections", spec, tmp_path / "ws", "--structure", str(path))

    assert code == rr.EXIT_INPUT
    assert any(expected in e for e in out["errors"]), out["errors"]
    assert spec.read_text(encoding="utf-8") == before


def test_ids_from_titles_are_ascii_and_unique(tmp_path, capsys):
    spec = write_spec(tmp_path)
    path = _structure(
        tmp_path / "s.json",
        [
            {"title": "Työmaan äänitys", "prompt": "x"},
            {"title": "Työmaan  äänitys!", "prompt": "y"},
            {"title": "???", "prompt": "z"},
        ],
    )
    assert cli(capsys, "set-sections", spec, tmp_path / "ws", "--structure", str(path))[0] == 0
    ids = [s["id"] for s in json.loads(spec.read_text(encoding="utf-8"))["sections"]]
    assert ids == ["tyomaan_aanitys", "tyomaan_aanitys_2", "section_3"]


def test_a_structure_change_after_curation_reruns_curation_not_normalization(tmp_path, capsys):
    spec, ws = write_spec(tmp_path), tmp_path / "ws"
    full_run(capsys, spec, ws)
    path = _structure(
        tmp_path / "s.json",
        [{"title": "Building services", "prompt": "Ventilation only."}],
    )

    code, out = cli(capsys, "set-sections", spec, ws, "--structure", str(path))

    assert code == 0
    assert any("curate and synthesize must run again" in w for w in out["warnings"])
    stale = cli(capsys, "preflight", spec, ws)[1]["stale"]
    assert {s.split(":")[0] for s in stale} == {"curate", "synthesize"}


def test_the_flow_from_template_to_report(tmp_path, capsys):
    (tmp_path / "template.md").write_text(
        "# Report\n\n## Building services\nVentilation and sewer. Include:\n"
        "- ventilation system and its age\n\n## Summary\nThe main findings.\n",
        encoding="utf-8",
    )
    spec, ws = write_spec(tmp_path, sections=[{"id": "draft", "title": "Draft"}]), tmp_path / "ws"
    assert cli(capsys, "normalize", spec, ws)[0] == 0  # the structure is agreed after this

    outline = tmp_path / "outline.json"
    assert tts.main([str(tmp_path / "template.md"), "--out", str(outline)]) == 0
    draft = json.loads(outline.read_text(encoding="utf-8"))["structure"]
    assert draft[1]["summary_of"] == ["Building services"]
    path = _structure(tmp_path / "structure.json", draft)

    assert cli(capsys, "set-sections", spec, ws, "--structure", str(path))[0] == 0
    for command in ("curate", "synthesize"):
        code, out = cli(capsys, command, spec, ws)
        assert code == 0, out
    assert out["sections"] == ["building_services", "summary"] and out["current"] is True


def test_the_draft_structure_lists_unsure_bullets_to_confirm():
    result = tts.outline(
        "# T\n\n## Findings\n- The 2019 inspection found two cracks in the sewer.\n"
        "## Scope\nWhat was inspected. Include:\n- rooms visited\n",
        "t.md",
    )
    findings, scope = result["structure"]
    assert findings["required_items"] == [] and findings["to_confirm"]
    assert scope["required_items"] == ["rooms visited"] and "to_confirm" not in scope


# ── Review fixes: path collisions, stdout, template ids, short PDFs ─


@pytest.mark.parametrize("folder", ["normalized", "knowledge", "report", "diagnostics"])
def test_an_input_inside_a_stage_folder_is_refused_and_kept(tmp_path, capsys, folder):
    ws = tmp_path / "ws"
    (ws / folder).mkdir(parents=True)
    original = ws / folder / "notes.txt"
    original.write_text("An original input the user put here.\n", encoding="utf-8")
    spec = write_spec(tmp_path, sources={"primary": [f"ws/{folder}/notes.txt"]})

    code, out = cli(capsys, "normalize", spec, ws, "--replace")

    assert code == rr.EXIT_INPUT
    assert any("which the pipeline deletes or overwrites" in e for e in out["errors"])
    assert original.read_text(encoding="utf-8").startswith("An original input")
    assert cli(capsys, "preflight", spec, ws)[0] == rr.EXIT_INPUT


def test_a_sample_report_where_update_sample_writes_is_refused(tmp_path, capsys):
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "sample_report.md").write_text("The user's own sample.\n", encoding="utf-8")
    spec = write_spec(tmp_path, sample_report="ws/sample_report.md")

    code, out = cli(capsys, "update-sample", spec, ws)

    assert code == rr.EXIT_INPUT and out["error"]["category"] == "path-collision"
    assert (ws / "sample_report.md").read_text(encoding="utf-8") == "The user's own sample.\n"


def test_component_output_does_not_reach_stdout(tmp_path, capsys, monkeypatch):
    class Chatty(FakeWriter):
        def normalize(self, spec, workspace, *, progress_callback=None):
            print("Transcribing... (this may take a while)")  # as the transcriber does
            return super().normalize(spec, workspace, progress_callback=progress_callback)

    monkeypatch.setattr(rr, "make_writer", lambda config: Chatty(config))
    spec, ws = write_spec(tmp_path), tmp_path / "ws"

    rr.main(["normalize", "--spec", str(spec), "--workspace", str(ws), "--json"])
    captured = capsys.readouterr()

    assert json.loads(captured.out)["ok"] is True
    assert "Transcribing" in captured.err


def test_template_ids_never_collide():
    result = tts.outline("# T\n\n## Findings\na\n## Findings\nb\n## Findings 2\nc\n", "t.md")
    ids = [s["id"] for s in result["sections"]]
    assert ids == ["findings", "findings_2", "findings_2_2"]
    assert len(set(ids)) == len(ids)


def test_a_short_text_pdf_is_not_a_scan(tmp_path, capsys):
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    _pdf(inputs / "receipt.pdf", ["Total: 100"])
    spec = write_spec(tmp_path, sources={"primary": ["inputs/receipt.pdf"]})

    code, out = cli(capsys, "preflight", spec, tmp_path / "ws")

    assert code == 0, out["errors"]
    assert any("receipt.pdf: pages [1] have very little text" in w for w in out["warnings"])
    assert not any("no text layer" in w for w in out["warnings"])


# ── Linked stage folders, and outputs that are their own input ──────


def _link_dir(link: Path, target: Path) -> None:
    """A directory symlink, or on Windows without the right to make one, a junction."""
    try:
        os.symlink(target, link, target_is_directory=True)
        return
    except (OSError, NotImplementedError):
        pass
    try:
        import _winapi

        _winapi.CreateJunction(str(target), str(link))
    except (ImportError, OSError) as exc:
        pytest.skip(f"cannot create a directory link here: {exc}")


def test_a_linked_stage_folder_cannot_reach_the_originals(tmp_path, capsys):
    spec, ws = write_spec(tmp_path), tmp_path / "ws"
    ws.mkdir()
    _link_dir(ws / "diagnostics", tmp_path / "inputs")  # the folder holding the originals
    originals = sorted(p.name for p in (tmp_path / "inputs").iterdir())

    code, out = cli(capsys, "normalize", spec, ws, "--replace")

    assert code == rr.EXIT_INPUT
    errors = " | ".join(out["errors"])
    assert "workspace/diagnostics is a link" in errors
    assert "site_notes.txt is inside workspace/diagnostics" in errors
    assert sorted(p.name for p in (tmp_path / "inputs").iterdir()) == originals
    assert cli(capsys, "preflight", spec, ws)[0] == rr.EXIT_INPUT


def test_a_linked_stage_folder_elsewhere_is_refused_too(tmp_path, capsys):
    spec, ws = write_spec(tmp_path), tmp_path / "ws"
    ws.mkdir()
    (tmp_path / "elsewhere").mkdir()
    _link_dir(ws / "normalized", tmp_path / "elsewhere")

    code, out = cli(capsys, "preflight", spec, ws)

    assert code == rr.EXIT_INPUT
    assert any("workspace/normalized is a link" in e for e in out["errors"])


def test_the_template_cannot_be_its_own_output(tmp_path):
    template = tmp_path / "template.md"
    template.write_text("# T\n\n## A\nText.\n", encoding="utf-8")

    assert tts.main([str(template), "--out", str(template)]) == 2
    assert template.read_text(encoding="utf-8") == "# T\n\n## A\nText.\n"


def test_the_structure_file_cannot_be_the_spec(tmp_path, capsys):
    spec = write_spec(tmp_path)
    before = spec.read_text(encoding="utf-8")

    code, out = cli(capsys, "set-sections", spec, tmp_path / "ws", "--structure", str(spec))

    assert code == rr.EXIT_INPUT and "same file" in out["error"]["message"]
    assert spec.read_text(encoding="utf-8") == before


def test_word_bullet_lists_become_required_items(tmp_path):
    # gaik's DocxParser drops list markers, so the script reads Word templates itself.
    docx = pytest.importorskip("docx")
    document = docx.Document()
    document.add_heading("Condition report", level=1)
    document.add_heading("Building services", level=2)
    document.add_paragraph("Describe the services. Include:")
    for item in ("ventilation system and its age", "radon measurement result"):
        document.add_paragraph(item, style="List Bullet")
    document.add_paragraph("Example of the expected style:")
    document.add_paragraph("The unit was serviced in 2020 and runs quietly.", style="List Bullet")
    document.add_heading("Summary", level=2)
    document.add_paragraph("The overall condition.")
    document.save(tmp_path / "t.docx")

    out = tmp_path / "o.json"
    assert tts.main([str(tmp_path / "t.docx"), "--out", str(out)]) == 0
    services, summary = json.loads(out.read_text(encoding="utf-8"))["structure"]
    assert services["required_items"] == [
        "ventilation system and its age",
        "radon measurement result",
    ]
    assert services["to_confirm"] == ["The unit was serviced in 2020 and runs quietly."]
    assert "2020" not in services["prompt"]
    assert summary["summary_of"] == ["Building services"]


def test_a_copied_run_folder_stays_current(tmp_path, capsys):
    # The run record keys sources by file name and content, not by path: copying or moving
    # the run folder (with paths that still reach the same inputs) must not look like a change.
    first = tmp_path / "runs" / "one"
    first.mkdir(parents=True)
    write_spec(tmp_path)  # creates tmp_path/inputs
    spec = json.loads((tmp_path / "report_spec.json").read_text(encoding="utf-8"))
    spec["sources"] = {k: ["../../" + p for p in v] for k, v in spec["sources"].items()}
    (first / "report_spec.json").write_text(json.dumps(spec), encoding="utf-8")
    assert full_run(capsys, first / "report_spec.json", first / "ws")["current"] is True

    second = tmp_path / "runs" / "two"
    shutil.copytree(first, second)
    assert cli(capsys, "preflight", second / "report_spec.json", second / "ws")[1]["stale"] == []


def test_the_spec_reference_carries_the_instruction_sentences():
    # The agent copies these sentences into a report's instructions; each was found by testing.
    text = " ".join(
        (SKILL_DIR / "references" / "report-spec.md").read_text(encoding="utf-8").split()
    )
    # The sentence is checked inside the quoted blocks, not only in the JSON example above them.
    quoted = [line for line in text.split("> ") if line.startswith("Use the (missing")]
    assert quoted and all(line.startswith("Use the (missing: ...) marker") for line in quoted)
    for sentence in (
        "Use the (missing: ...) marker only for the items listed as missing",
        "write nothing else in that section, even if loosely related facts exist",
        "Citation sentence, only with citations",
        "Gap markers, always",
    ):
        assert sentence in text
    assert "STRICTLY" not in text  # the sample sentence was removed on purpose


# ── Template library ─────────────────────────────────────────────────

tl = _load("template_library")

LIBRARY_SECTIONS = [
    {
        "id": "building_services",
        "title": "Building services",
        "instructions": "Ventilation, water and sewer.",
        "required_items": ["ventilation system and its age"],
    },
    {
        "id": "summary",
        "title": "Summary",
        "instructions": "The main findings.",
        "depends_on": ["building_services"],
    },
]


def library_cli(capsys, library, *argv):
    code = tl.main([*argv, "--library", str(library), "--json"])
    return code, json.loads(capsys.readouterr().out)


def save_template(capsys, tmp_path, library, *extra, name="House condition assessment", **spec):
    spec_path = write_spec(tmp_path, sections=LIBRARY_SECTIONS, **spec)
    return library_cli(
        capsys,
        library,
        "save",
        "--spec",
        str(spec_path),
        "--name",
        name,
        "--description",
        "Pre-sale inspection of a detached house",
        "--keywords",
        "building survey, property",
        *extra,
    )


def test_save_shows_a_preview_and_writes_nothing_without_approval(capsys, tmp_path):
    library = tmp_path / "lib"
    code, out = save_template(capsys, tmp_path, library)
    assert code == 0 and out["written"] is False and "next" in out
    assert not library.exists()


def test_an_approved_save_keeps_only_the_reusable_parts(capsys, tmp_path):
    library = tmp_path / "lib"
    code, out = save_template(capsys, tmp_path, library, "--approved")
    assert code == 0 and out["written"] is True
    saved = json.loads((library / "house_condition_assessment.json").read_text(encoding="utf-8"))
    assert set(saved) == {
        "format", "id", "name", "description", "keywords", "language", "title",
        "instructions", "structure", "saved",
    }  # fmt: skip
    assert saved["structure"][1] == {
        "title": "Summary",
        "prompt": "The main findings.",
        "summary_of": ["Building services"],
    }
    assert "inputs" not in json.dumps(saved) and "site_notes" not in json.dumps(saved)


def test_save_does_not_replace_a_template_unless_told(capsys, tmp_path):
    library = tmp_path / "lib"
    save_template(capsys, tmp_path, library, "--approved")
    code, out = save_template(capsys, tmp_path, library, "--approved")
    assert code == 2 and out["error"]["category"] == "would-replace"
    assert save_template(capsys, tmp_path, library, "--approved", "--replace")[0] == 0


@pytest.mark.parametrize("where", ["git", "skill"])
def test_save_refuses_a_library_that_could_reach_a_repository(capsys, tmp_path, where):
    if where == "git":
        (tmp_path / "repo" / ".git").mkdir(parents=True)
        library = tmp_path / "repo" / "templates"
    else:
        library = SKILL_DIR / "library-test-never-created"
    code, out = save_template(capsys, tmp_path, library, "--approved")
    assert code == 2 and out["error"]["category"] == "library-location"
    assert not library.exists()


def test_save_refuses_text_that_looks_like_a_key(capsys, tmp_path):
    code, out = save_template(
        capsys, tmp_path, tmp_path / "lib", "--approved", instructions=f"Use {SECRET}."
    )
    assert code == 2 and out["error"]["category"] == "secret"
    assert not (tmp_path / "lib").exists()


def test_search_finds_the_template_by_the_users_words(capsys, tmp_path):
    library = tmp_path / "lib"
    save_template(capsys, tmp_path, library, "--approved")
    save_template(capsys, tmp_path, library, "--approved", name="Quarterly project status")
    code, out = library_cli(capsys, library, "search", "I need a property survey for a house")
    assert code == 0 and out["matches"][0]["id"] == "house_condition_assessment"
    code, out = library_cli(capsys, library, "search", "house inspections")
    assert out["matches"][0]["id"] == "house_condition_assessment"  # inspection ~ inspections
    code, out = library_cli(capsys, library, "search", "marketing newsletter")
    assert out["matches"] == [] and out["templates_in_library"] == 2


def test_an_empty_or_missing_library_is_not_an_error(capsys, tmp_path):
    code, out = library_cli(capsys, tmp_path / "none", "search", "anything")
    assert code == 0 and out["matches"] == [] and out["templates_in_library"] == 0
    assert library_cli(capsys, tmp_path / "none", "list")[1]["exists"] is False


def test_a_loaded_template_goes_through_set_sections(capsys, tmp_path):
    library = tmp_path / "lib"
    save_template(capsys, tmp_path, library, "--approved")
    out_file = tmp_path / "structure.json"
    code, out = library_cli(
        capsys, library, "load", "house_condition_assessment", "--out", str(out_file)
    )
    assert code == 0 and out["sections"] == ["Building services", "Summary"]
    assert "No source has automatic priority" in out["instructions"]
    spec = write_spec(tmp_path / "new")
    code, result = cli(
        capsys, "set-sections", spec, tmp_path / "new" / "ws", "--structure", str(out_file)
    )
    assert code == 0, result
    ids = [s["id"] for s in json.loads(spec.read_text(encoding="utf-8"))["sections"]]
    assert ids == ["building_services", "summary"]


def test_load_refuses_unknown_ids_and_existing_files(capsys, tmp_path):
    library = tmp_path / "lib"
    save_template(capsys, tmp_path, library, "--approved")
    target = tmp_path / "s.json"
    target.write_text("keep", encoding="utf-8")
    code, out = library_cli(
        capsys, library, "load", "house_condition_assessment", "--out", str(target)
    )
    assert code == 2 and out["error"]["category"] == "would-replace"
    assert target.read_text(encoding="utf-8") == "keep"
    code, out = library_cli(capsys, library, "load", "../escape", "--out", str(tmp_path / "x.json"))
    assert code == 2 and out["error"]["category"] == "bad-input"
    assert (
        library_cli(capsys, library, "load", "missing", "--out", str(tmp_path / "x.json"))[0] == 2
    )


def test_a_broken_file_in_the_library_is_skipped_and_reported(capsys, tmp_path):
    library = tmp_path / "lib"
    save_template(capsys, tmp_path, library, "--approved")
    (library / "broken.json").write_text("{not json", encoding="utf-8")
    code, out = library_cli(capsys, library, "list")
    assert code == 0 and len(out["templates"]) == 1 and len(out["skipped"]) == 1


def test_the_default_library_is_under_the_home_folder(monkeypatch):
    monkeypatch.delenv(tl.ENV_LIBRARY, raising=False)
    assert tl.library_dir(None) == Path.home() / "report-templates"
    monkeypatch.setenv(tl.ENV_LIBRARY, "~/elsewhere")
    assert tl.library_dir(None) == Path.home() / "elsewhere"


def test_the_skill_text_names_the_library_and_the_approval_rule():
    text = " ".join((SKILL_DIR / "SKILL.md").read_text(encoding="utf-8").split())
    assert "template_library.py search" in text and "--approved" in text
    assert "style-and-length" not in text  # nothing may point at the removed sentence
    assert "First ask where to save the outputs" in text
    assert "Ask in step 1 whether the report cites its sources" in text
    assert "set `settings.citations` to `false`" in text
    assert "only after the user has seen the preview and agreed" in text


@pytest.fixture
def real_provider_check(monkeypatch):
    import gaik.software_components.llm as llm

    monkeypatch.setattr(rr, "load_config", REAL_LOAD_CONFIG)
    monkeypatch.setattr(llm, "get_llm_config", lambda name: {"provider": name})


@pytest.mark.parametrize(
    ("provider", "extra"),
    [
        ("anthropic", "llm-anthropic"),
        ("anthropic_foundry", "llm-anthropic"),
        ("google", "llm-google"),
    ],
)
def test_a_missing_provider_package_is_installed_from_its_extra(
    monkeypatch, real_provider_check, provider, extra
):
    installed = []
    available = {"yes": False}
    monkeypatch.setattr(rr, "package_available", lambda module: available["yes"])

    def fake_call(command, **kwargs):
        installed.append(command)
        available["yes"] = True
        return 0

    monkeypatch.setattr("subprocess.call", fake_call)
    assert REAL_LOAD_CONFIG(provider)["provider"] == provider
    assert installed[0][-1] == f"gaik[{extra}]" and installed[0][1:4] == ["-m", "pip", "install"]


def test_a_failed_install_stops_and_names_the_command(
    monkeypatch, capsys, tmp_path, real_provider_check
):
    monkeypatch.setattr(rr, "package_available", lambda module: False)
    monkeypatch.setattr("shutil.which", lambda name: None)
    monkeypatch.setattr("subprocess.call", lambda command, **kwargs: 1)
    spec = write_spec(tmp_path)
    args = ("--provider", "anthropic", "--check-provider")
    code, out = cli(capsys, "preflight", spec, tmp_path / "ws", *args)
    assert code == 4 and out["error"]["category"] == "provider-package"
    assert 'pip install "gaik[llm-anthropic]"' in out["error"]["message"]


def test_nothing_is_installed_when_the_package_is_there(monkeypatch, real_provider_check):
    monkeypatch.setattr(rr, "package_available", lambda module: True)

    def forbidden(command, **kwargs):
        raise AssertionError("pip must not run")

    monkeypatch.setattr("subprocess.call", forbidden)
    assert REAL_LOAD_CONFIG("anthropic")["provider"] == "anthropic"
    assert REAL_LOAD_CONFIG("azure")["provider"] == "azure"  # needs no extra package


# ── Provider and model defaults ─────────────────────────────────────


def models_of(spec_models: dict, config: dict) -> dict:
    spec = rr.import_report_writer().ReportSpec(
        title="T",
        sections=[{"id": "a", "title": "A", "instructions": "x"}],
        sources={"primary": ["a.txt"]},
        models=spec_models,
    )
    rr.apply_model_defaults(spec, config)
    return {s: getattr(spec.models, s) for s in ("curator", "writer", "reviewer")}


@pytest.fixture
def clean_model_env(monkeypatch):
    for name in (*rr.MODEL_ENV.values(), "LLM_PROVIDER"):
        monkeypatch.delenv(name, raising=False)


@pytest.mark.parametrize("provider", ["openai", "azure"])
def test_openai_and_azure_get_the_default_models(clean_model_env, provider):
    assert models_of({}, {"provider": provider}) == {
        "curator": "gpt-6-luna",
        "writer": "gpt-6-luna",
        "reviewer": "gpt-6.1-sol",
    }


def test_a_variable_beats_the_default_and_the_spec_beats_the_variable(clean_model_env, monkeypatch):
    monkeypatch.setenv("GAIK_REPORT_WRITER_MODEL", "from-env")
    monkeypatch.setenv("GAIK_REPORT_REVIEWER_MODEL", "from-env")
    got = models_of({"reviewer": "from-spec"}, {"provider": "openai"})
    assert got == {"curator": "gpt-6-luna", "writer": "from-env", "reviewer": "from-spec"}


@pytest.mark.parametrize(
    ("providers", "expected"),
    [
        (
            ("anthropic", "anthropic_foundry"),
            ("claude-sonnet-5", "claude-sonnet-5", "claude-sonnet-5-5"),
        ),
        (("google", "vertex"), ("gemini-3.6-flash", "gemini-3.6-flash", "gemini-3.8-flash")),
    ],
)
def test_anthropic_and_google_families_get_their_own_defaults(clean_model_env, providers, expected):
    for provider in providers:
        got = models_of({}, {"provider": provider})
        assert tuple(got.values()) == expected


def test_a_provider_without_defaults_keeps_its_own_model_unless_a_variable_names_one(
    clean_model_env, monkeypatch
):
    assert models_of({}, {"provider": "litellm"}) == dict.fromkeys(rr.MODEL_ENV)
    monkeypatch.setenv("GAIK_REPORT_WRITER_MODEL", "some-model")
    assert models_of({}, {"provider": "aitta"})["writer"] == "some-model"


def test_the_default_provider_is_openai_and_llm_provider_overrides_it(clean_model_env, monkeypatch):
    import gaik.software_components.llm as llm

    seen = []
    monkeypatch.setattr(llm, "get_llm_config", lambda name: seen.append(name) or {"provider": name})
    monkeypatch.setattr(rr, "package_available", lambda module: True)
    REAL_LOAD_CONFIG(None)
    monkeypatch.setenv("LLM_PROVIDER", "azure")
    REAL_LOAD_CONFIG(None)
    REAL_LOAD_CONFIG("anthropic")
    assert seen == ["openai", "azure", "anthropic"]


def test_the_defaults_never_reach_the_spec_file(tmp_path, capsys, clean_model_env):
    spec = write_spec(tmp_path)
    before = spec.read_text(encoding="utf-8")
    assert cli(capsys, "preflight", spec, tmp_path / "ws", "--check-provider")[0] == 0
    assert spec.read_text(encoding="utf-8") == before


def test_no_reasoning_effort_is_passed_unless_the_spec_sets_one(tmp_path):
    spec_path = write_spec(
        tmp_path, settings={"docx": False, "writer": {"reasoning_effort": "high"}}
    )
    spec = rr.load_spec(spec_path)
    assert spec.settings.curator.chat_kwargs() == {}
    assert spec.settings.reviewer.chat_kwargs() == {}
    assert spec.settings.writer.chat_kwargs() == {"reasoning_effort": "high"}


# ── The whole spec: propose-spec and apply-spec ─────────────────────

GOOD_INSTRUCTIONS = (
    "- Write in simple language\n"
    "- No source has automatic priority.\n"
    "- Cite each fact by its source file.\n"
    "- Use the (missing: ...) marker only for the items listed as missing."
)


def agreed_spec(tmp_path, **overrides):
    return write_spec(
        tmp_path, sections=LIBRARY_SECTIONS, instructions=GOOD_INSTRUCTIONS, **overrides
    )


def propose(capsys, spec, tmp_path, *extra):
    out = tmp_path / "proposal.json"
    return run(
        capsys, "propose-spec", "--spec", str(spec), "--workspace", str(tmp_path / "ws"),
        "--out", str(out), *extra,
    )  # fmt: skip


def apply_spec(capsys, spec, tmp_path, *extra):
    return run(
        capsys, "apply-spec", "--spec", str(spec), "--workspace", str(tmp_path / "ws"),
        "--proposal", str(tmp_path / "proposal.json"), *extra,
    )  # fmt: skip


def test_propose_spec_spells_out_every_key_and_leaves_the_spec_alone(
    capsys, tmp_path, clean_model_env
):
    spec = agreed_spec(tmp_path)
    before = spec.read_text(encoding="utf-8")
    code, out = propose(capsys, spec, tmp_path, "--provider", "openai")
    assert code == 0 and out["errors"] == []
    proposal = json.loads((tmp_path / "proposal.json").read_text(encoding="utf-8"))
    assert list(proposal)[: len(rr.SPEC_KEYS)] == list(rr.SPEC_KEYS)
    assert proposal["models"] == {
        "vision": None,
        "transcription": "gpt-4o-transcribe",
        "curator": "gpt-6-luna",
        "writer": "gpt-6-luna",
        "reviewer": "gpt-6.1-sol",
    }
    assert proposal["settings"]["strict_review"] is True
    assert proposal["settings"]["docx"] is False  # the spec's own value is kept
    assert proposal["settings"]["citations"] is True
    assert any("(default)" in line for line in out["review"])
    assert spec.read_text(encoding="utf-8") == before


def test_propose_spec_keeps_the_users_edits_and_resets_models_on_request(
    capsys, tmp_path, clean_model_env
):
    spec = agreed_spec(tmp_path, models={"writer": "my-writer"})
    propose(capsys, spec, tmp_path, "--provider", "openai")
    proposal = tmp_path / "proposal.json"
    edited = json.loads(proposal.read_text(encoding="utf-8"))
    edited["title"] = "Edited by the user"
    proposal.write_text(json.dumps(edited), encoding="utf-8")

    code, out = propose(capsys, spec, tmp_path, "--provider", "anthropic", "--reset-models")
    assert code == 0 and out["started_from"] == "proposal.json"
    again = json.loads(proposal.read_text(encoding="utf-8"))
    assert again["title"] == "Edited by the user"
    assert again["models"]["writer"] == "claude-sonnet-5"
    assert again["models"]["transcription"] is None  # Anthropic cannot transcribe


def test_propose_spec_turns_a_structure_into_sections(capsys, tmp_path, clean_model_env):
    spec = write_spec(tmp_path)
    structure = tmp_path / "structure.json"
    structure.write_text(
        json.dumps(
            [
                {"title": "Roof and gutters", "prompt": "Condition of the roof."},
                {
                    "title": "Summary",
                    "prompt": "The main findings.",
                    "summary_of": ["Roof and gutters"],
                },
            ]
        ),
        encoding="utf-8",
    )
    args = ("--provider", "openai", "--structure", str(structure))
    code, out = propose(capsys, spec, tmp_path, *args)
    assert code == 0
    sections = out["proposal"]["sections"]
    assert [s["id"] for s in sections] == ["roof_and_gutters", "summary"]
    assert sections[1]["depends_on"] == ["roof_and_gutters"]


def test_propose_spec_refuses_the_spec_as_its_own_output(capsys, tmp_path):
    spec = agreed_spec(tmp_path)
    code, out = run(
        capsys, "propose-spec", "--spec", str(spec), "--workspace", str(tmp_path / "ws"),
        "--out", str(spec),
    )  # fmt: skip
    assert code == 2 and "--out must not be the spec" in out["error"]["message"]


def test_apply_spec_check_writes_nothing_and_apply_writes_the_proposal(
    capsys, tmp_path, clean_model_env
):
    spec = agreed_spec(tmp_path)
    propose(capsys, spec, tmp_path, "--provider", "openai")
    before = spec.read_text(encoding="utf-8")

    code, out = apply_spec(capsys, spec, tmp_path, "--provider", "openai", "--check")
    assert code == 0 and out["written"] is False
    assert spec.read_text(encoding="utf-8") == before

    code, out = apply_spec(capsys, spec, tmp_path, "--provider", "openai")
    assert code == 0 and out["written"] is True
    proposal = json.loads((tmp_path / "proposal.json").read_text(encoding="utf-8"))
    assert json.loads(spec.read_text(encoding="utf-8")) == proposal
    assert rr.load_spec(spec).models.reviewer == "gpt-6.1-sol"


def test_apply_spec_refuses_credentials_and_unfinished_sections(capsys, tmp_path, clean_model_env):
    spec = agreed_spec(tmp_path)
    propose(capsys, spec, tmp_path, "--provider", "openai")
    path = tmp_path / "proposal.json"
    bad = json.loads(path.read_text(encoding="utf-8"))
    bad["models"]["api_key"] = SECRET
    bad["sections"][0]["instructions"] = ""
    path.write_text(json.dumps(bad), encoding="utf-8")
    before = spec.read_text(encoding="utf-8")

    code, out = apply_spec(capsys, spec, tmp_path, "--provider", "openai")
    message = out["error"]["message"]
    assert code == 2 and "credentials" in message and "has no instructions" in message
    assert SECRET not in json.dumps(out)
    assert spec.read_text(encoding="utf-8") == before


def test_apply_spec_names_the_stages_a_change_makes_stale(capsys, tmp_path, clean_model_env):
    spec, ws = agreed_spec(tmp_path), tmp_path / "ws"
    propose(capsys, spec, tmp_path, "--provider", "azure")
    assert apply_spec(capsys, spec, tmp_path, "--provider", "azure")[0] == 0  # step 2: agreed
    full_run(capsys, spec, ws)
    path = tmp_path / "proposal.json"
    changed = json.loads(path.read_text(encoding="utf-8"))
    changed["instructions"] = "- A different rule\n- Cite each fact."
    path.write_text(json.dumps(changed), encoding="utf-8")

    code, out = apply_spec(capsys, spec, tmp_path, "--provider", "azure", "--check")
    assert code == 0
    assert "curate must run again" in out["warnings"]
    assert "synthesize must run again" in out["warnings"]
    assert "normalize must run again" not in out["warnings"]
    assert any("no gap-marker sentence" in w for w in out["warnings"])


# ── Pandoc: check, and install only when asked ──────────────────────

ip = _load("install_pandoc")
FOUND = {"found": True, "version": "3.10", "path": "/somewhere/pandoc"}
MISSING = {"found": False, "reason": "the Pandoc program is not installed"}


def pandoc_cli(capsys, *argv):
    code = ip.main([*argv, "--json"])
    return code, json.loads(capsys.readouterr().out)


def forbid_download():
    raise AssertionError("Pandoc must not be downloaded here")


def test_check_installs_nothing_and_says_how_when_pandoc_is_missing(capsys, monkeypatch):
    monkeypatch.setattr(ip, "download_pandoc", forbid_download)
    monkeypatch.setattr(ip, "find_pandoc", lambda: MISSING)
    code, out = pandoc_cli(capsys, "--check")
    assert code == 4 and out["ok"] is False and out["installed_now"] is False
    assert "winget" in out["next"]

    monkeypatch.setattr(ip, "find_pandoc", lambda: FOUND)
    assert pandoc_cli(capsys, "--check")[0] == 0


def test_an_existing_pandoc_is_never_downloaded_again(capsys, monkeypatch):
    monkeypatch.setattr(ip, "download_pandoc", forbid_download)
    monkeypatch.setattr(ip, "find_pandoc", lambda: FOUND)
    code, out = pandoc_cli(capsys)
    assert code == 0 and out["installed_now"] is False


def test_a_missing_pandoc_is_installed_and_then_found(capsys, monkeypatch):
    states = iter([MISSING, FOUND])
    downloads = []
    monkeypatch.setattr(ip, "find_pandoc", lambda: next(states))
    monkeypatch.setattr(ip, "download_pandoc", lambda: downloads.append(1))
    code, out = pandoc_cli(capsys)
    assert code == 0 and out["installed_now"] is True and len(downloads) == 1


def test_a_failed_install_leaves_word_output_to_be_turned_off(capsys, monkeypatch):
    def fail():
        raise RuntimeError("no network")

    monkeypatch.setattr(ip, "find_pandoc", lambda: MISSING)
    monkeypatch.setattr(ip, "download_pandoc", fail)
    code, out = pandoc_cli(capsys)
    assert code == 4 and "the install failed" in out["reason"] and "winget" in out["next"]


def test_a_missing_pypandoc_package_is_not_papered_over(capsys, monkeypatch):
    missing = {"found": False, "reason": "the pypandoc package is not installed"}
    monkeypatch.setattr(ip, "find_pandoc", lambda: missing)
    monkeypatch.setattr(ip, "download_pandoc", forbid_download)
    code, out = pandoc_cli(capsys)
    assert code == 4 and out["next"] == "pip install pypandoc"


def test_the_skill_asks_before_installing_pandoc():
    text = " ".join((SKILL_DIR / "SKILL.md").read_text(encoding="utf-8").split())
    assert "install_pandoc.py --check" in text
    assert "ask whether to install it now" in text
    assert "Never install Pandoc without their yes" in text
    assert "set `settings.docx` to `false`" in text
