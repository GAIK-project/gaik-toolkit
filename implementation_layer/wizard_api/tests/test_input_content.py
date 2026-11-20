"""What an uploaded case or PoC input is, decided from its content.

Every fixture is generated here: a few bytes of each format's own signature,
or a small ZIP built in memory. No real documents.
"""

from __future__ import annotations

import io
import json
import os
import struct
import uuid
import wave
import zipfile

import pytest
from helpers import requires_postgres
from test_cases import _session_with_package
from wizard_api.services import case_service, input_content, poc_service, session_service
from wizard_api.services.input_content import (
    ALL_KINDS,
    InvalidInputError,
    UnsupportedInputError,
    allowed_kinds,
    check,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _wav() -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(b"\x00\x00" * 80)
    return buf.getvalue()


def _png() -> bytes:
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + struct.pack(">I", len(ihdr)) + b"IHDR" + ihdr + b"\x00" * 4


def _zip(entries: dict[str, bytes], compression: int = zipfile.ZIP_DEFLATED) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression) as z:
        for name, data in entries.items():
            z.writestr(zipfile.ZipInfo(name), data, compress_type=compression)
    return buf.getvalue()


_CONTENT_TYPES = b'<?xml version="1.0"?><Types/>'


def _docx(extra: dict[str, bytes] | None = None) -> bytes:
    return _zip(
        {
            "[Content_Types].xml": _CONTENT_TYPES,
            "word/document.xml": b"<w:document/>",
            **(extra or {}),
        }
    )


def _xlsx() -> bytes:
    return _zip({"[Content_Types].xml": _CONTENT_TYPES, "xl/workbook.xml": b"<workbook/>"})


