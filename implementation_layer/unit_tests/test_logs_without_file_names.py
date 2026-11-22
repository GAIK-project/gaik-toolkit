"""Log lines name an input file by a tag, never by its folder or its name.

A file name and the folders above it can hold a person's name; the logs go to log stores
that more people read than the files. The errors raised to the caller keep the path.
"""

import logging
from pathlib import Path
from types import SimpleNamespace

import pytest
from gaik.software_components._log_names import file_tag

NAME = "Matti_Virtanen_report"


def _private_file(tmp_path: Path, suffix: str, content: bytes) -> Path:
    folder = tmp_path / "Matti Virtanen"
    folder.mkdir(exist_ok=True)
    path = folder / f"{NAME}{suffix}"
    path.write_bytes(content)
    return path


def _assert_no_name_in_logs(caplog, path: Path) -> None:
    messages = [record.getMessage() for record in caplog.records]
    assert messages, "the call logged nothing, so the test checks nothing"
    for message in messages:
        for private in (str(path.parent), path.name, path.stem, "Matti", "Virtanen"):
            assert private not in message, message
    assert any(file_tag(path) in message for message in messages)


def test_file_tag_keeps_a_known_extension_and_hides_the_name():
    tag = file_tag("/home/someone/Matti_Virtanen_report.pdf")
    assert tag.startswith("file ") and tag.endswith(".pdf")
    assert "Matti" not in tag and "someone" not in tag
    assert tag == file_tag("/home/someone/Matti_Virtanen_report.pdf")
    assert tag != file_tag("/home/someone/other.pdf")
    assert file_tag("Virtanen.Matti").startswith("file ")
    assert "Matti" not in file_tag("Virtanen.Matti")
    assert file_tag(None) == "file"


def test_a_failing_pdf_parse_logs_no_file_name(tmp_path, caplog):
    pytest.importorskip("fitz")
    from gaik.software_components.parsers.pymypdf import PyMuPDFParser

    path = _private_file(tmp_path, ".pdf", b"%PDF-1.7\n" + b"\x00broken" * 50)
    with caplog.at_level(logging.DEBUG), pytest.raises(Exception) as raised:
        PyMuPDFParser().parse_document(str(path))
    _assert_no_name_in_logs(caplog, path)
    # The caller still gets an error; it is not shortened here.
    assert raised.value is not None


def _docx_with_a_corrupt_body() -> bytes:
    """A real DOCX archive whose ``word/document.xml`` is not XML.

    It passes the content check (a ZIP holding ``word/document.xml``), so python-docx
    opens it and fails inside the parser's error handler, which logs the ERROR line.
    """
    import io
    import zipfile

    from docx import Document

    blank = io.BytesIO()
    Document().save(blank)
    broken = io.BytesIO()
    with zipfile.ZipFile(blank) as source, zipfile.ZipFile(broken, "w") as target:
        for item in source.infolist():
            data = source.read(item)
            if item.filename == "word/document.xml":
                data = b"<w:document broken"
            target.writestr(item, data)
    return broken.getvalue()


def test_a_failing_docx_parse_logs_no_file_name(tmp_path, caplog):
    pytest.importorskip("docx")
    from gaik.software_components.parsers.docx_parser import DocxParser

    path = _private_file(tmp_path, ".docx", _docx_with_a_corrupt_body())
    with caplog.at_level(logging.DEBUG), pytest.raises(Exception):
        DocxParser().parse_document(str(path))
    errors = [record.getMessage() for record in caplog.records if record.levelno == logging.ERROR]
    assert errors, "the parse failed before the parser's error handler, so its line is unchecked"
    assert all(file_tag(path) in message for message in errors), errors
    _assert_no_name_in_logs(caplog, path)


def test_a_skipped_file_in_a_classified_folder_logs_no_file_name(tmp_path, caplog):
    pytest.importorskip("typesafe_sdk")
    from gaik.software_components.jev_classifier import JevClassifier

    path = _private_file(tmp_path, ".pdf", b"not a pdf")
    classifier = JevClassifier(api_key="", client=SimpleNamespace())
    with caplog.at_level(logging.DEBUG):
        results = classifier.classify_file(str(path.parent), ["invoice", "receipt"])
    assert results[path.name]["class"] == "unknown"
    _assert_no_name_in_logs(caplog, path)


def test_the_document_classifier_logs_no_file_name(tmp_path, caplog, monkeypatch):
    from gaik.software_components.doc_classifier import classifier as module

    monkeypatch.setattr(module, "build_compat_client", lambda config: SimpleNamespace())
    path = _private_file(tmp_path, ".pdf", b"not a pdf")
    classifier = module.DocumentClassifier({"model": "test-model"})
    with caplog.at_level(logging.DEBUG):
        results = classifier.classify(str(path.parent), ["invoice", "receipt"])
    assert results[path.name]["class"] == "unknown"
    _assert_no_name_in_logs(caplog, path)


