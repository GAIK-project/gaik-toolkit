"""RAG router - RAG pipeline endpoints for document indexing and Q&A."""

import asyncio
import json
import os
import re
import tempfile
import time
import uuid
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any, Literal

try:
    from utils import get_api_config, sse_event
except ImportError:
    from api.utils import get_api_config, sse_event
import requests
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from langchain_core.documents import Document
from pydantic import BaseModel

router = APIRouter()


# In-memory storage for RAG workflow instances (keyed by collection_id)
RAG_INSTANCES: dict[str, object] = {}

# Concurrency control: per-collection locks to prevent race conditions
_collection_locks: dict[str, asyncio.Lock] = {}
_global_lock = asyncio.Lock()

# File size limit
MAX_FILE_SIZE_MB = 20
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024

# Page limit for demo (CPU environment in CSC Rahti)
MAX_PAGES_VISION_PLUS_DEMO = 10
MAX_PAGES_OTHER_PARSERS_DEMO = 200

NO_RESULTS_MESSAGE = (
    "I couldn't find any relevant information in the indexed documents "
    "to answer your question. Please try rephrasing or ensure relevant "
    "documents have been indexed."
)

# Custom RAG prompt - friendly and flexible
CUSTOM_RAG_PROMPT = """You are a friendly document assistant 📚

Your job is to help users find information from the indexed documents.

Guidelines:
- Use ONLY facts found in Context. Do not rely on prior knowledge or assumptions.
- If Context is empty or irrelevant, say: "I couldn't find this in the provided documents."
- Be conversational and helpful - use emojis sparingly 😊
- For greetings (Hello, Hi, etc.): respond briefly and warmly, then ask what
  they'd like to know. 
- Do not summarize or list document contents unless the user asks.
- Only share specific information when the user asks for it
- Include citations [document_name, page X] when answering questions
- If you can't find an answer, say so briefly and suggest they rephrase

Answer style:
- Be conversational and helpful.
- If the answer requires steps, use short bullet points.
- Use valid Markdown for all bullet and numbered lists.
- Put the bullet marker and the content on the same line.
- Do not output empty bullet lines.
- When you cannot answer, suggest 2-3 rephrased queries that would likely retrieve better context.

Context:
{context}

Question: {query}"""

# Example document configuration
# In Docker: /app/routers/rag.py -> parent.parent = /app/
# Local dev: api/routers/rag.py -> parent.parent.parent = toolkit_demo_app/
_base_path = Path(__file__).parent.parent  # /app/ in Docker, api/ locally
if (_base_path / "public").exists():
    _public_path = _base_path / "public"
else:
    _public_path = _base_path.parent / "public"  # Fallback for local dev
EXAMPLE_PDF_PATH = _public_path / "GAIK_Test_Document_Demo.pdf"
EXAMPLE_INDEX_PATH = _public_path / "example-index.json"
EXAMPLE_COLLECTION_PREFIX = "example-demo"


def extract_page_filter(query: str) -> dict | None:
    """Extract page number filter from query like 'page 2' or 'sivu 2'.

    Returns a filter dict for VectorStore.search() if a page number is found,
    otherwise returns None for normal semantic search.
    """
    match = re.search(r"(?:page|sivu)\s*(\d+)", query, re.IGNORECASE)
    if match:
        return {"page_number": int(match.group(1))}
    return None


