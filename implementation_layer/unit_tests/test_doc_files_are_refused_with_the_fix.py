"""A Word 97-2003 .doc is refused with the fix, and no longer advertised.

DocxParser listed .doc as supported and the document classifier routed .doc files to
it, but python-docx reads only .docx: a real .doc failed with a type error that did not
say what to do. A DOCX saved under the .doc name is still read.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest

pytest.importorskip("docx")

from docx import Document  # noqa: E402
from gaik.software_components.file_type import FileTypeMismatchError  # noqa: E402
from gaik.software_components.parsers.docx_parser import DocxParser  # noqa: E402

# The start of an OLE compound file: what Word 97-2003 saves as .doc.
OLE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 512


def _legacy_doc(path):
    path.write_bytes(OLE)
    return path


def _docx_named_doc(path):
    document = Document()
    document.add_paragraph("Meeting notes")
    document.save(path)
    return path


def test_docx_parser_refuses_a_word_97_2003_doc_with_the_fix(tmp_path):
    path = _legacy_doc(tmp_path / "old.doc")
    parser = DocxParser()

    for parse in (parser.parse_docx, parser.parse_document):
        with pytest.raises(FileTypeMismatchError, match=r"save it as \.docx") as raised:
            parse(str(path))
        assert raised.value.detected == "ole"
        assert raised.value.file_name == "old.doc"
    assert not parser.is_supported_file("old.doc")
    assert parser.supported_extensions == [".docx"]


def test_docx_parser_still_reads_a_docx_saved_under_the_doc_name(tmp_path):
    path = _docx_named_doc(tmp_path / "renamed.doc")

    assert DocxParser().parse_document(str(path))["text_content"] == "Meeting notes"


def _classifier(monkeypatch):
    from gaik.software_components.doc_classifier import classifier as module

    monkeypatch.setattr(module, "build_compat_client", lambda config: SimpleNamespace())
    classifier = module.DocumentClassifier({"model": "test-model"})
    texts = []

    def classify_with_llm(text, classes):
        texts.append(text)
        return {"class": "invoice", "confidence": 1.0, "reasoning": "stub"}

    monkeypatch.setattr(classifier, "_classify_with_llm", classify_with_llm)
    return classifier, texts


def test_the_classifier_refuses_a_legacy_doc_with_the_fix(tmp_path, monkeypatch):
    classifier, texts = _classifier(monkeypatch)
    path = _legacy_doc(tmp_path / "old.doc")

    with pytest.raises(ValueError, match=r"save it as \.docx") as raised:
        classifier.classify(str(path), ["invoice"])

    assert ".doc," not in str(raised.value)  # .doc is not listed as supported
    assert texts == []


def test_the_classifier_skips_legacy_docs_in_a_folder_and_says_why(tmp_path, monkeypatch, caplog):
    classifier, texts = _classifier(monkeypatch)
    _legacy_doc(tmp_path / "old.doc")
    _docx_named_doc(tmp_path / "renamed.doc")
    _docx_named_doc(tmp_path / "notes.docx")

    with caplog.at_level(logging.WARNING):
        results = classifier.classify(str(tmp_path), ["invoice"])

    assert sorted(results) == ["notes.docx", "renamed.doc"]
    assert texts == ["Meeting notes", "Meeting notes"]
    assert "Skipping 1 .doc file(s)" in caplog.text
    assert "save it as .docx" in caplog.text


def test_a_folder_of_legacy_docs_only_names_the_fix(tmp_path, monkeypatch):
    classifier, _ = _classifier(monkeypatch)
    _legacy_doc(tmp_path / "old.doc")

    with pytest.raises(ValueError, match=r"no valid files[\s\S]*save it as \.docx"):
        classifier.classify(str(tmp_path), ["invoice"])
