"""
RAG workflow: parser -> embedder -> vector store -> retriever -> answer generator.

The parser is ``"vision"`` (default: Docling layout plus a vision model for images) or
``"text"`` (the document's own text layer, with no Docling and no vision model).
"""

from __future__ import annotations

import inspect
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from gaik.software_components.config import get_openai_config
from gaik.software_components.input_limits import InputLimits
from gaik.software_components.RAG._chunk_ids import check_document_id
from gaik.software_components.RAG.answer_generator import AnswerGenerator, Citation
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
    """The answer and the retrieved chunks.

    With ``citations=True``, ``citations`` lists the retrieved chunks the answer cites
    and ``dropped_citations`` the ``[name, page X]`` citations it wrote that match
    none of them (removed from the answer). When the answer streams, both are filled
    in once it has been read to the end.
    """

    answer: str | Iterable[str]
    documents: list[Document]
    citations: list[Citation] = field(default_factory=list)
    dropped_citations: list[str] = field(default_factory=list)


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
        owner: str | None = None,
        embedding_model: str | None = None,
        retriever_top_k: int = 5,
        retriever_threshold: float | None = None,
        retriever_hybrid: bool = False,
        retriever_rerank: bool = False,
        citations: bool = True,
        stream: bool = True,
        conversation_history: bool = True,
        last_n: int = 3,
        limits: InputLimits | None = None,
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
            owner: A user or session id. Documents this workflow indexes are recorded
                for it, and its questions retrieve only its own documents, also from a
                collection that other owners share. Without it, every workflow on the
                same collection and folder reads every document in it.
            embedding_model: Optional embedding model override.
            retriever_top_k: Number of chunks to retrieve.
            retriever_threshold: Optional score threshold.
            retriever_hybrid: Enable hybrid (BM25 + vector) scoring.
            retriever_rerank: Enable reranker for final ordering.
            citations: Include citations in generated answers.
            stream: Stream responses by default.
            conversation_history: Maintain last n Q/A pairs. The history is kept on
                this object, so a service with several users needs one workflow per
                user or session; a shared one answers each user with the others'
                earlier questions in its prompt.
            last_n: Number of Q/A pairs to keep if conversation_history is True.
            limits: Input limits for the parser (file size, PDF pages, images
                described); a document over one raises ``InputLimitError`` before it
                is parsed. ``None`` (default) leaves the parser's own defaults
                (:meth:`~gaik.software_components.input_limits.InputLimits.local_parsing`:
                no page limit) and passes nothing, so a parser class without a
                ``limits`` argument still works.
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

        # Only set limits are passed: a replacement parser class may not take them.
        parser_kwargs = {} if limits is None else {"limits": limits}
        if parser == "text":
            from .text_parser import TextRagParser

            self.parser = TextRagParser(**parser_kwargs)
        else:
            if VisionRagParser is None:
                raise ImportError(
                    "parser='vision' needs pip install 'gaik[rag-workflow]'; "
                    "parser='text' needs only 'gaik[rag-workflow-text]'"
                ) from _vision_import_error
            self.parser = VisionRagParser(vision_config=self.parser_config, **parser_kwargs)
        self.embedder = Embedder(config=self.embedding_config, model=embedding_model)
        self.vector_store = VectorStore(
            persist=persist,
            persist_path=persist_path,
            collection_name=collection_name,
            owner=owner,
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
        file_paths: Iterable[str | Path],
        *,
        filenames: list[str] | None = None,
        document_ids: list[str | int] | None = None,
    ) -> IndexResult:
        """Parse and index documents into the vector store.

        Each file is one document, with ``document_id`` its entry in
        ``document_ids`` or else its path with forward slashes
        (``Path(path).as_posix()``). The path is not resolved: ``data/a.pdf``
        and its absolute path are two documents, and one relative path indexed
        from two working directories is one. The display name in
        ``filenames`` does not identify it, so two files with the same name are
        two documents. Indexing a document again replaces its chunks: the ones
        it no longer has are deleted, and unchanged ones are not stored twice.
        Files saved under a new temporary path each time are new documents;
        pass ``document_ids`` to replace them.

        Args:
            file_paths: Paths to the files to index: PDFs, or with ``parser="text"``
                also Word (.docx), text and Markdown files.
            filenames: Optional list of original filenames (same order as file_paths).
                       If provided, these names are used instead of extracting from paths.
            document_ids: Optional stable id for each file (same order as
                file_paths), such as a database key; indexing the same id again
                replaces that document's chunks. A string or an int (stored as
                its string); any other id raises ``ValueError`` before a file
                is parsed.
        """
        file_paths = list(file_paths)
        if document_ids is not None and len(document_ids) != len(file_paths):
            raise ValueError("document_ids must have one entry for each file path")
        # Every id is checked before any file is parsed: parsing can cost vision calls.
        # The path in one spelling, so "docs/a.pdf" and Path("docs/a.pdf") (with
        # backslashes on Windows) are the same document.
        ids = [
            check_document_id(
                document_ids[i] if document_ids is not None else Path(file_path).as_posix()
            )
            for i, file_path in enumerate(file_paths)
        ]
        all_chunks: list[Document] = []

        for i, (file_path, document_id) in enumerate(zip(file_paths, ids)):
            doc_name = filenames[i] if filenames and i < len(filenames) else None
            if self.parser_kind == "text":
                chunks = self.parser.convert_doc_to_chunks(file_path, document_name=doc_name)
            else:
                chunks = self.parser.convert_doc_to_chunks_with_vision(
                    str(file_path), document_name=doc_name
                )
            for chunk in chunks:
                chunk.metadata = {**(chunk.metadata or {}), "document_id": document_id}
            all_chunks.extend(chunks)

        embeddings, documents = self.embedder.embed(all_chunks)
        self._replace_documents(list(dict.fromkeys(ids)), documents, embeddings)

        return IndexResult(
            num_documents=len(file_paths),
            num_chunks=len(all_chunks),
            vector_store_path=self.vector_store.persist_path if self.vector_store.persist else None,
        )

    def _replace_documents(
        self, document_ids: list[str], documents: list[Document], embeddings: list[list[float]]
    ) -> None:
        """Store ``documents`` in place of the stored chunks of ``document_ids``.

        Runs after the embedding succeeds, so a failed call leaves the old chunks.
        A store whose ``add()`` takes ``replace`` deletes the old chunks only once
        the new ones are stored; otherwise they are deleted first. Both act on
        the store's owner, when it has one.
        """
        store = self.vector_store
        delete_document = getattr(store, "delete_document", None)
        with_chunks = {(doc.metadata or {}).get("document_id") for doc in documents}
        if _takes_replace(store.add):
            store.add(documents, embeddings, replace=True)
            # A file that now has no chunks keeps none of its old ones.
            if delete_document is not None:
                for document_id in document_ids:
                    if document_id not in with_chunks:
                        delete_document(document_id)
            return
        # A replacement store without replace: delete first, then add.
        if delete_document is not None:
            for document_id in document_ids:
                delete_document(document_id)
        store.add(documents, embeddings)

    def delete_document(self, document_id: str | int) -> int:
        """Delete one document's chunks from the vector store.

        Args:
            document_id: The id the document was indexed under: its entry in
                ``document_ids``, or else its path with forward slashes
                (``Path(path).as_posix()``).

        Returns:
            The number of chunks deleted.
        """
        return self.vector_store.delete_document(document_id)

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
        cited = self.answer_generator.generate_with_citations(query, documents, stream=stream)
        return RAGWorkflowResult(
            answer=cited.answer,
            documents=documents,
            citations=cited.citations,
            dropped_citations=cited.dropped_citations,
        )


def _takes_replace(add) -> bool:
    """Whether a store's ``add`` accepts ``replace=``."""
    try:
        parameters = inspect.signature(add).parameters.values()
    except (TypeError, ValueError):
        return False
    return any(p.name == "replace" or p.kind is p.VAR_KEYWORD for p in parameters)
