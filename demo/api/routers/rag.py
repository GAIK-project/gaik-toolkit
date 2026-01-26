"""RAG router - RAG pipeline endpoints for document indexing and Q&A."""

import json
import os
import tempfile
import uuid
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

router = APIRouter()


def sse_event(event_type: str, data: dict) -> str:
    """Format data as an SSE event."""
    return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"


# In-memory storage for RAG workflow instances (keyed by collection_id)
RAG_INSTANCES: dict[str, object] = {}


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


def _get_api_config():
    """Get OpenAI configuration from environment (Azure or standard)."""
    use_azure = bool(os.getenv("AZURE_API_KEY"))
    if not use_azure and not os.getenv("OPENAI_API_KEY"):
        raise HTTPException(
            status_code=500,
            detail="Either AZURE_API_KEY or OPENAI_API_KEY environment variable must be set",
        )

    from gaik.building_blocks.config import get_openai_config

    return get_openai_config(use_azure=use_azure)


def _get_or_create_workflow(collection_id: str | None = None):
    """Get existing RAG workflow or create a new one."""
    from gaik.software_components.RAG_workflow import RAGWorkflow

    if collection_id and collection_id in RAG_INSTANCES:
        return RAG_INSTANCES[collection_id], collection_id

    # Create new workflow with in-memory storage (non-persistent for demo)
    new_id = str(uuid.uuid4())[:8]
    config = _get_api_config()

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

    # Validate file types
    for file in files:
        if not file.filename:
            raise HTTPException(status_code=400, detail="File has no filename")
        suffix = Path(file.filename).suffix.lower()
        if suffix != ".pdf":
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type: {suffix}. Only PDF files are supported.",
            )

    try:
        workflow, coll_id = _get_or_create_workflow(collection_id)
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
                # Index the document
                result = workflow.index_documents([tmp_path])
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
        raise HTTPException(status_code=404, detail="Collection not found. Please index documents first.")

    try:
        workflow = RAG_INSTANCES[collection_id]

        # Query with non-streaming for simple response
        result = workflow.ask(
            question,
            top_k=top_k,
            stream=False,
        )

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
        raise HTTPException(status_code=404, detail="Collection not found. Please index documents first.")

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
            from langchain_core.documents import Document
            documents = [doc for doc, _score in results]

            # Extract sources
            sources = []
            for doc in documents:
                meta = doc.metadata
                sources.append({
                    "document_name": meta.get("document_name", "unknown"),
                    "relevance_score": meta.get("relevance_score"),
                    "page_number": meta.get("page_number", "unknown"),
                })

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
            yield sse_event("result", {
                "answer": full_answer,
                "sources": sources,
            })

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

    return {"status": "success", "message": f"Collection {collection_id} cleared"}


@router.delete("/clear")
async def clear_all_collections():
    """Clear all RAG collections."""
    count = len(RAG_INSTANCES)
    RAG_INSTANCES.clear()

    return {"status": "success", "message": f"Cleared {count} collections"}