SAMPLES: dict[str, tuple[str, bytes]] = {
    "pdf": ("report.pdf", b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\n%%EOF\n"),
    "png": ("photo.png", _png()),
    "jpeg": ("photo.jpg", b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01" + b"\x00" * 8 + b"\xff\xd9"),
    "gif": ("photo.gif", b"GIF89a\x01\x00\x01\x00\x00\x00\x00;"),
    "webp": ("photo.webp", b"RIFF\x0c\x00\x00\x00WEBPVP8 " + b"\x00" * 4),
    "tiff": ("scan.tiff", b"II*\x00\x08\x00\x00\x00" + b"\x00" * 8),
    "wav": ("call.wav", _wav()),
    "mp3": ("call.mp3", b"ID3\x04\x00\x00\x00\x00\x00\x00" + b"\xff\xfb\x90\x00" + b"\x00" * 16),
    "m4a": ("call.m4a", b"\x00\x00\x00\x18ftypM4A \x00\x00\x00\x00M4A isom" + b"\x00" * 8),
    "txt": ("notes.txt", "Meeting notes: Kärkkäinen agreed.\n".encode()),
    "md": ("notes.md", b"# Notes\n\n- one\n- two\n"),
    "csv": ("rows.csv", b"name,amount\nalpha,1\nbeta,2\n"),
    "json": ("record.json", json.dumps({"id": 1, "name": "alpha"}).encode()),
    "docx": ("letter.docx", _docx()),
    "xlsx": ("sheet.xlsx", _xlsx()),
}


# ---------------------------------------------------------------------------
# The check itself
# ---------------------------------------------------------------------------


def test_every_supported_kind_has_a_sample():
    assert set(SAMPLES) == set(ALL_KINDS)


@pytest.mark.parametrize("kind", sorted(SAMPLES))
def test_a_file_of_each_accepted_type_is_accepted(kind):
    name, data = SAMPLES[kind]
    assert check(name, data) == kind


def test_a_bare_mpeg_frame_is_an_mp3():
    assert check("call.mp3", b"\xff\xfb\x90\x00" + b"\x00" * 32) == "mp3"


def test_a_text_file_with_a_utf8_byte_order_mark_is_accepted():
    assert check("notes.txt", b"\xef\xbb\xbfhello\n") == "txt"


@pytest.mark.parametrize(
    "name, content_of",
    [
        ("report.pdf", "png"),  # a picture named as a PDF
        ("photo.png", "pdf"),
        ("photo.jpg", "png"),
        ("call.wav", "mp3"),
        ("call.mp3", "wav"),
        ("call.m4a", "pdf"),
        ("letter.docx", "pdf"),
        ("letter.docx", "xlsx"),  # one office format named as the other
        ("sheet.xlsx", "docx"),
        ("notes.txt", "pdf"),  # a binary format named as text
        ("rows.csv", "png"),
        ("record.json", "docx"),
        ("notes.md", "wav"),
    ],
)
def test_a_renamed_file_whose_content_does_not_match_is_refused(name, content_of):
    _, data = SAMPLES[content_of]
    with pytest.raises(UnsupportedInputError, match="does not match its"):
        check(name, data)


def test_a_plain_archive_named_as_an_office_document_is_refused():
    data = _zip({"readme.txt": b"hello"})
    with pytest.raises(UnsupportedInputError, match="does not match its .docx extension"):
        check("letter.docx", data)


@pytest.mark.parametrize("name", ["bundle.zip", "page.html", "image.svg", "run.py", "noext"])
def test_a_type_outside_the_supported_set_is_refused_whatever_its_content(name):
    with pytest.raises(UnsupportedInputError, match="not accepted here; accepted types: PDF"):
        check(name, SAMPLES["txt"][1])


def test_an_archive_that_unpacks_past_the_bound_is_refused(monkeypatch):
    monkeypatch.setattr(input_content, "MAX_ARCHIVE_UNCOMPRESSED_BYTES", 64 * 1024)
    data = _docx({"word/media/blank.bin": b"\x00" * (128 * 1024)})
    assert len(data) < 16 * 1024  # small upload, large once unpacked

    with pytest.raises(InvalidInputError, match="unpacks to more than"):
        check("letter.docx", data)


def test_an_archive_whose_headers_understate_its_size_is_measured_not_trusted(monkeypatch):
    monkeypatch.setattr(input_content, "MAX_ARCHIVE_UNCOMPRESSED_BYTES", 64 * 1024)
    data = bytearray(_docx({"word/media/blank.bin": b"\x00" * (128 * 1024)}))
    # Rewrite the declared size of the large entry, in the local header and the
    # central directory, to something under the bound.
    real = struct.pack("<I", 128 * 1024)
    assert data.count(real) == 2
    data = bytes(data).replace(real, struct.pack("<I", 1024))

    with pytest.raises(InvalidInputError):
        check("letter.docx", data)


def test_an_archive_with_too_many_entries_is_refused(monkeypatch):
    monkeypatch.setattr(input_content, "MAX_ARCHIVE_ENTRIES", 10)
    data = _docx({f"word/part{i}.xml": b"<x/>" for i in range(20)})

    with pytest.raises(InvalidInputError, match="more than 10 entries"):
        check("letter.docx", data)


@pytest.mark.parametrize("entry", ["../outside.xml", "word/../../outside.xml", "/abs/entry.xml"])
def test_an_archive_with_an_entry_outside_its_folder_is_refused(entry):
    data = _docx({entry: b"<x/>"})
    with pytest.raises(InvalidInputError, match="outside its own folder"):
        check("letter.docx", data)


def test_a_damaged_archive_is_refused():
    data = b"PK\x03\x04" + b"\x00" * 64
    with pytest.raises(InvalidInputError, match="not a readable archive"):
        check("letter.docx", data)


@pytest.mark.parametrize(
    "name, data, message",
    [
        ("notes.txt", b"caf\xe9 au lait\n", "must be UTF-8 text"),  # Latin-1, not UTF-8
        ("rows.csv", b"a,b\n\xff\xfe\n", "must be UTF-8 text"),
        ("notes.md", b"# title\x00\x00\n", "must be UTF-8 text"),
        ("record.json", b'{"id": 1,', "not valid JSON"),
    ],
)
def test_text_that_is_not_valid_is_refused(name, data, message):
    with pytest.raises(InvalidInputError, match=message):
        check(name, data)


def test_an_empty_file_is_refused():
    with pytest.raises(poc_service.InputRejectedError, match="empty"):
        check("notes.txt", b"")


def test_a_name_that_leaves_the_input_directory_is_refused_as_that():
    with pytest.raises(poc_service.InputRejectedError, match="leave the input directory"):
        check("../notes.txt", b"hello")


# ---------------------------------------------------------------------------
# The session's input contract
# ---------------------------------------------------------------------------


def test_without_a_contract_every_supported_type_is_allowed():
    assert allowed_kinds(None) == ALL_KINDS
    assert allowed_kinds({"use_case": {"name": "x"}}) == ALL_KINDS
    assert allowed_kinds({"technical_spec": {"input_types": ["telepathy"]}}) == ALL_KINDS


def test_the_contract_is_the_uploaded_artifacts_and_the_technical_input_types():
    draft = {
        "artifacts": {
            "recording": {"type": "audio", "source": "user_upload", "optional": False},
            "ticket": {"type": "json", "source": "generated", "produced_by": "x"},
        },
        "technical_spec": {"input_types": ["pdf"], "input_formats": ["CSV"]},
    }
    assert allowed_kinds(draft) == {"wav", "mp3", "m4a", "pdf", "csv", "json"}


def test_a_contract_word_is_matched_on_its_parts():
    assert allowed_kinds({"technical_spec": {"input_types": ["scanned_pdf"]}}) == {"pdf", "json"}


def test_a_settings_json_is_accepted_whatever_the_contract_names():
    """A report spec or input bundle sits next to the inputs a blueprint names."""
    allowed = allowed_kinds(
        {"artifacts": {"sources": {"type": "document", "source": "user_upload"}}}
    )
    check("report_spec.json", b'{"sections": ["summary"]}', allowed)


def test_a_type_the_contract_does_not_ask_for_is_refused_and_the_allowed_ones_named():
    allowed = allowed_kinds({"technical_spec": {"input_types": ["audio"]}})
    name, data = SAMPLES["pdf"]
    with pytest.raises(UnsupportedInputError) as exc:
        check(name, data, allowed)
    assert (
        str(exc.value) == "this file type is not accepted here; accepted types: WAV, MP3, M4A, JSON"
    )


# ---------------------------------------------------------------------------
# Through the API
# ---------------------------------------------------------------------------


def _set_contract(out: str, input_types: list[str]) -> None:
    path = os.path.join(out, "use_case.blueprint.json")
    with open(path, encoding="utf-8") as fh:
        draft = json.load(fh)
    draft.setdefault("technical_spec", {})["input_types"] = input_types
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(draft, fh)


def _case_upload(client, db_session, input_types: list[str]):
    sid = _session_with_package(client, db_session)
    out = session_service.get_session(db_session, uuid.UUID(sid)).output_dir
    _set_contract(out, input_types)
    case = client.post(f"/sessions/{sid}/cases").json()
    url = f"/sessions/{sid}/cases/{case['id']}/inputs"
    return url, case_service.inputs_dir(out, case["id"])


@requires_postgres
@pytest.mark.parametrize("kind", ["wav", "pdf", "docx", "csv"])
def test_a_case_input_of_an_allowed_type_is_stored(client, db_session, kind):
    url, folder = _case_upload(client, db_session, ["audio", "document", "csv"])
    name, data = SAMPLES[kind]

    res = client.post(url, files={"file": (name, data, "application/octet-stream")})

    assert res.status_code == 201, res.text
    assert (folder / name).read_bytes() == data


@requires_postgres
def test_a_renamed_case_input_is_refused_with_415_and_not_written(client, db_session):
    url, folder = _case_upload(client, db_session, ["audio"])
    # Declared as a recording in both the name and the header; it is a PDF.
    res = client.post(url, files={"file": ("call.wav", SAMPLES["pdf"][1], "audio/wav")})

    assert res.status_code == 415
    detail = res.json()["detail"]
    assert detail["error"] == "input_type_not_accepted"
    assert detail["message"] == (
        "the file's content does not match its .wav extension; accepted types: WAV, MP3, M4A, JSON"
    )
    assert not (folder / "call.wav").exists()


@requires_postgres
def test_a_case_input_outside_the_contract_is_refused_with_415(client, db_session):
    url, folder = _case_upload(client, db_session, ["audio"])
    name, data = SAMPLES["pdf"]

    res = client.post(url, files={"file": (name, data, "application/pdf")})

    assert res.status_code == 415
    assert "accepted types: WAV, MP3, M4A, JSON" in res.json()["detail"]["message"]
    assert not folder.exists() or not any(folder.iterdir())


@requires_postgres
def test_an_oversized_or_escaping_archive_case_input_is_refused_with_422(
    client, db_session, monkeypatch
):
    monkeypatch.setattr(input_content, "MAX_ARCHIVE_UNCOMPRESSED_BYTES", 64 * 1024)
    url, folder = _case_upload(client, db_session, ["docx"])

    big = client.post(
        url, files={"file": ("big.docx", _docx({"word/b.bin": b"\x00" * (128 * 1024)}))}
    )
    escaping = client.post(url, files={"file": ("up.docx", _docx({"../up.xml": b"<x/>"}))})

    assert big.status_code == 422 and "unpacks to more than" in big.json()["detail"]["message"]
    assert (
        escaping.status_code == 422
        and "outside its own folder" in escaping.json()["detail"]["message"]
    )
    assert not folder.exists() or not any(folder.iterdir())


@requires_postgres
def test_invalid_text_case_input_is_refused_with_422(client, db_session):
    url, folder = _case_upload(client, db_session, ["text"])

    res = client.post(url, files={"file": ("notes.txt", b"caf\xe9\n", "text/plain")})

    assert res.status_code == 422
    assert res.json()["detail"]["message"] == "a TXT file must be UTF-8 text"
    assert not (folder / "notes.txt").exists()


def _poc_session(client, db_session, input_types: list[str]):
    sid = _session_with_package(client, db_session)
    out = session_service.get_session(db_session, uuid.UUID(sid)).output_dir
    _set_contract(out, input_types)
    return f"/sessions/{sid}/poc/input", os.path.join(out, "poc", "sample_input")


@requires_postgres
def test_a_poc_sample_input_gets_the_same_check(client, db_session):
    # The package fixture's draft also expects an audio upload.
    url, folder = _poc_session(client, db_session, ["pdf"])

    ok = client.post(url, files={"file": SAMPLES["pdf"]})
    renamed = client.post(url, files={"file": ("scan.pdf", SAMPLES["png"][1], "application/pdf")})
    outside = client.post(url, files={"file": SAMPLES["csv"]})
    bad_archive = client.post(url, files={"file": ("x.pdf", _docx({"../x": b"x"}))})

    assert ok.status_code == 201, ok.text
    assert (
        renamed.status_code == 415 and "accepted types: PDF" in renamed.json()["detail"]["message"]
    )
    assert outside.status_code == 415
    # A ZIP named as a PDF is a mismatch; it is not opened at all.
    assert bad_archive.status_code == 415
    # The package's example, the accepted upload, and the record of what was uploaded.
    assert sorted(os.listdir(folder)) == sorted(
        [poc_service.UPLOADED_NAMES_FILE, "developer.wav", SAMPLES["pdf"][0]]
    )
    assert poc_service.uploaded_sample_inputs(os.path.dirname(folder)) == [SAMPLES["pdf"][0]]


def test_the_accepted_types_are_listed_with_their_extensions():
    # What the upload form shows before a file is picked: the audio the
    # contract names, and JSON, which is always accepted.
    kinds = input_content.allowed_kinds({"technical_spec": {"input_types": ["audio"]}})

    listed = input_content.accepted(kinds)

    assert [item["label"] for item in listed] == ["WAV", "MP3", "M4A", "JSON"]
    assert listed[0] == {"kind": "wav", "label": "WAV", "extensions": [".wav"]}
    # The same labels, in the same order, as the refusal's own words.
    assert ", ".join(item["label"] for item in listed) == input_content.describe(kinds)


def test_contract_kinds_excludes_implicit_json_fallback_for_explicit_audio_contract():
    kinds = input_content.contract_kinds({"technical_spec": {"input_types": ["audio"]}})

    assert kinds == frozenset({"wav", "mp3", "m4a"})
    assert input_content.contract_kinds({}) == ALL_KINDS
