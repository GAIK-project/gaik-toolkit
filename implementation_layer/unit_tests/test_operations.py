"""gaik.operations offline: no network call anywhere.

Fakes replace only the object that would call a model (DataExtractor, SchemaGenerator,
Transcriber, the chat client, the Jev client). The schema builder, SourceTracing and the
parsers run for real.
"""

from __future__ import annotations

import asyncio
import logging
import subprocess
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from gaik import operations
from gaik.operations import (
    Classification,
    ExtractedField,
    FieldDefinition,
    OperationSettings,
    build_schema,
    classify_text,
    extract_fields,
    generate_fields,
    parse_document,
    quiet_stdout,
    run_async,
    transcribe_audio,
)
from pydantic import ValidationError

MARKER = "PRIVATE-TEXT-THAT-MUST-NOT-BE-LOGGED"
CONFIG = {"provider": "azure", "use_azure": True, "model": "fake-model", "api_key": "fake-key"}
SETTINGS = OperationSettings(config=CONFIG)

NOTE = (
    "Service visit on 14.3.2026 at Kallio pumping station.\n"
    "Technician Aino Virtanen replaced the shaft seal.\n"
    "Two valves were checked. Status: OK.\n"
)


# settings ------------------------------------------------------------------------------------


def test_llm_config_adds_the_timeout_and_copies_the_config():
    config = SETTINGS.llm_config()

    assert config["timeout"] == 120.0
    assert config["model"] == "fake-model"
    assert "timeout" not in CONFIG


def test_a_timeout_already_in_the_config_wins():
    settings = OperationSettings(config={**CONFIG, "timeout": 600.0}, timeout=30)

    assert settings.llm_config()["timeout"] == 600.0


def test_no_timeout_is_set_when_the_setting_is_none():
    assert "timeout" not in OperationSettings(config=CONFIG, timeout=None).llm_config()


def test_the_provider_config_is_read_when_no_config_is_given(monkeypatch):
    pytest.importorskip("openai")
    monkeypatch.setenv("AZURE_API_KEY", "fake-key")
    monkeypatch.setenv("AZURE_ENDPOINT", "https://example.invalid")

    config = OperationSettings(provider="azure", timeout=45).llm_config()

    assert config["provider"] == "azure"
    assert config["timeout"] == 45


def test_a_missing_variable_raises_the_components_own_error(monkeypatch):
    pytest.importorskip("openai")
    monkeypatch.delenv("AZURE_API_KEY", raising=False)
    monkeypatch.setenv("AZURE_ENDPOINT", "https://example.invalid")

    with pytest.raises(ValueError, match="AZURE_API_KEY"):
        OperationSettings(provider="azure").llm_config()


def test_repr_hides_the_config():
    assert "fake-key" not in repr(SETTINGS)
    assert "config" not in repr(SETTINGS)


# field definitions ---------------------------------------------------------------------------


def test_a_field_definition_needs_a_name():
    with pytest.raises(ValidationError):
        FieldDefinition(name="   ")


def test_options_are_for_text_fields_and_not_empty():
    assert FieldDefinition(name="status", options=["ok", "fault"]).options == ["ok", "fault"]
    with pytest.raises(ValidationError):
        FieldDefinition(name="status", options=[])
    with pytest.raises(ValidationError):
        FieldDefinition(name="count", type="int", options=["1", "2"])


def test_format_is_for_date_fields():
    assert FieldDefinition(name="day", type="date", format="%d.%m.%Y").format == "%d.%m.%Y"
    with pytest.raises(ValidationError):
        FieldDefinition(name="site", format="%d.%m.%Y")


def test_unknown_keys_and_types_are_refused():
    with pytest.raises(ValidationError):
        FieldDefinition(name="site", kind="text")
    with pytest.raises(ValidationError):
        FieldDefinition(name="rows", type="list[dict]")


def test_display_label_is_the_label_or_the_readable_name():
    assert FieldDefinition(name="work_done").display_label == "Work done"
    assert FieldDefinition(name="Sää ja lämpötila").display_label == "Sää ja lämpötila"
    assert FieldDefinition(name="work_done", label="Tehty työ").display_label == "Tehty työ"


# build_schema --------------------------------------------------------------------------------


def test_safe_names_keep_the_letters_and_map_back():
    pytest.importorskip("openai")
    schema = build_schema(
        [
            FieldDefinition(name="Sää ja lämpötila"),
            FieldDefinition(name="Saa ja lampotila"),
            FieldDefinition(name="Työn tekijä (nimi)"),
            FieldDefinition(name="2. käynti"),
            FieldDefinition(name="§§§"),
        ]
    )

    assert schema.names == {
        "saa_ja_lampotila": "Sää ja lämpötila",
        "saa_ja_lampotila_2": "Saa ja lampotila",
        "tyon_tekija_nimi": "Työn tekijä (nimi)",
        "f_2_kaynti": "2. käynti",
        "field": "§§§",
    }
    assert list(schema.model.model_fields) == list(schema.names)
    assert [spec.field_name for spec in schema.requirements.fields] == list(schema.names)


def test_build_schema_maps_each_definition_to_a_field_spec():
    pytest.importorskip("openai")
    schema = build_schema(
        [
            FieldDefinition(name="site", required=True, description="Where the work was done"),
            FieldDefinition(name="status", options=["ok", "fault"]),
            FieldDefinition(name="visit_date", type="date", format="%d.%m.%Y"),
        ],
        use_case_name="service note",
    )

    site, status, visit_date = schema.requirements.fields
    assert (site.nullable, site.description) == (False, "Where the work was done")
    assert (status.nullable, status.enum, status.description) == (True, ["ok", "fault"], "Status")
    assert (visit_date.field_type, visit_date.format) == ("date", "%d.%m.%Y")
    assert schema.requirements.use_case_name == "service note"


