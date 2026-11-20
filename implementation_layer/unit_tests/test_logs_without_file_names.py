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


def test_a_failing_docx_parse_logs_no_file_name(tmp_path, caplog):
    pytest.importorskip("docx")
    from gaik.software_components.parsers.docx_parser import DocxParser

    path = _private_file(tmp_path, ".docx", b"PK\x03\x04" + b"\x00broken" * 50)
    with caplog.at_level(logging.DEBUG), pytest.raises(Exception):
        DocxParser().parse_document(str(path))
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
