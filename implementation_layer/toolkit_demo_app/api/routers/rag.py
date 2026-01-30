"""RAG router - RAG pipeline endpoints for document indexing and Q&A."""

import asyncio
import json
import tempfile
import uuid
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from implementation_layer.toolkit_demo_app.api.utils import get_api_config

router = APIRouter()


def sse_event(event_type: str, data: dict) -> str:
    """Format data as an SSE event."""
    return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"


# In-memory storage for RAG workflow instances (keyed by collection_id)
RAG_INSTANCES: dict[str, object] = {}

# Concurrency control: per-collection locks to prevent race conditions
_collection_locks: dict[str, asyncio.Lock] = {}
_global_lock = asyncio.Lock()

# File size limit
MAX_FILE_SIZE_MB = 20
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024

# Example document configuration
EXAMPLE_PDF_PATH = Path(__file__).parent.parent.parent / "public" / "GAIK_Test_Document_Demo.pdf"
EXAMPLE_COLLECTION_ID = "example-demo"


async def _get_collection_lock(collection_id: str) -> asyncio.Lock:
    """Get or create a lock for a specific collection."""
    async with _global_lock:
        if collection_id not in _collection_locks:
            _collection_locks[collection_id] = asyncio.Lock()
        return _collection_locks[collection_id]


class Citation(BaseModel):
    """A citation from a source document."""

    text: str
    document_name: str
    page_number: str | int


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
    """Get existing RAG workflow or create a new one."""
    from gaik.software_modules.RAG_workflow import RAGWorkflow

    if collection_id and collection_id in RAG_INSTANCES:
        return RAG_INSTANCES[collection_id], collection_id

    # Create new workflow with in-memory storage (non-persistent for demo)
    new_id = str(uuid.uuid4())[:8]
    config = get_api_config()

    workflow = RAGWorkflow(
        api_config=config,
        persist=False,  # In-memory for demo
        collection_name=f"gaik_rag_{new_id}",
        retriever_top_k=5,
        citations=True,
        stream=True,
    )

    RAG_INSTANCES[new_id] = workflow
    return workflow, new_id


@router.post("/index", response_model=IndexResponse)
async def index_documents(
    files: list[UploadFile] = File(...),
    collection_id: str | None = Form(None),
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
                    # Index the document with original filename (without extension)
                    original_name = Path(file.filename).stem
                    result = workflow.index_documents([tmp_path], filenames=[original_name])
                    total_chunks += result.num_chunks

                    indexed_docs.append(
                        IndexedDocument(
                            filename=file.filename,
                            chunk_count=result.num_chunks,
                            status="indexed",
                        )
                    )
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
        no_results_msg = (
            "I couldn't find any relevant information in the indexed documents "
            "to answer your question. Please try rephrasing or ensure relevant "
            "documents have been indexed."
        )
        if not result.documents:
            return QueryResponse(answer=no_results_msg, sources=[])

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
            query_embedding = workflow.embedder.embed_query(question)
            results = workflow.vector_store.search(query_embedding, top_k=top_k)

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

                no_results_msg = (
                    "I couldn't find any relevant information in the indexed documents "
                    "to answer your question. Please try rephrasing or ensure relevant "
                    "documents have been indexed."
                )
                yield sse_event("result", {"answer": no_results_msg, "sources": []})
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

            # Send final result
            yield sse_event(
                "result",
                {
                    "answer": full_answer,
                    "sources": sources,
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

    - **collection_id**: The collection to clear
    """
    if collection_id not in RAG_INSTANCES:
        raise HTTPException(status_code=404, detail="Collection not found")

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
async def load_example_document():
    """
    Load the pre-bundled example PDF for demo purposes.

    Returns existing example collection if already loaded, otherwise indexes the example document.
    """
    from gaik.software_modules.RAG_workflow import RAGWorkflow

    # If already loaded, return existing collection
    if EXAMPLE_COLLECTION_ID in RAG_INSTANCES:
        workflow = RAG_INSTANCES[EXAMPLE_COLLECTION_ID]
        chunk_count = workflow.vector_store.count()
        return IndexResponse(
            collection_id=EXAMPLE_COLLECTION_ID,
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

    # Verify example file exists
    if not EXAMPLE_PDF_PATH.exists():
        raise HTTPException(
            status_code=500,
            detail="Example document not found. Please contact administrator.",
        )

    # Acquire lock and index
    lock = await _get_collection_lock(EXAMPLE_COLLECTION_ID)

    async with lock:
        # Double-check after acquiring lock (another request may have loaded it)
        if EXAMPLE_COLLECTION_ID in RAG_INSTANCES:
            workflow = RAG_INSTANCES[EXAMPLE_COLLECTION_ID]
            chunk_count = workflow.vector_store.count()
            return IndexResponse(
                collection_id=EXAMPLE_COLLECTION_ID,
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
            workflow = RAGWorkflow(
                api_config=config,
                persist=False,
                collection_name=f"gaik_rag_{EXAMPLE_COLLECTION_ID}",
                retriever_top_k=5,
                citations=True,
                stream=True,
            )

            result = workflow.index_documents(
                [str(EXAMPLE_PDF_PATH)], filenames=["GAIK_Test_Document_Demo"]
            )

            RAG_INSTANCES[EXAMPLE_COLLECTION_ID] = workflow

            return IndexResponse(
                collection_id=EXAMPLE_COLLECTION_ID,
                document_count=1,
                chunk_count=result.num_chunks,
                documents=[
                    IndexedDocument(
                        filename="GAIK_Test_Document_Demo.pdf",
                        chunk_count=result.num_chunks,
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
