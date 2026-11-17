"""The parsers read a file's type from its content and refuse one whose extension does not match."""

from __future__ import annotations

import io
import zipfile
from types import SimpleNamespace

import pytest
from gaik.software_components.file_type import (
    FileTypeMismatchError,
    check_file_type,
    detect_file_type,
)

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 32
GIF = b"GIF89a" + b"\x00" * 32
WEBP = b"RIFF\x24\x00\x00\x00WEBPVP8 " + b"\x00" * 32
TIFF = b"II*\x00" + b"\x00" * 32
BMP = b"BM\x36\x00\x00\x00\x00\x00\x00\x00" + b"\x00" * 32
OLE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 32
PDF = b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n1 0 obj\n<<>>\nendobj\n"


def _zip(members: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, text in members.items():
            archive.writestr(name, text)
    return buffer.getvalue()


DOCX = _zip({"[Content_Types].xml": "<Types/>", "word/document.xml": "<w:document/>"})
XLSX = _zip({"[Content_Types].xml": "<Types/>", "xl/workbook.xml": "<workbook/>"})
PPTX = _zip({"[Content_Types].xml": "<Types/>", "ppt/presentation.xml": "<p/>"})
ZIP = _zip({"readme.txt": "hello"})


def _file(tmp_path, name, data):
    path = tmp_path / name
    path.write_bytes(data)
    return path


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        (PDF, "pdf"),
        (b"\n\n  " + PDF, "pdf"),
        (DOCX, "docx"),
        (XLSX, "xlsx"),
        (PPTX, "pptx"),
        (ZIP, "zip"),
        (b"junk" * 10 + DOCX, "docx"),
        (OLE, "ole"),
        (PNG, "png"),
        (JPEG, "jpeg"),
        (GIF, "gif"),
        (WEBP, "webp"),
        (TIFF, "tiff"),
        (BMP, "bmp"),
        (b"name,amount\nBMW,3\n", "text"),
        (b"BMW sales were up\n", "text"),
        ("Päivämäärä;Summa\n".encode(), "text"),
        (b"\xff\xfeh\x00i\x00", "text"),
        (b"", "empty"),
        (b"\x01\x02\x00\x03binary", "unknown"),
    ],
)
def test_detect_file_type_reads_the_type_from_the_content(tmp_path, data, expected):
    assert detect_file_type(_file(tmp_path, "file.bin", data)) == expected


@pytest.mark.parametrize(
    ("name", "data"),
    [
        ("report.pdf", PDF),
        ("notes.docx", DOCX),
        ("legacy.doc", OLE),
        ("legacy-but-new.doc", DOCX),
        ("budget.xlsx", XLSX),
        ("slides.pptx", PPTX),
        ("scan.png", PNG),
        ("photo.jpg", JPEG),
        ("photo.jpeg", JPEG),
        ("scan.tif", TIFF),
        ("log.csv", b"a,b\n1,2\n"),
        ("readme.md", b"# Title\n"),
        ("unknown.xyz", b"\x01\x00"),
    ],
)
def test_a_file_whose_content_matches_its_extension_is_accepted(tmp_path, name, data):
    check_file_type(_file(tmp_path, name, data))


@pytest.mark.parametrize(
    ("name", "data", "detected"),
    [
        ("report.pdf", DOCX, "docx"),
        ("report.pdf", PNG, "png"),
        ("notes.docx", PDF, "pdf"),
        ("notes.docx", XLSX, "xlsx"),
        ("notes.docx", b"plain words", "text"),
        ("budget.xlsx", ZIP, "zip"),
        ("scan.png", JPEG, "jpeg"),
        ("scan.png", PDF, "pdf"),
        ("photo.jpg", b"not an image", "text"),
        ("log.csv", ZIP, "zip"),
        ("log.csv", b"\x01\x00\x02", "unknown"),
        ("readme.txt", PDF, "pdf"),
    ],
)
def test_a_file_whose_content_differs_from_its_extension_is_refused(tmp_path, name, data, detected):
    path = _file(tmp_path, name, data)
    with pytest.raises(FileTypeMismatchError) as caught:
        check_file_type(path)
    error = caught.value
    assert isinstance(error, ValueError)
    assert error.file_name == name
    assert error.extension == path.suffix
    assert error.detected == detected
    message = str(error)
    assert f"'{name}'" in message and path.suffix in message
    assert str(tmp_path) not in message


def test_content_of_another_type_than_the_caller_reads_is_refused_without_an_extension(
    tmp_path,
):
    path = _file(tmp_path, "upload", DOCX)
    with pytest.raises(FileTypeMismatchError, match="is a DOCX document, not a PDF document"):
        check_file_type(path, {"pdf"})


