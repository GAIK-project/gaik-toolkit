"""VisionRagParser puts a page's image descriptions on one chunk, not on every chunk.

Offline: Docling's chunker and the vision call are replaced by fakes.
"""

import sys
import types

import pytest

pytest.importorskip("langchain_core")

from gaik.software_components.RAG.rag_parser_vision.parser import (  # noqa: E402
    VisionRagParser,
)


class _Chunk:
    def __init__(self, text, page):
        self.text = text
        self._page = page

    def model_dump(self):
        return {"meta": {"doc_items": [{"prov": [{"page_no": self._page}]}]}}


@pytest.fixture
def parser(monkeypatch):
    chunks = [_Chunk(f"text {i}", 1) for i in range(6)]

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

    instance = VisionRagParser.__new__(VisionRagParser)
    instance.verbose = False
    result = types.SimpleNamespace(document=object())
    descriptions = {1: ["A bar chart of sales."], 2: ["A photo of a site."]}
    monkeypatch.setattr(instance, "_convert_with_vision", lambda path: (result, "md", descriptions))
    monkeypatch.setattr(instance, "_maybe_save_markdown", lambda *a: None)
    return instance


def test_a_page_description_is_on_one_chunk_and_a_textless_page_keeps_its_own(parser):
    docs = parser.convert_doc_to_chunks_with_vision("report.pdf")

    with_chart = [d for d in docs if "A bar chart of sales." in d.page_content]
    assert len(with_chart) == 1
    assert with_chart[0].metadata["page_number"] == 1

    photo = [d for d in docs if "A photo of a site." in d.page_content]
    assert len(photo) == 1
    assert photo[0].metadata["page_number"] == 2
    assert len(docs) == 7