def _normalize_source_name(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def _filter_sources_by_citations(
    answer: str, sources: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    citations = re.findall(r"\[([^\]]+?),\s*page\s+(\d+)\]", answer, flags=re.IGNORECASE)
    if not citations:
        return sources

    cited_pairs = {
        (_normalize_source_name(document_name), str(page_number))
        for document_name, page_number in citations
    }
    filtered = [
        source
        for source in sources
        if (
            _normalize_source_name(str(source.get("document_name", ""))),
            str(source.get("page_number", "")),
        )
        in cited_pairs
    ]
    return filtered or sources


async def _get_collection_lock(collection_id: str) -> asyncio.Lock:
    """Get or create a lock for a specific collection."""
    async with _global_lock:
        if collection_id not in _collection_locks:
            _collection_locks[collection_id] = asyncio.Lock()
        return _collection_locks[collection_id]


class DoclingRagApiClient:
    def __init__(
        self,
        *,
        api_base: str,
        password: str,
        timeout_seconds: int = 60 * 30,
        healthcheck_timeout_seconds: int = 30,
    ) -> None:
        if not api_base:
            raise ValueError("api_base is required")
        if not password:
            raise ValueError("password is required")

        self.api_base = api_base.rstrip("/")
        self.password = password
        self.timeout_seconds = timeout_seconds
        self.healthcheck_timeout_seconds = healthcheck_timeout_seconds

    def parse_document(self, document_path: str | Path) -> dict[str, Any]:
        start_time = time.perf_counter()
        input_file = Path(document_path)
        if not input_file.exists():
            raise FileNotFoundError(f"Document file not found: {input_file}")
        if input_file.suffix.lower() != ".pdf":
            raise ValueError("Docling RAG endpoint currently supports PDF files only")

        r = requests.get(f"{self.api_base}/health", timeout=self.healthcheck_timeout_seconds)
        r.raise_for_status()

        with input_file.open("rb") as f:
            files = {"file": (input_file.name, f, "application/pdf")}
            r = requests.post(
                f"{self.api_base}/parsedocument_rag",
                files=files,
                headers={"key": self.password},
                timeout=self.timeout_seconds,
            )
            if r.status_code >= 400:
                r.raise_for_status()

        payload = r.json()
        return {
            "source_file": payload.get("source_file") or input_file.name,
            "chunk_count": payload.get("chunk_count") or 0,
            "chunks": payload.get("chunks") or [],
            "elapsed_seconds": round(time.perf_counter() - start_time, 3),
        }


class DemoRagWorkflow:
    def __init__(self, *, config: dict, collection_name: str) -> None:
        from gaik.software_components.RAG.answer_generator import AnswerGenerator
        from gaik.software_components.RAG.embedder import Embedder
        from gaik.software_components.RAG.retriever import Retriever
        from gaik.software_components.RAG.vector_store import VectorStore

        self.api_config = config
        self.embedder = Embedder(config=config)
        self.vector_store = VectorStore(
            persist=False,
            collection_name=collection_name,
        )
        self.retriever = Retriever(
            embedder=self.embedder,
            vector_store=self.vector_store,
            top_k=5,
        )
        self.answer_generator = AnswerGenerator(
            config=config,
            citations=True,
            stream=True,
            prompt=CUSTOM_RAG_PROMPT,
            conversation_history=True,
            last_n=3,
        )

    def index_chunk_documents(self, documents: list[Document]) -> int:
        embeddings, docs = self.embedder.embed(documents)
        self.vector_store.add(docs, embeddings)
        return len(docs)

    def ask(self, query: str, *, top_k: int | None = None, stream: bool | None = None):
        documents = self.retriever.search(query, top_k=top_k)
        answer = self.answer_generator.generate(query, documents, stream=stream)
        return type("RAGWorkflowResult", (), {"answer": answer, "documents": documents})()


def _build_demo_workflow(config: dict, collection_id: str) -> DemoRagWorkflow:
    return DemoRagWorkflow(
        config=config,
        collection_name=f"gaik_rag_{collection_id}",
    )


def _parse_with_pymupdf(file_path: str | Path, document_name: str) -> list[Document]:
    import fitz

    docs: list[Document] = []
    pdf = fitz.open(str(file_path))
    try:
        for index, page in enumerate(pdf, start=1):
            text = page.get_text().strip()
            if not text:
                continue
            docs.append(
                Document(
                    page_content=text,
                    metadata={
                        "source": str(file_path),
                        "document_name": document_name,
                        "page_number": index,
                        "heading": None,
                        "chunk_id": len(docs),
                        "parser_used": "pymupdf",
                    },
                )
            )
    finally:
        pdf.close()

    if not docs:
        raise ValueError("PyMuPDF parser produced no text chunks")
    return docs


def _parse_with_vision_plus(
    file_path: str | Path, document_name: str, config: dict
) -> list[Document]:
    from gaik.software_components.RAG.rag_parser_vision import VisionRagParser

    parser = VisionRagParser(vision_config=config)
    docs = parser.convert_doc_to_chunks_with_vision(str(file_path), document_name=document_name)
    for doc in docs:
        doc.metadata["parser_used"] = "vision_plus"
    return docs


def _parse_with_docling_rag_api(file_path: str | Path, document_name: str) -> list[Document]:
    api_base = os.getenv("DOCLING_API_BASE")
    password = os.getenv("DOCLING_API_PASSWORD")
    if not api_base or not password:
        raise ValueError("DOCLING_API_BASE and DOCLING_API_PASSWORD must be set")

    client = DoclingRagApiClient(api_base=api_base, password=password)
    result = client.parse_document(file_path)
    docs: list[Document] = []
    for index, chunk in enumerate(result["chunks"]):
        metadata = dict(chunk.get("metadata") or {})
        metadata.setdefault("source", str(file_path))
        metadata["document_name"] = document_name
        metadata.setdefault("chunk_id", index)
        metadata["parser_used"] = "docling_rag"
        docs.append(Document(page_content=chunk.get("page_content", ""), metadata=metadata))

    if not docs:
        raise ValueError("Docling RAG parser returned no chunks")
    return docs


def _parse_document_to_chunks(
    file_path: str | Path,
    *,
    document_name: str,
    parser_choice: str,
    config: dict,
) -> tuple[list[Document], str]:
    choice = (parser_choice or "docling_rag").lower()
    if choice == "pymupdf":
        return _parse_with_pymupdf(file_path, document_name), "pymupdf"
    if choice == "docling_rag":
        try:
            return _parse_with_docling_rag_api(file_path, document_name), "docling_rag"
        except Exception as exc:
            print(f"Docling RAG parser failed, falling back to PyMuPDF: {exc}")
            return _parse_with_pymupdf(file_path, document_name), "pymupdf"
    if choice == "vision_plus":
        try:
            return _parse_with_vision_plus(file_path, document_name, config), "vision_plus"
        except Exception as exc:
            print(f"Vision+ parser failed, falling back to PyMuPDF: {exc}")
            return _parse_with_pymupdf(file_path, document_name), "pymupdf"
    raise ValueError(f"Unsupported parser_choice: {parser_choice}")


class Source(BaseModel):
    """A source document reference."""

    document_name: str
    relevance_score: float | None = None
    page_number: str | int | None = None


class IndexedDocument(BaseModel):
    """Information about an indexed document."""

    filename: str
    chunk_count: int
    status: Literal["indexed", "processing", "error"] = "indexed"


class IndexResponse(BaseModel):
    """Response from document indexing."""

    collection_id: str
    document_count: int
    chunk_count: int
    documents: list[IndexedDocument]
    status: Literal["success", "error"]
    error: str | None = None


class QueryResponse(BaseModel):
    """Response from RAG query."""

    answer: str
    sources: list[Source]
    error: str | None = None


class StatusResponse(BaseModel):
    """Response from status check."""

    collection_id: str | None
    document_count: int
    chunk_count: int
    is_ready: bool


def _get_or_create_workflow(collection_id: str | None = None):
    """Get existing demo RAG workflow or create a new one."""
    if collection_id and collection_id in RAG_INSTANCES:
        return RAG_INSTANCES[collection_id], collection_id

    new_id = str(uuid.uuid4())[:8]
    config = get_api_config()
    workflow = _build_demo_workflow(config, new_id)
    RAG_INSTANCES[new_id] = workflow
    return workflow, new_id


@router.post("/index", response_model=IndexResponse)
async def index_documents(
    files: list[UploadFile] = File(...),
    collection_id: str | None = Form(None),
    parser_choice: Literal["vision_plus", "docling_rag", "pymupdf"] = Form("docling_rag"),
):
    """
    Index PDF documents into the RAG vector store.

    - **files**: PDF files to index
    - **collection_id**: Optional existing collection to add to
    """
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")

    # Validate file types and sizes
    for file in files:
        if not file.filename:
            raise HTTPException(status_code=400, detail="File has no filename")
        suffix = Path(file.filename).suffix.lower()
        if suffix != ".pdf":
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type: {suffix}. Only PDF files are supported.",
            )
        # Check file size using underlying file object
        file.file.seek(0, 2)  # Seek to end
        file_size = file.file.tell()
        file.file.seek(0)  # Reset to beginning
        if file_size > MAX_FILE_SIZE_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"File '{file.filename}' exceeds maximum size of {MAX_FILE_SIZE_MB}MB",
            )

    # Determine target collection ID for locking
    target_coll_id = collection_id or str(uuid.uuid4())[:8]

    # Acquire lock for this collection to prevent concurrent modifications
    lock = await _get_collection_lock(target_coll_id)

    try:
        async with lock:
            workflow, coll_id = _get_or_create_workflow(
                collection_id if collection_id else target_coll_id
            )
            indexed_docs: list[IndexedDocument] = []
            total_chunks = 0

            for file in files:
                # Save uploaded file temporarily
                suffix = Path(file.filename).suffix.lower()
                with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                    content = await file.read()
                    tmp.write(content)
                    tmp_path = tmp.name

                try:
                    # Check page count for PDF files (demo limit)
                    if suffix == ".pdf":
                        import fitz  # PyMuPDF - already available via docling

                        doc = fitz.open(tmp_path)
                        page_count = doc.page_count
                        doc.close()

                        max_pages = (
                            MAX_PAGES_VISION_PLUS_DEMO
                            if parser_choice == "vision_plus"
                            else MAX_PAGES_OTHER_PARSERS_DEMO
                        )
                        if page_count > max_pages:
                            Path(tmp_path).unlink(missing_ok=True)
                            raise HTTPException(
                                status_code=400,
                                detail=(
                                    f"PDF has {page_count} pages. "
                                    f"Maximum {max_pages} pages allowed for parser '{parser_choice}'. "
                                    f"Try a smaller document or switch parser."
                                ),
                            )

                    # Parse and index the document with the selected parser
                    original_name = Path(file.filename).stem
                    chunks, parser_used = _parse_document_to_chunks(
                        tmp_path,
                        document_name=original_name,
                        parser_choice=parser_choice,
                        config=workflow.api_config,
                    )
                    num_chunks = workflow.index_chunk_documents(chunks)
                    total_chunks += num_chunks

                    indexed_docs.append(
                        IndexedDocument(
                            filename=file.filename,
                            chunk_count=num_chunks,
                            status="indexed",
                        )
                    )
                    print(f"Indexed {file.filename} using parser: {parser_used}")
                except Exception as e:
                    indexed_docs.append(
                        IndexedDocument(
                            filename=file.filename,
                            chunk_count=0,
                            status="error",
                        )
                    )
                    print(f"Error indexing {file.filename}: {e}")
                finally:
                    Path(tmp_path).unlink(missing_ok=True)

            return IndexResponse(
                collection_id=coll_id,
                document_count=len(files),
                chunk_count=total_chunks,
                documents=indexed_docs,
                status="success" if total_chunks > 0 else "error",
            )

    except ImportError as e:
        raise HTTPException(
            status_code=500, detail=f"Required components not installed: {e}"
        ) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/query", response_model=QueryResponse)
