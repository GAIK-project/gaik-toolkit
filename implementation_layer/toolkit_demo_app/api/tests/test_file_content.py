"""Uploads are checked against the type their name says before they reach a reader."""

import io
import zipfile

import pytest
from api.utils.file_content import content_mismatch
from fastapi.testclient import TestClient


def _zip(*names: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name in names:
            archive.writestr(name, "<x/>")
    return buffer.getvalue()


DOCX = _zip("[Content_Types].xml", "word/document.xml")
XLSX = _zip("[Content_Types].xml", "xl/workbook.xml")

MATCHING = [
    (".pdf", b"%PDF-1.7\n"),
    (".pdf", b"\n" * 10 + b"%PDF-1.4\n"),
    (".png", b"\x89PNG\r\n\x1a\nrest"),
    (".jpg", b"\xff\xd8\xff\xe0rest"),
    (".gif", b"GIF89arest"),
    (".bmp", b"BMrest"),
    (".tif", b"II*\x00rest"),
    (".webp", b"RIFF\x00\x00\x00\x00WEBPVP8 "),
    (".wav", b"RIFF\x00\x00\x00\x00WAVEfmt "),
    (".mp3", b"ID3\x04rest"),
    (".mp3", b"\xff\xfb\x90rest"),
    (".mp3", b"\xff\xe3\x18\xc4rest"),
    (".aac", b"\xff\xf1\x50rest"),
    (".m4a", b"\x00\x00\x00\x20ftypM4A rest"),
    (".mp4", b"\x00\x00\x00\x20ftypisomrest"),
    (".mov", b"\x00\x00\x00\x14ftypqt  rest"),
    (".webm", b"\x1a\x45\xdf\xa3rest"),
    (".ogg", b"OggSrest"),
    (".flac", b"fLaCrest"),
    (".docx", DOCX),
    (".xlsx", XLSX),
    (".xlsm", XLSX),
    (".xls", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1rest"),
    (".parquet", b"PAR1 data PAR1"),
    (".csv", b"a;b\n1;2\n"),
    (".csv", "nimi;määrä\n".encode("cp1252")),
    (".csv", b"MZ;Nimi\n1;2\n"),
    (".tsv", b"a\tb\n"),
    (".txt", b"plain text"),
    (".md", b"# Title\n"),
    (".json", b'{"a": 1}'),
]


@pytest.mark.parametrize(("suffix", "data"), MATCHING)
def test_content_of_the_named_type_is_accepted(suffix, data):
    assert content_mismatch(suffix, data) is None


MISMATCHED = [
    (".pdf", b"<html>not a pdf</html>"),
    (".pdf", DOCX),
    (".png", b"%PDF-1.7\n"),
    (".jpg", b"\x89PNG\r\n\x1a\n"),
    (".docx", XLSX),
    (".docx", b"PK\x03\x04 not a readable archive"),
    (".xlsx", DOCX),
    (".mp3", b"#!/bin/sh\n"),
    (".mp3", b"\xff\xea\x00rest"),
    (".wav", b"RIFF\x00\x00\x00\x00WEBPVP8 "),
    (".csv", b"%PDF-1.7\n"),
    (".csv", b"\n%PDF-1.7\n1 0 obj\n"),
    (".txt", b"a;b\n%PDF-1.4\n"),
    (".csv", DOCX),
    (".txt", b"MZ\x90\x00"),
    (".json", b"{\x00}"),
    (".parquet", b"PAR1 truncated"),
]


@pytest.mark.parametrize(("suffix", "data"), MISMATCHED)
def test_content_of_another_type_is_refused(suffix, data):
    assert content_mismatch(suffix, data) == f"The file's content is not a {suffix} file."


def test_an_empty_file_is_refused():
    assert content_mismatch(".pdf", b"") == "The file is empty."


def test_an_extension_without_a_signature_here_is_refused():
    assert content_mismatch(".exe", b"MZ") == "Files of type .exe cannot be checked."


def test_every_extension_a_route_accepts_has_a_check():
    from api.routers import tabular_agent, vision_extractor

    routes = {".pdf", ".docx", ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".tif", ".webp"}
    audio = {".mp3", ".wav", ".m4a", ".mp4", ".webm", ".ogg", ".flac", ".mov"}
    for suffix in (
        routes
        | audio
        | set(tabular_agent.ALLOWED_EXTENSIONS)
        | set(vision_extractor.SUPPORTED_SUFFIXES)
    ):
        assert content_mismatch(suffix, b"") == "The file is empty.", suffix


def test_a_route_refuses_a_renamed_file_before_any_parser():
    from api import main

    client = TestClient(main.app)
    response = client.post(
        "/parse",
        files={"file": ("report.pdf", DOCX, "application/pdf")},
        data={"parser_type": "pymupdf"},
    )
    assert response.status_code == 415
    assert response.json()["detail"] == "The file's content is not a .pdf file."