def test_the_built_model_converts_to_a_strict_schema_and_makes_no_client(monkeypatch):
    pytest.importorskip("openai")
    import openai
    from openai.lib._pydantic import to_strict_json_schema

    def no_client(*args, **kwargs):
        raise AssertionError("build_schema must not make a client")

    # AzureOpenAI and the async clients are built on the same two constructors.
    monkeypatch.setattr(openai.OpenAI, "__init__", no_client)
    monkeypatch.setattr(openai.AsyncOpenAI, "__init__", no_client)
    kinds = ("str", "int", "float", "bool", "date", "decimal", "list[str]")
    fields = [FieldDefinition(name=f"{kind} field", type=kind) for kind in kinds]
    fields += [FieldDefinition(name=f"{kind} must", type=kind, required=True) for kind in kinds]
    fields.append(FieldDefinition(name="status", options=["ok", "fault"]))

    schema = build_schema(fields)
    strict = to_strict_json_schema(schema.model)

    assert strict["additionalProperties"] is False
    assert set(strict["required"]) == set(schema.names)
    assert len(strict["properties"]) == len(fields)


def test_build_schema_refuses_no_fields_and_repeated_names():
    with pytest.raises(ValueError, match="no fields"):
        build_schema([])
    with pytest.raises(ValueError, match="same name"):
        build_schema([FieldDefinition(name="site"), FieldDefinition(name="site")])


# parse_document ------------------------------------------------------------------------------


def _pdf(path: Path, pages: list[str]) -> Path:
    pymupdf = pytest.importorskip("pymupdf")
    document = pymupdf.open()
    for text in pages:
        page = document.new_page()
        if text:
            page.insert_text((72, 72), text)
    document.save(path)
    document.close()
    return path


def test_a_pdf_gives_one_entry_per_page(tmp_path):
    path = _pdf(tmp_path / "note.pdf", ["First page of the note.", "Second page of the note."])

    document = parse_document(path)

    assert document.kind == "pdf"
    assert document.pages == ["First page of the note.", "Second page of the note."]
    assert document.text == "First page of the note.\n\nSecond page of the note."


def test_a_page_that_prints_a_page_mark_itself_is_still_split_by_page(tmp_path):
    path = _pdf(tmp_path / "marks.pdf", ["See the table below.\n[Page 2]\nmore text", "Last."])

    document = parse_document(path)

    assert len(document.pages) == 2
    assert "[Page 2]" in document.pages[0]
    assert document.pages[1] == "Last."


def test_an_empty_page_keeps_its_place_and_stays_out_of_the_text(tmp_path):
    path = _pdf(tmp_path / "gap.pdf", ["One.", "", "Three."])

    document = parse_document(path)

    assert document.pages == ["One.", "", "Three."]
    assert document.text == "One.\n\nThree."


def test_a_pdf_without_text_raises(tmp_path):
    path = _pdf(tmp_path / "scan.pdf", ["", ""])

    with pytest.raises(ValueError, match="no text was found"):
        parse_document(path)


def test_the_kind_comes_from_the_content_not_the_name(tmp_path):
    path = _pdf(tmp_path / "really_a_pdf.txt", ["A PDF under a text name."])

    assert parse_document(path).kind == "pdf"


@pytest.mark.parametrize("name", ["formats.md", "formats.txt"])
def test_a_note_that_mentions_the_pdf_header_is_text(tmp_path, name):
    text = "# Formats\n\nA PDF starts with the bytes %PDF-1.7 and ends with %%EOF."
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")

    document = parse_document(path)

    assert (document.kind, document.text) == ("text", text)


def test_a_pdf_whose_header_is_not_the_first_thing_in_the_file_is_still_a_pdf(tmp_path):
    plain = _pdf(tmp_path / "plain.pdf", ["A page after a line of junk."])
    path = tmp_path / "prefixed.pdf"
    path.write_bytes(b"a line some scanner wrote first\n" + plain.read_bytes())

    document = parse_document(path)

    assert (document.kind, document.text) == ("pdf", "A page after a line of junk.")


def test_a_docx_that_unpacks_to_far_more_than_its_size_is_refused_unread(tmp_path, monkeypatch):
    import zipfile

    docx = pytest.importorskip("docx")
    plain = tmp_path / "plain.docx"
    docx.Document().save(str(plain))
    path = tmp_path / "packed_small.docx"
    megabyte = b"<w:p/>" * (1024 * 1024 // 6 + 1)
    with zipfile.ZipFile(plain) as source, zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as out:
        for part in source.infolist():
            if part.filename != "word/document.xml":
                out.writestr(part, source.read(part.filename))
        with out.open("word/document.xml", "w") as body:
            for _ in range(51):
                body.write(megabyte)
    from gaik.software_components import parsers

    def never(*args, **kwargs):
        raise AssertionError("the file must be refused before a parser opens it")

    monkeypatch.setattr(parsers.DocxParser, "parse_docx", never)

    assert path.stat().st_size < 1024 * 1024
    with pytest.raises(ValueError, match="too large when unpacked"):
        parse_document(path)


def test_the_unpacked_size_of_a_docx_counts_every_part(tmp_path, monkeypatch):
    import zipfile

    from gaik.operations import documents

    path = tmp_path / "pictures.docx"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_STORED) as archive:
        archive.writestr("word/document.xml", "<w:document/>")
        archive.writestr("word/media/image1.png", bytes(4000))
    monkeypatch.setattr(documents, "MAX_DOCX_UNPACKED_BYTES", 3000)

    # Stored parts are no markup, so only the total stops this file.
    with pytest.raises(ValueError, match="too large when unpacked"):
        parse_document(path)