async def query_rag(
    question: str = Form(...),
    collection_id: str = Form(...),
    top_k: int = Form(5),
    search_type: Literal["semantic", "hybrid"] = Form("semantic"),
):
    """
    Query the RAG system with a question.

    - **question**: The question to answer
    - **collection_id**: The collection to query
    - **top_k**: Number of chunks to retrieve
    - **search_type**: Type of search (semantic or hybrid)
    """
    if not question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    if collection_id not in RAG_INSTANCES:
        raise HTTPException(
            status_code=404, detail="Collection not found. Please index documents first."
        )

    try:
        workflow = RAG_INSTANCES[collection_id]

        # Query with non-streaming for simple response
        result = workflow.ask(
            question,
            top_k=top_k,
            stream=False,
        )

        # Handle empty results gracefully
        if not result.documents:
            return QueryResponse(answer=NO_RESULTS_MESSAGE, sources=[])

        # Extract sources from retrieved documents
        sources: list[Source] = []
        for doc in result.documents:
            meta = doc.metadata
            sources.append(
                Source(
                    document_name=meta.get("document_name", "unknown"),
                    relevance_score=meta.get("relevance_score"),
                    page_number=meta.get("page_number", "unknown"),
                )
            )

        return QueryResponse(
            answer=result.answer if isinstance(result.answer, str) else "".join(result.answer),
            sources=sources,
        )

    except ImportError as e:
        raise HTTPException(
            status_code=500, detail=f"Required components not installed: {e}"
        ) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/query/stream")
