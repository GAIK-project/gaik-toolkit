"""The RAG parsers' progress prints name the file by its tag, and print no heading.

``verbose=True`` is the default, and a file name, the folders above it or a heading can
name a person. Offline: Docling's converter and chunker are replaced by fakes.
"""

import sys
import types

import pytest

pytest.importorskip("langchain_core")

from gaik.software_components._log_names import file_tag  # noqa: E402

PATH = "/data/Matti Virtanen/Matti_Virtanen_lab_results.pdf"
PRIVATE = ("Matti", "Virtanen", "lab_results")


class _Chunk:
    def __init__(self, text: str, page: int, *, fail: bool = False) -> None:
        self.text = text
        self._page = page
        self._fail = fail

    def model_dump(self):
        if self._fail:
            raise ValueError(f"cannot read a chunk of {PATH}")
        return {
            "meta": {
                "origin": {"filename": "Matti_Virtanen_lab_results.pdf"},
                "headings": ["Matti Virtanen, lab results"],
                "doc_items": [{"prov": [{"page_no": self._page}]}],
            }
        }


@pytest.fixture
def fake_chunker(monkeypatch):
    chunks = [_Chunk(f"text {i}", 1) for i in range(4)] + [_Chunk("x", 2, fail=True)]

    class _Chunker:
        def chunk(self, doc):
            return iter(chunks)

    module = types.ModuleType("docling.chunking")
    module.HierarchicalChunker = _Chunker
    if "docling" not in sys.modules:
        try:
            import docling  # noqa: F401
        except ImportError:
            monkeypatch.setitem(sys.modules, "docling", types.ModuleType("docling"))
    monkeypatch.setitem(sys.modules, "docling.chunking", module)


def _assert_tagged(printed: str) -> None:
    assert "Chunk 1:" in printed, "the parser printed no chunk line, so the test checks nothing"
    assert "Error processing chunk" in printed, "the error line was not printed"
    for private in PRIVATE:
        assert private not in printed, printed
    assert file_tag(PATH) in printed


def test_the_vision_parser_prints_no_file_name_or_heading(fake_chunker, monkeypatch, capsys):
    from gaik.software_components.RAG.rag_parser_vision.parser import VisionRagParser

    parser = VisionRagParser.__new__(VisionRagParser)
    parser.verbose = True
    result = types.SimpleNamespace(document=object())
    monkeypatch.setattr(parser, "_convert_with_vision", lambda path: (result, "md", {}))
    monkeypatch.setattr(parser, "_maybe_save_markdown", lambda *a: None)

    for document_name in (None, "Matti_Virtanen_lab_results"):
        docs = parser.convert_doc_to_chunks_with_vision(PATH, document_name=document_name)
        printed = capsys.readouterr().out
        _assert_tagged(printed)
        assert f"vision-enhanced content from {file_tag(PATH)}" in printed
        # The chunks themselves keep the name and the heading.
        assert docs[0].metadata["document_name"] == "Matti_Virtanen_lab_results"
        assert docs[0].metadata["heading"] == "Matti Virtanen, lab results"


def test_the_docling_parser_prints_no_file_name_or_heading(fake_chunker, monkeypatch, capsys):
    # Without Docling, fake_chunker has put an empty "docling" module in place, which
    # importorskip("docling") would find; the parser needs the converter module.
    pytest.importorskip("docling.document_converter")
    from gaik.software_components.RAG.rag_parser_docling.parser import DoclingRagParser

    parser = DoclingRagParser.__new__(DoclingRagParser)
    result = types.SimpleNamespace(document=types.SimpleNamespace(pages=[1, 2]))
    monkeypatch.setattr(parser, "_convert", lambda path: result)

    docs = parser.convert_pdf_to_chunks_with_metadata(PATH)

    _assert_tagged(capsys.readouterr().out)
    assert docs[0].metadata["heading"] == "Matti Virtanen, lab results"