def test_a_docx_is_one_page_of_markdown(tmp_path):
    docx = pytest.importorskip("docx")
    path = tmp_path / "note.docx"
    document = docx.Document()
    document.add_heading("Service note", level=1)
    document.add_paragraph("The pump was serviced.")
    document.save(str(path))

    parsed = parse_document(path)

    assert parsed.kind == "docx"
    assert parsed.pages == [parsed.text]
    assert "# Service note" in parsed.text and "The pump was serviced." in parsed.text


def test_a_zip_that_is_not_a_docx_is_refused(tmp_path):
    import zipfile

    path = tmp_path / "archive.docx"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("readme.txt", "not a document")

    with pytest.raises(ValueError, match="unsupported file type"):
        parse_document(path)


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        ("Sää oli kylmä.\r\nTyö tehtiin.".encode(), "Sää oli kylmä.\nTyö tehtiin."),
        ("﻿Sää oli kylmä.".encode(), "Sää oli kylmä."),
        ("Sää oli kylmä.".encode("cp1252"), "Sää oli kylmä."),
        ("Sää oli kylmä.".encode("utf-16"), "Sää oli kylmä."),
    ],
    ids=["utf-8", "utf-8 with a mark", "cp1252", "utf-16"],
)
def test_a_text_file_is_decoded(tmp_path, data, expected):
    path = tmp_path / "note.txt"
    path.write_bytes(data)

    document = parse_document(path)

    assert (document.kind, document.pages, document.text) == ("text", [expected], expected)


def test_markdown_is_text(tmp_path):
    path = tmp_path / "note.MD"
    path.write_text("# Note\n\nBody.", encoding="utf-8")

    assert parse_document(path).kind == "text"


@pytest.mark.parametrize("name", [".txt", ".env", "notes", "notes.csv", "notes.json"])
def test_a_dot_file_or_another_suffix_is_never_read_as_text(tmp_path, name):
    path = tmp_path / name
    path.write_text("plain text", encoding="utf-8")

    with pytest.raises(ValueError, match="unsupported file type"):
        parse_document(path)


def test_binary_content_under_a_text_name_is_refused(tmp_path):
    path = tmp_path / "data.txt"
    path.write_bytes(b"\x00\x01\x02binary")

    with pytest.raises(ValueError, match="unsupported file type"):
        parse_document(path)


def test_an_empty_text_file_and_a_missing_file_raise(tmp_path):
    (tmp_path / "empty.txt").write_text("  \n", encoding="utf-8")

    with pytest.raises(ValueError, match="no text was found"):
        parse_document(tmp_path / "empty.txt")
    with pytest.raises(FileNotFoundError):
        parse_document(tmp_path / "missing.pdf")


# transcribe_audio ----------------------------------------------------------------------------


class _FakeTranscriber:
    """Stands in for gaik's Transcriber; ``raw`` is the transcript it returns."""

    raw = "Hello from the site."
    calls: list[dict] = []

    def __init__(self, api_config, output_dir, **options):
        self.call = {"config": api_config, "output_dir": Path(output_dir), **options}
        type(self).calls.append(self.call)

    def transcribe(self, file_path, *, custom_context=""):
        self.call["custom_context"] = custom_context
        self.call["folder_existed"] = self.call["output_dir"].is_dir()
        print(f"Transcribing {MARKER}")
        if isinstance(self.raw, Exception):
            raise self.raw
        return SimpleNamespace(
            raw_transcript=self.raw, audio_duration_s=12.5, model_used="fake-transcribe"
        )


@pytest.fixture
def transcriber(monkeypatch, tmp_path):
    package = pytest.importorskip("gaik.software_components.transcriber")
    if not hasattr(package, "Transcriber"):
        pytest.skip("the transcriber extra is not installed")

    class Fake(_FakeTranscriber):
        calls: list[dict] = []

    monkeypatch.setattr(package, "Transcriber", Fake)
    Fake.audio = tmp_path / "note.wav"
    Fake.audio.write_bytes(b"RIFF fake audio")
    Fake.work = tmp_path / "work"
    Fake.work.mkdir()
    Fake.settings = OperationSettings(config=CONFIG, work_dir=Fake.work)
    return Fake


def test_transcribe_returns_the_text_and_removes_its_folder(transcriber):
    transcript = transcribe_audio(transcriber.audio, settings=transcriber.settings)

    (call,) = transcriber.calls
    assert transcript.model_dump() == {
        "text": "Hello from the site.",
        "duration_s": 12.5,
        "language": None,
        "model": "fake-transcribe",
        "failed_segments": 0,
    }
    assert call["folder_existed"] and call["output_dir"].parent == transcriber.work
    assert call["output_dir"].name.startswith("gaik-transcribe-")
    assert list(transcriber.work.iterdir()) == []
    assert (call["language"], call["custom_context"]) == ("auto", "")
    assert call["config"]["timeout"] == 120.0


def test_the_folder_is_removed_when_the_transcriber_fails(transcriber):
    transcriber.raw = ConnectionError("provider said no")

    with pytest.raises(ConnectionError):
        transcribe_audio(transcriber.audio, settings=transcriber.settings)

    assert transcriber.calls[0]["folder_existed"]
    assert list(transcriber.work.iterdir()) == []


def test_the_language_goes_into_the_prompt_and_the_constructor(transcriber):
    transcript = transcribe_audio(
        transcriber.audio,
        language="Finnish",
        context="Names: Kallio, Virtanen.",
        settings=transcriber.settings,
    )

    (call,) = transcriber.calls
    assert call["language"] == "Finnish"
    assert call["custom_context"] == (
        "Names: Kallio, Virtanen.\nLanguage of the recording: Finnish."
    )
    assert transcript.language == "Finnish"