async def query_rag_stream(
    question: str = Form(...),
    collection_id: str = Form(...),
    top_k: int = Form(5),
    search_type: Literal["semantic", "hybrid"] = Form("semantic"),
):
    """
    Query the RAG system with SSE streaming response.

    Returns Server-Sent Events with progress updates and streamed answer.
    """
    if not question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    if collection_id not in RAG_INSTANCES:
        raise HTTPException(
            status_code=404, detail="Collection not found. Please index documents first."
        )

    async def event_generator() -> AsyncGenerator[str, None]:
        steps = [
            {"step": 1, "name": "Searching documents", "status": "pending"},
            {"step": 2, "name": "Generating answer", "status": "pending"},
        ]

        yield sse_event("steps", {"steps": steps})

        try:
            workflow = RAG_INSTANCES[collection_id]

            # Step 1: Retrieve documents
            steps[0]["status"] = "in_progress"
            yield sse_event("step_update", steps[0])

            # Get the retriever to search
            # Check if query contains page number reference (e.g., "page 2", "sivu 3")
            page_filter = extract_page_filter(question)
            query_embedding = workflow.embedder.embed_query(question)
            results = workflow.vector_store.search(
                query_embedding, top_k=top_k, filters=page_filter
            )

            # Convert to documents with optional hybrid/rerank
            documents = [doc for doc, _score in results] if results else []

            # Handle empty results gracefully
            if not documents:
                steps[0]["status"] = "completed"
                steps[0]["message"] = "No relevant documents found"
                yield sse_event("step_update", steps[0])
                yield sse_event("sources", {"sources": []})

                steps[1]["status"] = "completed"
                yield sse_event("step_update", steps[1])

                yield sse_event("result", {"answer": NO_RESULTS_MESSAGE, "sources": []})
                return

            # Extract sources
            sources = []
            for doc in documents:
                meta = doc.metadata
                sources.append(
                    {
                        "document_name": meta.get("document_name", "unknown"),
                        "relevance_score": meta.get("relevance_score"),
                        "page_number": meta.get("page_number", "unknown"),
                    }
                )

            steps[0]["status"] = "completed"
            steps[0]["message"] = f"Found {len(documents)} relevant chunks"
            yield sse_event("step_update", steps[0])
            yield sse_event("sources", {"sources": sources})

            # Step 2: Generate answer with streaming
            steps[1]["status"] = "in_progress"
            yield sse_event("step_update", steps[1])

            # Stream the answer
            answer_gen = workflow.answer_generator.generate(question, documents, stream=True)

            collected_answer = []
            for chunk in answer_gen:
                collected_answer.append(chunk)
                yield sse_event("answer_chunk", {"chunk": chunk})

            full_answer = "".join(collected_answer)

            steps[1]["status"] = "completed"
            yield sse_event("step_update", steps[1])

            # Send final result with sources limited to the pages actually cited.
            cited_sources = _filter_sources_by_citations(full_answer, sources)
            yield sse_event(
                "result",
                {
                    "answer": full_answer,
                    "sources": cited_sources,
                },
            )

        except ImportError as e:
            yield sse_event("error", {"message": f"Required components not installed: {e}"})
        except Exception as e:
            for step in steps:
                if step["status"] == "in_progress":
                    step["status"] = "error"
                    step["message"] = str(e)
                    yield sse_event("step_update", step)
                    break
            yield sse_event("error", {"message": str(e)})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/status/{collection_id}", response_model=StatusResponse)