def test_an_empty_sheet_is_logged_without_the_workbook_name(tmp_path, caplog):
    duckdb = pytest.importorskip("duckdb")
    pytest.importorskip("openpyxl")
    from gaik.software_components.tabular_agent.loader import load_sources
    from openpyxl import Workbook

    path = _private_file(tmp_path, ".xlsx", b"")
    workbook = Workbook()
    workbook.active.title = "Matti Virtanen"
    data = workbook.create_sheet("Data")
    for row in (("region", "revenue"), ("North", "1,5"), ("South", "2,25")):
        data.append(list(row))
    workbook.save(path)

    con = duckdb.connect(":memory:")
    try:
        with caplog.at_level(logging.DEBUG):
            load_sources(con, [(None, path)])
    finally:
        con.close()
    _assert_no_name_in_logs(caplog, path)


def test_error_text_keeps_the_cause_and_tags_the_path(tmp_path):
    from gaik.software_components._log_names import error_text, file_tag

    path = tmp_path / "Matti Virtanen" / "Matti_Virtanen_report.pdf"
    exc = ValueError(f"cannot open '{path}': broken xref table")
    text = error_text(exc, path)
    assert text.startswith("ValueError: cannot open")
    assert "broken xref table" in text
    assert file_tag(path) in text
    assert "Matti" not in text and "Virtanen" not in text and str(tmp_path) not in text


def test_error_text_tags_a_bare_file_name_in_the_message(tmp_path):
    from gaik.software_components._log_names import error_text

    path = tmp_path / "Matti_Virtanen_report.docx"
    text = error_text(KeyError("Matti_Virtanen_report.docx"), path)
    assert "Matti" not in text and text.startswith("KeyError:")


def test_a_set_salt_gives_the_same_tag_in_another_process(tmp_path):
    import subprocess
    import sys

    code = (
        "from gaik.software_components._log_names import file_tag;"
        "print(file_tag('/data/Matti_Virtanen_report.pdf'))"
    )
    env = {**__import__("os").environ, "GAIK_LOG_TAG_SALT": "deployment-salt"}
    runs = {
        subprocess.run(
            [sys.executable, "-c", code], env=env, capture_output=True, text=True, check=True
        ).stdout
        for _ in range(2)
    }
    assert len(runs) == 1 and next(iter(runs)).startswith("file ")


def test_a_long_salt_still_gives_a_stable_tag():
    import subprocess
    import sys

    code = (
        "from gaik.software_components._log_names import file_tag;"
        "print(file_tag('/data/Matti_Virtanen_report.pdf'))"
    )
    # blake2b refuses a key over 64 bytes; the set salt is hashed first.
    env = {**__import__("os").environ, "GAIK_LOG_TAG_SALT": "x" * 96}
    runs = {
        subprocess.run(
            [sys.executable, "-c", code], env=env, capture_output=True, text=True, check=True
        ).stdout
        for _ in range(2)
    }
    assert len(runs) == 1 and next(iter(runs)).startswith("file ")


def test_error_text_tags_the_doubled_backslashes_of_an_oserror_repr():
    from gaik.software_components._log_names import error_text, file_tag

    path = r"C:\Users\Matti Virtanen\Matti_Virtanen_report.docx"
    exc = PermissionError(f"[Errno 13] Permission denied: {path!r}")
    text = error_text(exc, path)
    assert "Matti" not in text and "Virtanen" not in text, text
    assert file_tag(path) in text


def test_layout_inference_logs_no_file_or_sheet_name(caplog):
    from gaik.software_components.tabular_agent.loader import _resolve_layout
    from gaik.software_components.tabular_agent.models import SheetLayout

    grid = [["region", "revenue"], ["North", 1.5], ["South", 2.25]]

    def failing(label, rendered):
        raise RuntimeError(f"could not read {label}")

    def inferred(label, rendered):
        return SheetLayout(header_row=0, data_start_row=1, reasoning=f"read {label}")

    for infer in (failing, inferred):
        caplog.clear()
        with caplog.at_level(logging.DEBUG):
            _resolve_layout(
                grid,
                sheet_label="Matti_Virtanen_report.xlsx / Matti Virtanen",
                log_label="a sheet in file 1234abcd.xlsx",
                layout_inference="always",
                infer_layout=infer,
            )
        messages = [record.getMessage() for record in caplog.records]
        assert messages
        assert not any("Matti" in m or "Virtanen" in m for m in messages), messages