def test_part_headers_are_removed_and_failed_parts_counted(transcriber):
    transcriber.raw = (
        "\n[Timestamp: 00:00 - 19:30]\nFirst part."
        "\n\n\n[Timestamp: 19:30 - 39:00]\n[Transcription failed for segment 2]"
        "\n\n\n[Timestamp: 39:00 - 58:30]\nThird part."
    )

    transcript = transcribe_audio(transcriber.audio, settings=transcriber.settings)

    assert transcript.text == "First part.\n\nThird part."
    assert transcript.failed_segments == 1


def test_a_recording_whose_every_part_failed_raises(transcriber):
    transcriber.raw = (
        "\n[Timestamp: 00:00 - 19:30]\n[Transcription failed for segment 1]"
        "\n\n\n[Timestamp: 19:30 - 39:00]\n[Transcription failed for segment 2]"
    )

    with pytest.raises(RuntimeError, match="every part"):
        transcribe_audio(transcriber.audio, settings=transcriber.settings)


def test_a_silent_recording_raises(transcriber):
    transcriber.raw = "  \n"

    with pytest.raises(ValueError, match="no speech"):
        transcribe_audio(transcriber.audio, settings=transcriber.settings)


def test_bad_audio_input_is_refused_before_any_call(transcriber, tmp_path):
    (tmp_path / "note.txt").write_text("not audio", encoding="utf-8")
    (tmp_path / "empty.mp3").write_bytes(b"")

    with pytest.raises(ValueError, match="unsupported audio type"):
        transcribe_audio(tmp_path / "note.txt", settings=transcriber.settings)
    with pytest.raises(ValueError, match="empty"):
        transcribe_audio(tmp_path / "empty.mp3", settings=transcriber.settings)
    with pytest.raises(FileNotFoundError):
        transcribe_audio(tmp_path / "missing.wav", settings=transcriber.settings)
    assert transcriber.calls == []


# generate_fields -----------------------------------------------------------------------------


def _generator(monkeypatch, requirements, structure_type="flat"):
    """Replace SchemaGenerator with one that returns the given requirements."""
    extractor = pytest.importorskip("gaik.software_components.extractor")
    seen: dict = {}

    class FakeGenerator:
        def __init__(self, config, **options):
            seen.update(config=config, **options)

        def generate_schema_with_usage(self, user_requirements):
            seen["requirement"] = user_requirements
            print(f"Generating schema for {MARKER}")
            return SimpleNamespace(
                requirements=requirements,
                structure_analysis=SimpleNamespace(structure_type=structure_type),
            )

    monkeypatch.setattr(extractor, "SchemaGenerator", FakeGenerator)
    return seen


def _requirements(*specs, name="service"):
    from gaik.software_components.extractor import ExtractionRequirements, FieldSpec

    return ExtractionRequirements(use_case_name=name, fields=[FieldSpec(**spec) for spec in specs])


def test_generate_fields_maps_a_flat_result_field_by_field(monkeypatch):
    seen = _generator(
        monkeypatch,
        _requirements(
            {"field_name": "site", "field_type": "str", "description": "Where", "required": True},
            {
                "field_name": "status",
                "field_type": "str",
                "description": "State",
                "enum": ["ok", "fault"],
                "nullable": True,
            },
            {
                "field_name": "visit_date",
                "field_type": "date",
                "description": "Day of the visit",
                "format": "%d.%m.%Y",
                "nullable": True,
            },
            {"field_name": "parts", "field_type": "list[dict]", "description": "Parts used"},
            {"field_name": "cost", "field_type": "decimal", "description": "Cost in euros"},
        ),
    )

    fields = generate_fields(
        "  Collect the site, status, date, parts and cost.  ", settings=SETTINGS
    )

    assert [field.model_dump(exclude={"label"}) for field in fields] == [
        {
            "name": "site",
            "type": "str",
            "description": "Where",
            "required": True,
            "options": None,
            "format": None,
        },
        {
            "name": "status",
            "type": "str",
            "description": "State",
            "required": False,
            "options": ["ok", "fault"],
            "format": None,
        },
        {
            "name": "visit_date",
            "type": "date",
            "description": "Day of the visit",
            "required": False,
            "options": None,
            "format": "%d.%m.%Y",
        },
        {
            "name": "parts",
            "type": "list[str]",
            "description": "Parts used",
            "required": True,
            "options": None,
            "format": None,
        },
        {
            "name": "cost",
            "type": "decimal",
            "description": "Cost in euros",
            "required": True,
            "options": None,
            "format": None,
        },
    ]
    assert seen["requirement"] == "Collect the site, status, date, parts and cost."
    assert (seen["temperature"], seen["reasoning_effort"]) == (0.0, None)
    assert seen["config"]["timeout"] == 120.0


def test_a_parent_with_collections_gives_one_list_field_per_collection(monkeypatch):
    from gaik.software_components.extractor import (
        ChildRequirements,
        CompositeExtractionRequirements,
    )

    composite = CompositeExtractionRequirements(
        parent_requirements=_requirements(
            {"field_name": "order_number", "field_type": "str", "description": "Order number"}
        ),
        children=[
            ChildRequirements(
                container_name="line_items",
                container_description="The ordered products",
                requirements=_requirements(
                    {"field_name": "product", "field_type": "str", "description": "Product"},
                    {"field_name": "quantity", "field_type": "int", "description": "Pieces"},
                    name="line item",
                ),
            )
        ],
    )
    _generator(monkeypatch, composite, structure_type="parent_with_nested_list")

    fields = generate_fields("An order with its line items.", settings=SETTINGS)

    assert [(field.name, field.type) for field in fields] == [
        ("order_number", "str"),
        ("line_items", "list[str]"),
    ]
    assert fields[1].description == "The ordered products (one entry per item: product, quantity)"
    assert fields[1].required is False