async def get_status(collection_id: str):
    """
    Get the status of a RAG collection.

    - **collection_id**: The collection to check
    """
    if collection_id not in RAG_INSTANCES:
        return StatusResponse(
            collection_id=None,
            document_count=0,
            chunk_count=0,
            is_ready=False,
        )

    workflow = RAG_INSTANCES[collection_id]
    chunk_count = workflow.vector_store.count()

    return StatusResponse(
        collection_id=collection_id,
        document_count=0,  # We don't track this separately
        chunk_count=chunk_count,
        is_ready=chunk_count > 0,
    )


@router.delete("/clear/{collection_id}")
async def clear_collection(collection_id: str):
    """
    Clear a RAG collection and free resources.

    Idempotent: returns success even if collection doesn't exist
    (e.g., after server restart when client still has old collection ID).

    - **collection_id**: The collection to clear
    """
    if collection_id in RAG_INSTANCES:
        del RAG_INSTANCES[collection_id]

    # Clean up the lock for this collection
    if collection_id in _collection_locks:
        del _collection_locks[collection_id]

    return {"status": "success", "message": f"Collection {collection_id} cleared"}


@router.delete("/clear")
async def clear_all_collections():
    """Clear all RAG collections."""
    count = len(RAG_INSTANCES)
    RAG_INSTANCES.clear()
    _collection_locks.clear()

    return {"status": "success", "message": f"Cleared {count} collections"}


