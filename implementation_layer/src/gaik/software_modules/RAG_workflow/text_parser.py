"""Text-layer parsing for ``RAGWorkflow(parser="text")``: no Docling, no vision model.

PDFs are read page by page from their text layer with PyMuPDF, Word files with
python-docx, and text or Markdown files as UTF-8. Each page is split into chunks at
paragraph boundaries, with a short overlap, and every chunk carries the metadata the
vision parser gives (``source``, ``document_name``, ``page_number``, ``heading``,
``chunk_id``), so retrieval and citations work the same.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

try:
    from langchain_core.documents import Document
except ImportError:  # pragma: no cover - optional dependency
    Document = None  # type: ignore[assignment]

SUFFIXES = (".pdf", ".docx", ".txt", ".md")
_BLANK_LINE = re.compile(r"\n\s*\n")
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


class TextRagParser:
    """Chunks a document's own text, page by page, without Docling or a vision model.

    Args:
        chunk_chars: Longest chunk in characters.
        overlap_chars: Characters of the previous chunk repeated at the start of the
            next one on the same page, so a sentence split between chunks is found
            from either.
    """

    def __init__(self, chunk_chars: int = 1200, overlap_chars: int = 150):
        if Document is None:
            raise ImportError(
                "RAGWorkflow(parser='text') needs langchain-core: "
                "pip install 'gaik[rag-workflow-text]'"
            )
        if chunk_chars < 200 or not 0 <= overlap_chars < chunk_chars // 2:
            raise ValueError("chunk_chars must be >= 200 and overlap_chars < chunk_chars / 2")
        self.chunk_chars = chunk_chars
        self.overlap_chars = overlap_chars

    def convert_doc_to_chunks(
        self, path: str | Path, document_name: str | None = None
    ) -> list[Document]:
        """Chunks of one file.

        Raises:
            ValueError: An unsupported file type, or a file without any text (a
                scanned PDF needs ``parser="vision"``).
        """
        path = Path(path)
        name = document_name or os.path.splitext(path.name)[0]
        pages = self._pages(path)
        if not any(text.strip() for _, text in pages):
            raise ValueError(
                f"{path.name}: no text layer to read. Scanned PDFs need "
                "RAGWorkflow(parser='vision')."
            )
        chunks: list[Document] = []
        for page_number, text in pages:
            for piece in self._split(text):
                chunks.append(
                    Document(
                        page_content=piece,
                        metadata={
                            "source": str(path),
                            "document_name": name,
                            "page_number": page_number if page_number is not None else "Unknown",
                            "heading": None,
                            "chunk_id": len(chunks),
                        },
                    )
                )
        return chunks

    @staticmethod
    def _pages(path: Path) -> list[tuple[int | None, str]]:
        suffix = path.suffix.lower()
        if suffix == ".pdf":
            try:
                import pymupdf
            except ImportError as exc:  # pragma: no cover - depends on the installed extra
                raise ImportError(
                    "RAGWorkflow(parser='text') reads PDFs with PyMuPDF: "
                    "pip install 'gaik[rag-workflow-text]'"
                ) from exc
            with pymupdf.open(path) as doc:
                return [(number, page.get_text("text")) for number, page in enumerate(doc, 1)]
        if suffix == ".docx":
            try:
                import docx
            except ImportError as exc:  # pragma: no cover - depends on the installed extra
                raise ImportError(
                    "RAGWorkflow(parser='text') reads Word files with python-docx: "
                    "pip install 'gaik[rag-workflow-text]'"
                ) from exc
            document = docx.Document(str(path))
            blocks = [paragraph.text for paragraph in document.paragraphs]
            for table in document.tables:
                for row in table.rows:
                    blocks.append(" | ".join(cell.text.strip() for cell in row.cells))
            return [(None, "\n\n".join(blocks))]
        if suffix in (".txt", ".md"):
            return [(None, path.read_text(encoding="utf-8", errors="replace"))]
        raise ValueError(
            f"{path.name}: unsupported file type {suffix or '(none)'}; "
            f"parser='text' reads {', '.join(SUFFIXES)}"
        )

    def _split(self, text: str) -> list[str]:
        """Pack paragraphs into chunks of at most ``chunk_chars``, with overlap."""
        paragraphs: list[str] = []
        for block in _BLANK_LINE.split(text.replace("\r\n", "\n")):
            paragraph = " ".join(block.split())
            if not paragraph:
                continue
            if len(paragraph) <= self.chunk_chars:
                paragraphs.append(paragraph)
            else:
                paragraphs.extend(self._split_long(paragraph))

        chunks: list[str] = []
        current = ""
        for paragraph in paragraphs:
            candidate = f"{current}\n\n{paragraph}" if current else paragraph
            if len(candidate) <= self.chunk_chars:
                current = candidate
                continue
            chunks.append(current)
            tail = self._tail(current)
            current = f"{tail} {paragraph}" if tail else paragraph
            if len(current) > self.chunk_chars:
                current = paragraph
        if current:
            chunks.append(current)
        return chunks

    def _split_long(self, paragraph: str) -> list[str]:
        """A paragraph longer than a chunk, cut at sentence ends, else at spaces."""
        pieces: list[str] = []
        current = ""
        for sentence in _SENTENCE_END.split(paragraph):
            while len(sentence) > self.chunk_chars:
                cut = sentence.rfind(" ", 0, self.chunk_chars)
                cut = cut if cut > 0 else self.chunk_chars
                if current:
                    pieces.append(current)
                    current = ""
                pieces.append(sentence[:cut].strip())
                sentence = sentence[cut:].strip()
            candidate = f"{current} {sentence}".strip()
            if len(candidate) <= self.chunk_chars:
                current = candidate
            else:
                pieces.append(current)
                current = sentence
        if current:
            pieces.append(current)
        return pieces

    def _tail(self, chunk: str) -> str:
        """The last ``overlap_chars`` of a chunk, starting at a word."""
        if not self.overlap_chars:
            return ""
        tail = chunk[-self.overlap_chars :]
        space = tail.find(" ")
        return tail[space + 1 :] if 0 <= space < len(tail) - 1 else tail