def test_a_requirement_for_rows_is_refused(monkeypatch):
    _generator(
        monkeypatch,
        _requirements({"field_name": "product", "field_type": "str", "description": "Product"}),
        structure_type="nested_list",
    )

    with pytest.raises(ValueError, match="list of items"):
        generate_fields("Every row of the price list.", settings=SETTINGS)


def test_a_short_requirement_and_an_empty_result_raise(monkeypatch):
    seen = _generator(monkeypatch, _requirements())

    with pytest.raises(ValueError, match="too short"):
        generate_fields(" a ", settings=SETTINGS)
    assert seen == {}
    with pytest.raises(RuntimeError, match="no fields"):
        generate_fields("Collect something.", settings=SETTINGS)


# extract_fields ------------------------------------------------------------------------------

FIELDS = [
    FieldDefinition(name="Käyntipäivä", type="date", label="Visit date"),
    FieldDefinition(name="site", required=True),
    FieldDefinition(name="technician"),
    FieldDefinition(name="status", options=["ok", "fault"]),
    FieldDefinition(name="valves", type="int"),
    FieldDefinition(name="Sää"),
    FieldDefinition(name="notes"),
    FieldDefinition(name="work", type="list[str]"),
    FieldDefinition(name="cost", type="decimal"),
]

RECORD = {
    "kayntipaiva": "2026-03-14",
    "site": "Kallio pumping station",
    "technician": "Aino Mäkinen",
    "status": "OK",
    "valves": 2,
    "saa": None,
    "notes": "",
    "work": ["replaced the shaft seal", " "],
    "cost": None,
}

CITATIONS = [
    {"field": "kayntipaiva", "document": 1, "page": 1, "quote": "service visit  on 14.3.2026"},
    {"field": "site", "document": 1, "page": 1, "quote": "at Kallio pumping station"},
    {"field": "site", "document": 1, "page": 1, "quote": "a second quote that is ignored"},
    {"field": "technician", "document": 1, "page": 1, "quote": "Technician Aino Mäkinen"},
    {"field": "valves", "document": 1, "page": 1, "quote": "Two valves were checked"},
    {"field": "saa", "document": 1, "page": 1, "quote": "Status: OK"},
    {"field": "work[0]", "document": 1, "page": 1, "quote": "replaced the shaft seal"},
    {"field": "unknown_field", "document": 1, "page": 1, "quote": "Status: OK"},
]


def _extractor(monkeypatch, record, citations=None):
    """Replace DataExtractor with one that returns the record, as the real one would."""
    extractor = pytest.importorskip("gaik.software_components.extractor")
    seen: dict = {}

    class FakeExtractor:
        def __init__(self, config, **options):
            seen.update(config=config, **options)

        def extract(self, extraction_model, requirements, user_requirements, documents):
            seen.update(
                model=extraction_model,
                requirements=requirements,
                task=user_requirements,
                documents=documents,
            )
            print(f"Processing document {MARKER}")
            if record is None:
                return []
            row = dict(record)
            if "field_sources" in extraction_model.model_fields:
                row["field_sources"] = {"items": citations or []}
            return [row]

    monkeypatch.setattr(extractor, "DataExtractor", FakeExtractor)
    return seen


def test_extract_fields_returns_values_with_checked_evidence(monkeypatch):
    seen = _extractor(monkeypatch, RECORD, CITATIONS)

    values = extract_fields(NOTE, FIELDS, instructions="Read the service note.", settings=SETTINGS)
    by_name = {item.name: item for item in values}

    assert [item.name for item in values] == [field.name for field in FIELDS]
    assert all(isinstance(item, ExtractedField) for item in values)
    # A quote found in the text comes back exactly as the text has it.
    assert by_name["Käyntipäivä"].model_dump() == {
        "name": "Käyntipäivä",
        "label": "Visit date",
        "value": "2026-03-14",
        "evidence": "Service visit on 14.3.2026",
        "verdict": "verified",
    }
    assert (by_name["site"].evidence, by_name["site"].verdict) == (
        "at Kallio pumping station",
        "verified",
    )
    # A quote that is not in the text is no evidence.
    assert (by_name["technician"].evidence, by_name["technician"].verdict) == (None, "check")
    # A value without a citation.
    assert (by_name["status"].value, by_name["status"].evidence) == ("ok", None)
    assert by_name["status"].verdict == "unchecked"
    # A number the quote spells out in words cannot be compared.
    assert (by_name["valves"].value, by_name["valves"].evidence) == (2, "Two valves were checked")
    assert by_name["valves"].verdict == "unchecked"
    # No value: no evidence, whatever the model cited.
    for name in ("Sää", "notes", "cost"):
        assert by_name[name].model_dump(include={"value", "evidence", "verdict"}) == {
            "value": None,
            "evidence": None,
            "verdict": None,
        }
    assert by_name["Sää"].label == "Sää"
    assert by_name["work"].value == ["replaced the shaft seal"]
    assert by_name["work"].evidence == "replaced the shaft seal"

    assert seen["documents"] == [NOTE]
    assert "field_sources" in seen["model"].model_fields
    assert seen["task"].startswith("Read the service note.\n\nRULES:")
    assert "SOURCE CITATIONS" in seen["task"]
    assert [spec.field_name for spec in seen["requirements"].fields][:2] == ["kayntipaiva", "site"]
    assert (seen["temperature"], seen["reasoning_effort"]) == (0.0, None)
    assert seen["config"]["timeout"] == 120.0