@router.post("/load-example", response_model=IndexResponse)
async def load_example_document(
    parser_choice: Literal["vision_plus", "docling_rag", "pymupdf"] = Form("docling_rag"),
):
    """
    Load the pre-indexed example document for demo purposes.

    Uses pre-computed embeddings from example-index.json for instant loading.
    Falls back to real-time indexing if pre-indexed file not found.
    """
    example_collection_id = f"{EXAMPLE_COLLECTION_PREFIX}-{parser_choice}"

    # If already loaded, return existing collection
    if example_collection_id in RAG_INSTANCES:
        workflow = RAG_INSTANCES[example_collection_id]
        chunk_count = workflow.vector_store.count()
        return IndexResponse(
            collection_id=example_collection_id,
            document_count=1,
            chunk_count=chunk_count,
            documents=[
                IndexedDocument(
                    filename="GAIK_Test_Document_Demo.pdf",
                    chunk_count=chunk_count,
                    status="indexed",
                )
            ],
            status="success",
        )

    # Acquire lock
    lock = await _get_collection_lock(example_collection_id)

    async with lock:
        # Double-check after acquiring lock
        if example_collection_id in RAG_INSTANCES:
            workflow = RAG_INSTANCES[example_collection_id]
            chunk_count = workflow.vector_store.count()
            return IndexResponse(
                collection_id=example_collection_id,
                document_count=1,
                chunk_count=chunk_count,
                documents=[
                    IndexedDocument(
                        filename="GAIK_Test_Document_Demo.pdf",
                        chunk_count=chunk_count,
                        status="indexed",
                    )
                ],
                status="success",
            )

        try:
            config = get_api_config()
            workflow = _build_demo_workflow(config, example_collection_id)

            # Try to load pre-indexed data first for Vision+ only (instant loading)
            if parser_choice == "vision_plus" and EXAMPLE_INDEX_PATH.exists():
                with open(EXAMPLE_INDEX_PATH, encoding="utf-8") as f:
                    index_data = json.load(f)

                documents = [
                    Document(page_content=c["page_content"], metadata=c["metadata"])
                    for c in index_data["chunks"]
                ]
                embeddings = [c["embedding"] for c in index_data["chunks"]]
                workflow.vector_store.add(documents, embeddings)
                RAG_INSTANCES[example_collection_id] = workflow

                chunk_count = len(documents)
                return IndexResponse(
                    collection_id=example_collection_id,
                    document_count=1,
                    chunk_count=chunk_count,
                    documents=[
                        IndexedDocument(
                            filename="GAIK_Test_Document_Demo.pdf",
                            chunk_count=chunk_count,
                            status="indexed",
                        )
                    ],
                    status="success",
                )

            if not EXAMPLE_PDF_PATH.exists():
                raise HTTPException(
                    status_code=500,
                    detail="Example document not found. Please contact administrator.",
                )

            chunks, parser_used = _parse_document_to_chunks(
                EXAMPLE_PDF_PATH,
                document_name="GAIK_Test_Document_Demo",
                parser_choice=parser_choice,
                config=config,
            )
            chunk_count = workflow.index_chunk_documents(chunks)
            print(f"Loaded example using parser: {parser_used}")

            RAG_INSTANCES[example_collection_id] = workflow

            return IndexResponse(
                collection_id=example_collection_id,
                document_count=1,
                chunk_count=chunk_count,
                documents=[
                    IndexedDocument(
                        filename="GAIK_Test_Document_Demo.pdf",
                        chunk_count=chunk_count,
                        status="indexed",
                    )
                ],
                status="success",
            )

        except ImportError as e:
            raise HTTPException(
                status_code=500, detail=f"Required components not installed: {e}"
            ) from e
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=f"Failed to load example document: {e}"
            ) from e
