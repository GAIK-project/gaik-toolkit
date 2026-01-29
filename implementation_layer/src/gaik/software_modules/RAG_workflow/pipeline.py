"""
RAG workflow: vision parser -> embedder -> vector store -> retriever -> answer generator.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from gaik.software_components.config import get_openai_config
from gaik.software_components.RAG.answer_generator import AnswerGenerator
from gaik.software_components.RAG.embedder import Embedder
from gaik.software_components.RAG.rag_parser_vision import VisionRagParser
from gaik.software_components.RAG.retriever import Retriever
from gaik.software_components.RAG.vector_store import VectorStore

try:
    from langchain_core.documents import Document
except ImportError:  # pragma: no cover - optional dependency
    Document = None  # type: ignore[assignment]


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
    """End-to-end RAG workflow using vision parsing and re-ranked retrieval."""

    def __init__(
        self,
        *,
        api_config: dict | None = None,
        use_azure: bool = True,
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
        self.api_config = api_config or get_openai_config(use_azure=use_azure)

        self.parser = VisionRagParser(vision_config=self.api_config)
        self.embedder = Embedder(config=self.api_config, model=embedding_model)
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
            config=self.api_config,
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
            file_paths: List of paths to PDF files to index.
            filenames: Optional list of original filenames (same order as file_paths).
                       If provided, these names are used instead of extracting from paths.
        """
        all_chunks: list[Document] = []

        for i, file_path in enumerate(file_paths):
            doc_name = filenames[i] if filenames and i < len(filenames) else None
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
