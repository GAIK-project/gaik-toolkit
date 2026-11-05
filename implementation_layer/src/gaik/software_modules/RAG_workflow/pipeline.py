"""
RAG workflow: parser -> embedder -> vector store -> retriever -> answer generator.

The parser is ``"vision"`` (default: Docling layout plus a vision model for images) or
``"text"`` (the document's own text layer, with no Docling and no vision model).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from gaik.software_components.config import get_openai_config
from gaik.software_components.RAG.answer_generator import AnswerGenerator
from gaik.software_components.RAG.embedder import Embedder
from gaik.software_components.RAG.retriever import Retriever
from gaik.software_components.RAG.vector_store import VectorStore

try:
    from langchain_core.documents import Document
except ImportError:  # pragma: no cover - optional dependency
    Document = None  # type: ignore[assignment]

# The vision parser needs Docling, torch and transformers, which a text-only install
# (gaik[rag-workflow-text]) lacks. Any failure to import them (a missing package, or a
# torch DLL that does not load) leaves parser="text" usable and is reported on use.
_vision_import_error: Exception | None = None
try:
    from gaik.software_components.RAG.rag_parser_vision import VisionRagParser
except Exception as exc:  # noqa: BLE001  # pragma: no cover - depends on the environment
    VisionRagParser = None  # type: ignore[assignment,misc]
    _vision_import_error = exc


@dataclass
class IndexResult:
    num_documents: int
    num_chunks: int
    vector_store_path: str | None


@dataclass
class RAGWorkflowResult:
    answer: str | Iterable[str]
    documents: list[Document]


class RAGWorkflow:
    """End-to-end RAG workflow: parse, embed, store, retrieve and answer."""

    def __init__(
        self,
        *,
        api_config: dict | None = None,
        use_azure: bool = True,
        parser: Literal["vision", "text"] = "vision",
        parser_config: dict | None = None,
        embedding_config: dict | None = None,
        answer_config: dict | None = None,
        persist: bool = True,
        persist_path: str = "chroma_store",
        collection_name: str = "gaik_rag",
        embedding_model: str | None = None,
        retriever_top_k: int = 5,
        retriever_threshold: float | None = None,
        retriever_hybrid: bool = False,
        retriever_rerank: bool = False,
        citations: bool = True,
        stream: bool = True,
        conversation_history: bool = True,
        last_n: int = 3,
    ) -> None:
        """
        Initialize the workflow.

        Args:
            api_config: OpenAI/Azure config. If None, built via get_openai_config(use_azure).
            use_azure: Whether to build default config for Azure (ignored if api_config supplied).
            parser: How documents become chunks. ``"vision"`` (default) parses PDFs with
                VisionRagParser: Docling layout plus a vision model that describes
                images; it needs the ``rag-workflow`` extra (Docling, torch).
                ``"text"`` reads the text layer of PDFs, and Word, text and Markdown
                files, with no Docling and no vision model (``rag-workflow-text``
                extra); a scanned PDF without a text layer raises ValueError.
            parser_config: Optional separate config for the vision model (``parser="vision"``
                only).
            embedding_config: Optional separate config for the embedding provider.
            answer_config: Optional separate config for the answer generation provider.
            persist: If True, use persistent Chroma vector store.
            persist_path: Directory for Chroma persistence.
            collection_name: Chroma collection name.
            embedding_model: Optional embedding model override.
            retriever_top_k: Number of chunks to retrieve.
            retriever_threshold: Optional score threshold.
            retriever_hybrid: Enable hybrid (BM25 + vector) scoring.
            retriever_rerank: Enable reranker for final ordering.
            citations: Include citations in generated answers.
            stream: Stream responses by default.
            conversation_history: Maintain last n Q/A pairs.
            last_n: Number of Q/A pairs to keep if conversation_history is True.
        """
        if parser not in ("vision", "text"):
            raise ValueError(f"parser must be 'vision' or 'text', not {parser!r}")
        self.parser_kind = parser
        self.api_config = api_config
        stage_configs = (embedding_config, answer_config)
        if parser == "vision":
            stage_configs += (parser_config,)
        if self.api_config is None and any(config is None for config in stage_configs):
            self.api_config = get_openai_config(use_azure=use_azure)
        self.parser_config = parser_config if parser_config is not None else self.api_config
        self.embedding_config = (
            embedding_config if embedding_config is not None else self.api_config
        )
        self.answer_config = answer_config if answer_config is not None else self.api_config

        if parser == "text":
            from .text_parser import TextRagParser

            self.parser = TextRagParser()
        else:
            if VisionRagParser is None:
                raise ImportError(
                    "parser='vision' needs pip install 'gaik[rag-workflow]'; "
                    "parser='text' needs only 'gaik[rag-workflow-text]'"
                ) from _vision_import_error
            self.parser = VisionRagParser(vision_config=self.parser_config)
        self.embedder = Embedder(config=self.embedding_config, model=embedding_model)
        self.vector_store = VectorStore(
            persist=persist,
            persist_path=persist_path,
            collection_name=collection_name,
        )
        self.retriever = Retriever(
            embedder=self.embedder,
            vector_store=self.vector_store,
            hybrid_search=retriever_hybrid,
            re_rank=retriever_rerank,
            top_k=retriever_top_k,
            score_threshold=retriever_threshold,
        )
        self.answer_generator = AnswerGenerator(
            config=self.answer_config,
            citations=citations,
            stream=stream,
            conversation_history=conversation_history,
            last_n=last_n,
        )

    def index_documents(
        self,
        file_paths: list[str | Path],
        *,
        filenames: list[str] | None = None,
    ) -> IndexResult:
        """Parse and index documents into the vector store.

        Args:
            file_paths: Paths to the files to index: PDFs, or with ``parser="text"``
                also Word (.docx), text and Markdown files.
            filenames: Optional list of original filenames (same order as file_paths).
                       If provided, these names are used instead of extracting from paths.
        """
        all_chunks: list[Document] = []

        for i, file_path in enumerate(file_paths):
            doc_name = filenames[i] if filenames and i < len(filenames) else None
            if self.parser_kind == "text":
                chunks = self.parser.convert_doc_to_chunks(file_path, document_name=doc_name)
            else:
                chunks = self.parser.convert_doc_to_chunks_with_vision(
                    str(file_path), document_name=doc_name
                )
            all_chunks.extend(chunks)

        embeddings, documents = self.embedder.embed(all_chunks)
        self.vector_store.add(documents, embeddings)

        return IndexResult(
            num_documents=len(file_paths),
            num_chunks=len(all_chunks),
            vector_store_path=self.vector_store.persist_path if self.vector_store.persist else None,
        )

    def ask(
        self,
        query: str,
        *,
        top_k: int | None = None,
        score_threshold: float | None = None,
        filters: dict | None = None,
        include_scores: bool = False,
        stream: bool | None = None,
    ) -> RAGWorkflowResult:
        """Retrieve relevant chunks and generate an answer."""
        documents = self.retriever.search(
            query,
            top_k=top_k,
            score_threshold=score_threshold,
            filters=filters,
            include_scores=include_scores,
        )
        answer = self.answer_generator.generate(query, documents, stream=stream)
        return RAGWorkflowResult(answer=answer, documents=documents)