def test_without_evidence_no_tracing_is_done(monkeypatch):
    tracing = pytest.importorskip("gaik.software_components.source_tracing")
    seen = _extractor(monkeypatch, RECORD, CITATIONS)

    def no_tracing(*args, **kwargs):
        raise AssertionError("SourceTracing must not be used without evidence")

    monkeypatch.setattr(tracing, "SourceTracing", no_tracing)

    values = extract_fields(NOTE, FIELDS, evidence=False, settings=SETTINGS)

    assert "field_sources" not in seen["model"].model_fields
    assert "SOURCE CITATIONS" not in seen["task"]
    assert seen["task"].startswith("Fill the fields of the schema from the text.")
    assert all(item.evidence is None and item.verdict is None for item in values)
    assert {item.name: item.value for item in values}["site"] == "Kallio pumping station"


def test_values_are_made_json_safe(monkeypatch):
    from decimal import Decimal

    fields = [
        FieldDefinition(name="cost", type="decimal"),
        FieldDefinition(name="share", type="float"),
        FieldDefinition(name="done", type="bool"),
        FieldDefinition(name="status", options=["ok", "fault"]),
        FieldDefinition(name="tasks", type="list[str]"),
    ]
    record = {
        "cost": Decimal("1234.50"),
        "share": float("nan"),
        "done": False,
        "status": "broken",
        "tasks": [],
    }
    _extractor(monkeypatch, record)

    values = extract_fields(NOTE, fields, evidence=False, settings=SETTINGS)

    assert [item.value for item in values] == ["1234.50", None, False, None, None]
    assert [item.model_dump(mode="json")["value"] for item in values][0] == "1234.50"


def test_bad_input_and_no_record_raise(monkeypatch):
    seen = _extractor(monkeypatch, None)

    with pytest.raises(ValueError, match="text is empty"):
        extract_fields("  \n", FIELDS, settings=SETTINGS)
    with pytest.raises(ValueError, match="no fields"):
        extract_fields(NOTE, [], settings=SETTINGS)
    assert seen == {}
    with pytest.raises(RuntimeError, match="no record"):
        extract_fields(NOTE, FIELDS, settings=SETTINGS)


# classify_text -------------------------------------------------------------------------------

LABELS = {"urgent": "Needs action today", "normal": "Can wait"}


class _FakeJev:
    model = "jev-fake"

    def __init__(self, answer):
        self.answer = answer
        self.calls: list[tuple] = []

    def classify(self, text, classes, instructions=None):
        self.calls.append((text, classes, instructions))
        return self.answer


def test_classify_with_jev_maps_its_answer():
    jev = _FakeJev(
        {
            "class": "urgent",
            "confidence": 0.93,
            "probabilities": {"urgent": 0.97, "normal": 0.03},
            "predicted": "urgent",
            "model": "jev-1.13.0",
        }
    )

    result = classify_text(
        " Water is leaking onto the cabinet. ",
        {"urgent": "Needs action today", "normal": ""},
        instructions="How urgent is this?",
        jev=jev,
    )

    assert result == Classification(
        label="urgent",
        confidence=0.93,
        probabilities={"urgent": 0.97, "normal": 0.03},
        model="jev-1.13.0",
        backend="jev",
    )
    assert jev.calls == [
        (
            "Water is leaking onto the cabinet.",
            {"urgent": "Needs action today", "normal": None},
            "How urgent is this?",
        )
    ]


def test_a_jev_label_that_was_not_offered_raises():
    jev = _FakeJev({"class": "unknown", "confidence": 0.2, "probabilities": {}})

    with pytest.raises(RuntimeError, match="not offered"):
        classify_text("Some text.", ["urgent", "normal"], jev=jev)


def _chat(monkeypatch, best, scores, provider_client=False):
    """Replace the chat client with one that answers with the given scores."""
    llm = pytest.importorskip("gaik.software_components.llm")
    seen: dict = {}

    def answer(response_format):
        items = [{"label": label, "probability": value} for label, value in scores]
        return response_format(best=best, scores=items)

    def parse(**kwargs):
        seen.update(kwargs)
        message = SimpleNamespace(parsed=answer(kwargs["response_format"]))
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])

    class Provider:
        provider, model, raw = "anthropic", "fake-model", None

        def chat_parsed(self, messages, response_format, **kwargs):
            seen.update(messages=messages, response_format=response_format, **kwargs)
            return answer(response_format)

        def chat(self, *args, **kwargs):
            raise AssertionError

        def chat_stream(self, *args, **kwargs):
            raise AssertionError

        def embed(self, *args, **kwargs):
            raise AssertionError

    raw = SimpleNamespace(
        beta=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(parse=parse)))
    )
    client = Provider() if provider_client else raw
    monkeypatch.setattr(llm, "build_compat_client", lambda config: client)
    return seen


def test_classify_with_a_chat_model_normalises_the_scores(monkeypatch):
    seen = _chat(monkeypatch, "normal", [("urgent", 3.0), ("normal", 1.0), ("urgent", 9.0)])

    result = classify_text(f"A leak. {MARKER}", LABELS, settings=SETTINGS)

    assert result == Classification(
        label="urgent",
        confidence=0.75,
        probabilities={"urgent": 0.75, "normal": 0.25},
        model="fake-model",
        backend="llm",
    )
    assert seen["model"] == "fake-model"
    assert (seen["temperature"], seen["top_p"], seen["timeout"]) == (0.0, 1.0, 120.0)
    assert "reasoning_effort" not in seen
    user = seen["messages"][1]["content"]
    assert '- "urgent": Needs action today' in user and MARKER in user
    assert user.startswith("Which label describes the text best?")