def test_unrecognised_content_named_pdf_is_left_to_the_pdf_parser(tmp_path):
    # PyMuPDF repairs a PDF without its header line; the parser reports what it cannot read.
    assert check_file_type(_file(tmp_path, "scan.pdf", b"1 0 obj\n<<>>\n"), {"pdf"}) == "text"


# -- the parsers ----------------------------------------------------------------


def test_pymupdf_parser_refuses_an_image_named_pdf(tmp_path):
    pytest.importorskip("fitz")
    from gaik.software_components.parsers.pymypdf import PyMuPDFParser

    path = _file(tmp_path, "invoice.pdf", PNG)
    with pytest.raises(FileTypeMismatchError, match=r"'invoice\.pdf' is a PNG image"):
        PyMuPDFParser().parse_pdf(str(path))


def test_pymupdf_parser_refuses_a_pdf_named_as_another_type(tmp_path):
    fitz = pytest.importorskip("fitz")
    from gaik.software_components.parsers.pymypdf import PyMuPDFParser

    document = fitz.open()
    document.new_page().insert_text((72, 72), "Invoice 42")
    path = tmp_path / "invoice.png"
    document.save(path)
    document.close()
    with pytest.raises(FileTypeMismatchError, match=r"as its extension \.png says"):
        PyMuPDFParser().parse_pdf(str(path))


def test_docx_parser_refuses_a_workbook_named_docx(tmp_path):
    pytest.importorskip("docx")
    from gaik.software_components.parsers.docx_parser import DocxParser

    path = _file(tmp_path, "notes.docx", XLSX)
    with pytest.raises(FileTypeMismatchError, match="is an XLSX workbook, not a DOCX document"):
        DocxParser().parse_docx(str(path))


def test_spreadsheet_parser_refuses_a_document_named_xlsx_or_csv(tmp_path):
    from gaik.software_components.parsers.spreadsheet_parser import SpreadsheetParser

    for name, data in [("budget.xlsx", DOCX), ("log.csv", PDF)]:
        path = _file(tmp_path, name, data)
        with pytest.raises(FileTypeMismatchError, match=name.replace(".", r"\.")):
            SpreadsheetParser().parse_spreadsheet(path)


def test_docling_api_client_refuses_a_mismatched_file_before_any_request(tmp_path, monkeypatch):
    from gaik.software_components.parsers import docling_api_client

    calls = []
    monkeypatch.setattr(docling_api_client._http, "get", lambda *args, **kwargs: calls.append(args))
    monkeypatch.setattr(
        docling_api_client._http, "post", lambda *args, **kwargs: calls.append(args)
    )
    client = docling_api_client.DoclingApiClientParser(
        api_base="https://docling.example",
        password="test",
        allowed_endpoint_hosts="docling.example",
    )
    with pytest.raises(FileTypeMismatchError):
        client.parse_document(_file(tmp_path, "report.pdf", DOCX))
    assert calls == []


def _vision_parser(monkeypatch):
    from gaik.software_components.parsers.vision import VisionParser

    sent = []
    monkeypatch.setattr(VisionParser, "_initialize_client", lambda self: SimpleNamespace())
    monkeypatch.setattr(
        VisionParser,
        "_parse_image",
        lambda self, image, **kwargs: sent.append(kwargs.get("mime_type")) or "markdown",
    )
    return VisionParser({"provider": "openai", "model": "vision", "api_key": "test"}), sent


def test_vision_parser_refuses_mismatched_files_before_any_model_call(tmp_path, monkeypatch):
    pytest.importorskip("fitz")
    parser, sent = _vision_parser(monkeypatch)
    with pytest.raises(FileTypeMismatchError):
        parser.convert_image(_file(tmp_path, "scan.png", PDF))
    with pytest.raises(FileTypeMismatchError):
        parser.convert_image(_file(tmp_path, "upload", b"plain words"))
    with pytest.raises(FileTypeMismatchError):
        parser.convert_pdf(_file(tmp_path, "scan.pdf", JPEG))
    assert sent == []


def test_vision_parser_sends_an_image_without_a_suffix_with_its_content_type(tmp_path, monkeypatch):
    parser, sent = _vision_parser(monkeypatch)
    assert parser.convert_image(_file(tmp_path, "upload", JPEG)) == "markdown"
    assert sent == ["image/jpeg"]


def test_chat_content_refuses_an_image_whose_content_differs_from_its_extension(tmp_path):
    from gaik.software_components.parsers.multimodal_parser.chat_content import (
        build_chat_document_content,
    )

    with pytest.raises(FileTypeMismatchError, match="is a GIF image, not a PNG image"):
        build_chat_document_content([_file(tmp_path, "scan.png", GIF)], "Read this")
