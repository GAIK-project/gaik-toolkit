"""The parsers read a file's type from its content and refuse one whose extension does not match."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path
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
        (b"II+\x00\x08\x00\x00\x00" + b"\x00" * 32, "tiff"),
        (b"MM\x00+\x00\x08\x00\x00" + b"\x00" * 32, "tiff"),
        (BMP, "bmp"),
        ("name;summa\nPäivä;3\n".encode("utf-16-le"), "text"),
        ("name;summa\nPäivä;3\n".encode("utf-16-be"), "text"),
        (b"words\x00and a NUL", "unknown"),
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
        # An image saved under another image extension: its content decides.
        ("scan.png", JPEG),
        ("photo.jpg", PNG),
        ("photo.jpg", WEBP),
        ("scan.tif", TIFF),
        ("scan.tiff", b"II+\x00\x08\x00\x00\x00" + b"\x00" * 32),
        ("export.csv", "a;b\n1;2\n".encode("utf-16-le")),
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

    with pytest.raises(FileTypeMismatchError, match="is a PDF document, not an image"):
        build_chat_document_content([_file(tmp_path, "scan.png", PDF)], "Read this")


# -- a bounded read before the limits ------------------------------------------


def _many_entries(path: Path, count: int) -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("word/document.xml", "<w:document/>")
        for number in range(count):
            archive.writestr(f"media/part{number:05}.bin", b"")
    return path


def _refuse_zipfile(monkeypatch):
    opened = []

    class Recorder(zipfile.ZipFile):
        def __init__(self, *args, **kwargs):
            opened.append(args[0] if args else kwargs.get("file"))
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(zipfile, "ZipFile", Recorder)
    return opened


def test_a_docx_over_the_size_limit_is_refused_before_its_directory_is_read(tmp_path, monkeypatch):
    pytest.importorskip("docx")
    from gaik.software_components.input_limits import InputLimitError, InputLimits
    from gaik.software_components.parsers.docx_parser import DocxParser

    path = _many_entries(tmp_path / "notes.docx", 3000)
    opened = _refuse_zipfile(monkeypatch)
    parser = DocxParser(limits=InputLimits(max_file_bytes=1024))
    with pytest.raises(InputLimitError, match="max_file_bytes"):
        parser.parse_docx(str(path))
    assert opened == []


def test_an_archive_with_a_directory_over_the_cap_is_typed_from_its_first_entries(
    tmp_path, monkeypatch
):
    from gaik.software_components import file_type

    path = _many_entries(tmp_path / "notes.docx", 200)
    monkeypatch.setattr(file_type, "_MAX_ZIP_DIRECTORY_BYTES", 1024)
    opened = _refuse_zipfile(monkeypatch)
    assert file_type.detect_file_type(path) == "docx"
    assert opened == []

    monkeypatch.setattr(file_type, "_MAX_ZIP_DIRECTORY_BYTES", 2 * 1024 * 1024)
    monkeypatch.setattr(file_type, "_MAX_ZIP_ENTRIES", 100)
    assert file_type.detect_file_type(path) == "docx"
    assert opened == []
    assert file_type.detect_file_type(_file(tmp_path, "other.zip", ZIP)) == "zip"
    assert len(opened) == 1


def test_a_zip64_archive_is_read_from_its_zip64_end_record(tmp_path):
    from gaik.software_components import file_type

    path = tmp_path / "notes.docx"
    with zipfile.ZipFile(path, "w", allowZip64=True) as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("word/document.xml", "<w:document/>")
    data = path.read_bytes()
    # The end record of a small archive, rewritten as a ZIP64 one would leave it.
    at = data.rfind(b"PK\x05\x06")
    fields = list(file_type._END_RECORD.unpack_from(data, at))
    entries, directory, offset = fields[4], fields[5], fields[6]
    fields[3:7] = [0xFFFF, 0xFFFF, 0xFFFFFFFF, 0xFFFFFFFF]
    record_64 = file_type._END_RECORD_64.pack(
        b"PK\x06\x06", 44, 45, 45, 0, 0, entries, entries, directory, offset
    )
    locator = file_type._END_RECORD_64_LOCATOR.pack(b"PK\x06\x07", 0, at, 1)
    path.write_bytes(data[:at] + record_64 + locator + file_type._END_RECORD.pack(*fields))
    assert file_type._zip_directory_size(path) == (entries, directory)
    assert file_type.detect_file_type(path) == "docx"


@pytest.mark.parametrize(
    ("call", "name"),
    [
        ("chat_pdf", "scan.pdf"),
        ("chat_image", "scan.png"),
        ("vision_image", "scan.png"),
    ],
)
def test_the_image_and_pdf_paths_check_the_size_before_the_content(
    tmp_path, monkeypatch, call, name
):
    from gaik.software_components.input_limits import InputLimitError, InputLimits

    path = _many_entries(tmp_path / name, 50)
    opened = _refuse_zipfile(monkeypatch)
    limits = InputLimits(max_file_bytes=1024)
    with pytest.raises(InputLimitError, match="max_file_bytes"):
        if call == "vision_image":
            parser, _sent = _vision_parser(monkeypatch)
            parser.limits = limits
            parser.convert_image(path)
        else:
            if call == "chat_pdf":
                pytest.importorskip("fitz")
            from gaik.software_components.parsers.multimodal_parser.chat_content import (
                build_chat_document_content,
            )

            build_chat_document_content([path], "Read this", limits=limits)
    assert opened == []


# -- the parsers that need Docling or a model ------------------------------------


class _Converter:
    def __init__(self):
        self.calls = []

    def convert(self, *args, **kwargs):
        self.calls.append(args)
        raise AssertionError("the converter ran")


def _docling_parser(limits=None):
    pytest.importorskip("docling")
    pytest.importorskip("psutil")
    from gaik.software_components.input_limits import InputLimits
    from gaik.software_components.parsers.docling import DoclingParser

    parser = object.__new__(DoclingParser)
    parser.limits = limits or InputLimits.local_parsing()
    parser.docling_available = True
    parser.supported_extensions = [".pdf", ".docx"]
    parser.converter = _Converter()
    return parser


def _vision_plus_parser(limits=None):
    pytest.importorskip("docling")
    from gaik.software_components.input_limits import InputLimits
    from gaik.software_components.parsers.visionPlus import VisionPlusParser

    parser = object.__new__(VisionPlusParser)
    parser.limits = limits or InputLimits.local_parsing()
    parser.verbose = False
    parser.converter = _Converter()
    return parser


def _multimodal_parser(limits=None):
    pytest.importorskip("markdown_it")
    from gaik.software_components.input_limits import InputLimits
    from gaik.software_components.parsers.multimodal_parser.multimodal_parser import (
        MultimodalParser,
    )

    parser = object.__new__(MultimodalParser)
    parser.limits = limits or InputLimits()
    parser._shared_config = True
    parser._call_shared = lambda *args: (_ for _ in ()).throw(AssertionError("model call"))
    return parser


def _parse(kind, parser, path):
    if kind == "multimodal":
        return parser.parse(path)
    return parser.parse_document(str(path))


_BUILDERS = {
    "docling": _docling_parser,
    "vision_plus": _vision_plus_parser,
    "multimodal": _multimodal_parser,
}


@pytest.mark.parametrize("kind", sorted(_BUILDERS))
def test_docling_vision_plus_and_multimodal_parsers_refuse_an_image_named_pdf(tmp_path, kind):
    parser = _BUILDERS[kind]()
    path = _file(tmp_path, "report.pdf", PNG)
    with pytest.raises(FileTypeMismatchError, match=r"'report\.pdf' is a PNG image"):
        _parse(kind, parser, path)
    if kind != "multimodal":
        assert parser.converter.calls == []


@pytest.mark.parametrize("kind", sorted(_BUILDERS))
def test_docling_vision_plus_and_multimodal_parsers_check_the_size_first(
    tmp_path, monkeypatch, kind
):
    from gaik.software_components.input_limits import InputLimitError, InputLimits

    parser = _BUILDERS[kind](InputLimits(max_file_bytes=1024))
    path = _many_entries(tmp_path / "report.pdf", 50)
    opened = _refuse_zipfile(monkeypatch)
    with pytest.raises(InputLimitError, match="max_file_bytes"):
        _parse(kind, parser, path)
    assert opened == []


# -- markup named .pdf, images under another image extension -------------------

SVG = b'<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"><text y="5">hi</text></svg>'
HTML = b"<html><body><p>Hello</p></body></html>"


@pytest.mark.parametrize("data", [SVG, HTML], ids=["svg", "html"])
def test_markup_named_pdf_is_refused_as_no_pdf(tmp_path, data):
    pytest.importorskip("pymupdf")
    with pytest.raises(FileTypeMismatchError, match=r"'x\.pdf' is plain text, not a PDF"):
        check_file_type(_file(tmp_path, "x.pdf", data), {"pdf"})
    with pytest.raises(FileTypeMismatchError):
        check_file_type(_file(tmp_path, "x.pdf", data))


@pytest.mark.parametrize("data", [SVG, HTML], ids=["svg", "html"])
def test_markup_named_pdf_reaches_no_model_and_no_upload(tmp_path, monkeypatch, data):
    pytest.importorskip("pymupdf")
    from gaik.software_components.parsers import docling_api_client
    from gaik.software_components.parsers.multimodal_parser.chat_content import (
        build_chat_document_content,
    )

    path = _file(tmp_path, "x.pdf", data)
    with pytest.raises(FileTypeMismatchError):
        build_chat_document_content([path], "Read this")

    parser, sent = _vision_parser(monkeypatch)
    with pytest.raises(FileTypeMismatchError):
        parser.convert_pdf(path)
    assert sent == []

    with pytest.raises(FileTypeMismatchError):
        _multimodal_parser().parse(path)

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
        client.parse_document(path)
    assert calls == []


def test_vision_parser_reads_no_pdf_that_pymupdf_opens_as_another_format(tmp_path, monkeypatch):
    pytest.importorskip("fitz")
    parser, _sent = _vision_parser(monkeypatch)
    with pytest.raises(ValueError, match="is not a PDF document"):
        parser._pdf_to_images(_file(tmp_path, "x.pdf", SVG), dpi=72)


@pytest.mark.parametrize(
    ("data", "mime"), [(PNG, "image/png"), (WEBP, "image/webp")], ids=["png", "webp"]
)
def test_an_image_saved_as_jpg_is_sent_with_its_content_type(tmp_path, monkeypatch, data, mime):
    from gaik.software_components.parsers.multimodal_parser.chat_content import (
        build_chat_document_content,
    )

    # The pixel check needs a decodable image; these are headers only.
    monkeypatch.setattr(
        "gaik.software_components.input_limits.InputLimits.check_image_file",
        lambda self, path: None,
    )
    path = _file(tmp_path, "photo.jpg", data)
    parser, sent = _vision_parser(monkeypatch)
    assert parser.convert_image(path) == "markdown"
    assert sent == [mime]

    content = build_chat_document_content([path], "Read this")
    assert any(
        part.get("type") == "image_url" and part["image_url"]["url"].startswith(f"data:{mime};")
        for part in content
        if isinstance(part, dict)
    )


def test_a_damaged_content_types_part_leaves_the_member_names_to_decide(tmp_path):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<Types>" + "x" * 2000 + "</Types>")
        archive.writestr("word/document.xml", "<w:document/>")
    data = bytearray(buffer.getvalue())
    # Damage the deflate stream of the first member, keeping the archive's directory.
    start = 30 + len("[Content_Types].xml")
    data[start : start + 8] = b"\xff" * 8
    assert detect_file_type(_file(tmp_path, "notes.docx", bytes(data))) == "docx"


def test_an_office_file_with_a_utf16_manifest_and_a_renamed_main_part_is_read(tmp_path):
    manifest = (
        '<?xml version="1.0" encoding="UTF-16"?><Types><Override PartName="/word/main.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.'
        'wordprocessingml.document.main+xml"/></Types>'
    )
    for encoded in (manifest.encode("utf-16"), manifest.encode("utf-16-le")):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("[Content_Types].xml", encoded)
            archive.writestr("word/main.xml", "<w:document/>")
        data = buffer.getvalue()
        assert detect_file_type(_file(tmp_path, "notes.docx", data)) == "docx"


def test_utf16_text_with_a_surrogate_pair_at_the_end_of_the_sample_is_text(tmp_path):
    # The pair's four bytes start at byte 8188, so the 8 KiB sample ends inside it.
    text = "a" * 4094 + "\U0001f601" + "b" * 100
    data = text.encode("utf-16-le")
    assert data[8188:8192] == "\U0001f601".encode("utf-16-le")
    assert detect_file_type(_file(tmp_path, "notes.txt", data)) == "text"


# -- the RAG parsers -----------------------------------------------------------


def _docling_rag_parser(limits=None):
    pytest.importorskip("docling")
    from gaik.software_components.input_limits import InputLimits
    from gaik.software_components.RAG.rag_parser_docling.parser import DoclingRagParser

    parser = object.__new__(DoclingRagParser)
    parser.limits = limits or InputLimits.local_parsing()
    parser.converter = _Converter()
    return parser


def _vision_rag_parser(limits=None):
    pytest.importorskip("docling")
    from gaik.software_components.input_limits import InputLimits
    from gaik.software_components.RAG.rag_parser_vision.parser import VisionRagParser

    parser = object.__new__(VisionRagParser)
    parser.limits = limits or InputLimits.local_parsing()
    parser.verbose = False
    parser.converter = _Converter()
    return parser


def _text_rag_parser(limits=None):
    pytest.importorskip("langchain_core")
    from gaik.software_modules.RAG_workflow.text_parser import TextRagParser

    return TextRagParser(limits=limits)


_RAG_BUILDERS = {
    "docling_rag": (_docling_rag_parser, lambda parser, path: parser._convert(str(path))),
    "vision_rag": (
        _vision_rag_parser,
        lambda parser, path: parser.convert_doc_to_chunks_with_vision(str(path)),
    ),
    "text_rag": (_text_rag_parser, lambda parser, path: parser.convert_doc_to_chunks(path)),
}


@pytest.mark.parametrize("kind", sorted(_RAG_BUILDERS))
@pytest.mark.parametrize(
    ("data", "detected"),
    [(PNG, "a PNG image"), (DOCX, "a DOCX document"), (HTML, "plain text")],
    ids=["png", "docx", "html"],
)
def test_the_rag_parsers_refuse_another_type_named_pdf(tmp_path, kind, data, detected):
    pytest.importorskip("pymupdf")
    build, parse = _RAG_BUILDERS[kind]
    parser = build()
    with pytest.raises(FileTypeMismatchError, match=rf"'report\.pdf' is {detected}"):
        parse(parser, _file(tmp_path, "report.pdf", data))
    if kind != "text_rag":
        assert parser.converter.calls == []


@pytest.mark.parametrize("kind", ["docling_rag", "vision_rag"])
@pytest.mark.parametrize(
    ("name", "data"), [("notes.docx", DOCX), ("scan.png", PNG)], ids=["docx", "png"]
)
def test_the_docling_rag_parsers_still_convert_what_docling_reads(tmp_path, kind, name, data):
    # Docling converts DOCX and images too: content that matches its extension
    # reaches the converter (the fake raises AssertionError once it runs).
    build, parse = _RAG_BUILDERS[kind]
    parser = build()
    with pytest.raises(AssertionError, match="the converter ran"):
        parse(parser, _file(tmp_path, name, data))
    assert len(parser.converter.calls) == 1


@pytest.mark.parametrize(
    ("name", "data"),
    [("notes.docx", XLSX), ("notes.md", PNG), ("notes.txt", PDF)],
    ids=["workbook-as-docx", "image-as-md", "pdf-as-txt"],
)
def test_the_text_rag_parser_refuses_a_document_of_another_type(tmp_path, name, data):
    with pytest.raises(FileTypeMismatchError, match=rf"'{name}' is"):
        _text_rag_parser().convert_doc_to_chunks(_file(tmp_path, name, data))


@pytest.mark.parametrize("kind", sorted(_RAG_BUILDERS))
def test_the_rag_parsers_check_the_size_first(tmp_path, monkeypatch, kind):
    from gaik.software_components.input_limits import InputLimitError, InputLimits

    build, parse = _RAG_BUILDERS[kind]
    parser = build(InputLimits(max_file_bytes=1024))
    path = _many_entries(tmp_path / "report.pdf", 50)
    opened = _refuse_zipfile(monkeypatch)
    with pytest.raises(InputLimitError, match="max_file_bytes"):
        parse(parser, path)
    assert opened == []