def test_temperature_is_left_out_when_none_and_effort_is_passed(monkeypatch):
    seen = _chat(monkeypatch, "urgent", [("urgent", 1.0)])
    settings = OperationSettings(config=CONFIG, temperature=None, reasoning_effort="low")

    classify_text("A leak.", LABELS, settings=settings)

    assert "temperature" not in seen
    assert seen["reasoning_effort"] == "low"


def test_a_tie_goes_to_the_models_best_label(monkeypatch):
    _chat(monkeypatch, "normal", [("urgent", 0.5), ("normal", 0.5)])

    result = classify_text("Hard to say.", LABELS, settings=SETTINGS)

    assert (result.label, result.confidence) == ("normal", 0.5)


def test_negative_and_missing_scores_still_sum_to_one(monkeypatch):
    _chat(monkeypatch, "c", [("a", -2.0), ("b", 1.0), ("c", 2.0)])

    result = classify_text("Text.", ["a", "b", "c", "d"], settings=SETTINGS)

    assert result.probabilities == {"a": 0.0, "b": 0.3333, "c": 0.6667, "d": 0.0}
    assert result.label == "c"
    assert round(sum(result.probabilities.values()), 4) == 1.0


def test_scores_that_are_all_zero_fall_back_to_the_best_label(monkeypatch):
    _chat(monkeypatch, "normal", [])

    result = classify_text("Text.", LABELS, settings=SETTINGS)

    assert result.probabilities == {"urgent": 0.0, "normal": 1.0}


def test_another_provider_goes_through_its_provider_client(monkeypatch):
    seen = _chat(monkeypatch, "urgent", [("urgent", 0.9), ("normal", 0.1)], provider_client=True)

    result = classify_text("A leak.", LABELS, instructions="How urgent?", settings=SETTINGS)

    assert (result.label, result.backend) == ("urgent", "llm")
    assert seen["model"] == "fake-model"
    assert seen["messages"][1]["content"].startswith("How urgent?")
    assert "temperature" not in seen


@pytest.mark.parametrize(
    "labels",
    [
        ["only"],
        [],
        ["a", "a"],
        ["a", " "],
        {"a": "x", " a": "y"},
        "ab",
        [str(n) for n in range(256)],
    ],
    ids=["one", "none", "repeated", "blank", "same after trimming", "a string", "too many"],
)
def test_bad_labels_are_refused(labels):
    with pytest.raises(ValueError, match="label"):
        classify_text("Some text.", labels, settings=SETTINGS)


def test_blank_text_is_refused():
    with pytest.raises(ValueError, match="text is empty"):
        classify_text("   ", LABELS, settings=SETTINGS)


# quiet stdout --------------------------------------------------------------------------------


def test_quiet_stdout_holds_what_the_block_printed(capsys):
    print("before")
    with quiet_stdout() as printed:
        print("inside")
        with quiet_stdout() as inner:
            print("nested")
        assert inner is printed
        print("still inside")
    print("after")

    assert printed.getvalue() == "inside\nnested\nstill inside\n"
    assert capsys.readouterr().out == "before\nafter\n"


def test_two_threads_capture_their_own_prints_while_the_main_thread_prints(capsys):
    ready = threading.Barrier(3)
    release = threading.Event()
    printed: dict[str, str] = {}

    def work(name: str) -> None:
        with quiet_stdout() as buffer:
            ready.wait(timeout=5)
            for step in range(20):
                print(f"{name} step {step}")
                time.sleep(0.001)
            release.wait(timeout=5)
            print(f"{name} done")
            printed[name] = buffer.getvalue()

    threads = [threading.Thread(target=work, args=(name,)) for name in ("first", "second")]
    for thread in threads:
        thread.start()
    ready.wait(timeout=5)
    print("the main thread still prints")
    release.set()
    for thread in threads:
        thread.join(timeout=5)

    assert capsys.readouterr().out == "the main thread still prints\n"
    for name in ("first", "second"):
        expected = "".join(f"{name} step {step}\n" for step in range(20)) + f"{name} done\n"
        assert printed[name] == expected


def test_two_coroutines_capture_their_own_prints_across_an_await(capsys):
    printed: dict[str, str] = {}

    async def work(name: str, wait: float) -> None:
        await asyncio.sleep(wait)
        with quiet_stdout() as buffer:
            print(f"{name} starts")
            await asyncio.sleep(0.05)  # the other coroutines run while this one waits
            print(f"{name} ends")
            printed[name] = buffer.getvalue()
        print(f"{name} is out of its block")

    async def bystander() -> None:
        await asyncio.sleep(0.03)
        print("a bystander prints")

    async def scenario() -> None:
        # `second` enters while `first` is inside, and is still inside when `first` leaves.
        await asyncio.gather(work("first", 0.0), work("second", 0.02), bystander())

    asyncio.run(scenario())

    assert printed == {
        "first": "first starts\nfirst ends\n",
        "second": "second starts\nsecond ends\n",
    }
    assert capsys.readouterr().out == (
        "a bystander prints\nfirst is out of its block\nsecond is out of its block\n"
    )


def test_a_worker_thread_started_inside_a_block_is_captured_with_it(capsys):
    async def scenario() -> str:
        with quiet_stdout() as buffer:
            await asyncio.to_thread(print, "from the worker")
        await asyncio.to_thread(print, "after the block")
        return buffer.getvalue()

    assert asyncio.run(scenario()) == "from the worker\n"
    assert capsys.readouterr().out == "after the block\n"


def test_an_operation_keeps_the_components_prints_out_of_stdout(monkeypatch, capsys):
    _extractor(monkeypatch, RECORD, CITATIONS)

    extract_fields(NOTE, FIELDS, settings=SETTINGS)
    assert MARKER not in capsys.readouterr().out

    extract_fields(NOTE, FIELDS, settings=OperationSettings(config=CONFIG, quiet=False))
    assert MARKER in capsys.readouterr().out


def test_the_stand_in_forwards_what_it_does_not_handle():
    with quiet_stdout():
        pass

    assert type(sys.stdout).__name__ == "_ThreadStdout"
    assert sys.stdout.encoding
    assert sys.stdout.writable()
    assert not sys.stdout.closed


def test_the_stand_in_works_in_a_process_without_stdout(monkeypatch):
    import io

    monkeypatch.setattr(sys, "stdout", None)

    with quiet_stdout() as printed:
        print("inside")
    print("dropped, as it would be without the stand-in")

    assert printed.getvalue() == "inside\n"
    with pytest.raises(io.UnsupportedOperation):
        sys.stdout.fileno()


def test_the_stand_in_outlives_the_stream_it_stood_in_for(monkeypatch):
    """A library that kept ``sys.stdout`` (colorama does) asks it questions at exit."""
    import io

    gone = io.StringIO()
    monkeypatch.setattr(sys, "stdout", gone)
    with quiet_stdout():
        pass
    stand_in = sys.stdout
    gone.close()
    monkeypatch.setattr(sys, "stdout", io.StringIO())

    assert stand_in.isatty() is False
    stand_in.write("to where the process prints now")
    assert sys.stdout.getvalue() == "to where the process prints now"


# run_async -----------------------------------------------------------------------------------


def test_run_async_returns_the_value_from_a_worker_thread():
    def work(first: int, *, second: int) -> tuple[int, bool]:
        return first + second, threading.current_thread() is threading.main_thread()

    assert asyncio.run(run_async(work, 2, second=3)) == (5, False)


def test_run_async_raises_timeout_error_on_a_missed_deadline():
    async def call() -> float:
        started = time.perf_counter()
        with pytest.raises(TimeoutError):
            await run_async(time.sleep, 1.0, deadline=0.05)
        return time.perf_counter() - started

    # The wait ends at the deadline, not when the thread does.
    assert asyncio.run(call()) < 0.8


def test_run_async_passes_the_functions_error_on():
    def work() -> None:
        raise KeyError("missing")

    with pytest.raises(KeyError):
        asyncio.run(run_async(work, deadline=5))


def test_an_operation_captures_its_prints_in_the_worker_thread(monkeypatch, capsys):
    _extractor(monkeypatch, RECORD, CITATIONS)

    values = asyncio.run(run_async(extract_fields, NOTE, FIELDS, settings=SETTINGS, deadline=30))

    assert values[1].value == "Kallio pumping station"
    assert MARKER not in capsys.readouterr().out


# logs and imports ----------------------------------------------------------------------------


def test_nothing_from_the_input_reaches_the_log(monkeypatch, transcriber, tmp_path, caplog):
    private_note = NOTE + MARKER
    record = {**RECORD, "notes": MARKER}
    citations = [*CITATIONS, {"field": "notes", "document": 1, "page": 1, "quote": MARKER}]
    _extractor(monkeypatch, record, citations)
    _generator(
        monkeypatch,
        _requirements({"field_name": "site", "field_type": "str", "description": MARKER}),
    )
    _chat(monkeypatch, "urgent", [("urgent", 1.0)])
    transcriber.raw = f"[Timestamp: 00:00 - 01:00]\n{MARKER}\n[Transcription failed for segment 2]"
    (tmp_path / "note.txt").write_text(private_note, encoding="utf-8")

    with caplog.at_level(logging.DEBUG):
        parse_document(tmp_path / "note.txt")
        extract_fields(private_note, FIELDS, instructions=MARKER, settings=SETTINGS)
        generate_fields(f"Collect the site. {MARKER}", settings=SETTINGS)
        classify_text(private_note, LABELS, instructions=MARKER, settings=SETTINGS)
        transcript = transcribe_audio(
            transcriber.audio, context=MARKER, settings=transcriber.settings
        )

    assert MARKER in transcript.text
    assert MARKER not in caplog.text
    assert "lost 1 part" in caplog.text


def test_importing_the_package_is_silent_and_loads_no_component():
    code = (
        "import sys\n"
        "import gaik.operations\n"
        "loaded = sorted(name for name in sys.modules "
        "if name.startswith('gaik.software_components') or name in ('openai', 'pymupdf'))\n"
        "sys.stderr.write('LOADED=' + ','.join(loaded) + '\\n')\n"
    )

    done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120)

    assert done.returncode == 0
    assert done.stdout == ""
    # The line is looked up, so a warning another package writes to stderr does not fail this.
    assert "LOADED=\n" in done.stderr


def test_a_missing_extra_is_named_in_the_error(monkeypatch, tmp_path):
    import importlib.util

    real_find_spec = importlib.util.find_spec
    monkeypatch.setattr(
        importlib.util,
        "find_spec",
        lambda name, *args: None if name == "pymupdf" else real_find_spec(name, *args),
    )
    path = tmp_path / "note.pdf"
    path.write_bytes(b"%PDF-1.7\n")

    with pytest.raises(ImportError, match=r"parse_document needs PyMuPDF.*gaik\[operations\]"):
        parse_document(path)


def test_the_public_names_are_the_designed_ones():
    assert operations.__all__ == [
        "OperationSettings",
        "FieldDefinition",
        "ParsedDocument",
        "Transcript",
        "ExtractedField",
        "Classification",
        "ExtractionSchema",
        "parse_document",
        "transcribe_audio",
        "generate_fields",
        "extract_fields",
        "classify_text",
        "build_schema",
        "run_async",
        "quiet_stdout",
    ]
    assert operations.__version__ == "0.1.0"
