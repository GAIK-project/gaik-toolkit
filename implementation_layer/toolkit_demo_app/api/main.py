"""
GAIK Toolkit Demo API

FastAPI backend that provides REST endpoints for the GAIK toolkit components.
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Load .env.local from toolkit_demo_app folder - must be before other imports
env_path = Path(__file__).parent.parent / ".env.local"
load_dotenv(env_path)

try:
    # Docker: routers/ is in same directory as main.py
    from routers import (  # noqa: E402
        classifier,
        diary,
        extractor,
        parser,
        pipeline,
        rag,
        transcriber,
    )
except ImportError:
    # Local dev: running from project root with api.main:app
    from api.routers import (  # noqa: E402
        classifier,
        diary,
        extractor,
        parser,
        pipeline,
        rag,
        transcriber,
    )
from fastapi import FastAPI, Request  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402

from gaik import __version__ as gaik_version  # noqa: E402


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("GAIK Demo API starting...")
    yield
    # Shutdown
    logger.info("GAIK Demo API shutting down...")


app = FastAPI(
    title="GAIK Toolkit Demo API",
    description="REST API for GAIK toolkit components",
    version=gaik_version,
    lifespan=lifespan,
    redirect_slashes=False,
)

# CORS for Next.js frontend (allowing all origins for cluster-internal usage)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler for unhandled errors."""
    logger.error(f"Unhandled error: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )

# Include routers
app.include_router(parser.router, prefix="/parse", tags=["Parser"])
app.include_router(classifier.router, prefix="/classify", tags=["Classifier"])
app.include_router(extractor.router, prefix="/extract", tags=["Extractor"])
app.include_router(transcriber.router, prefix="/transcribe", tags=["Transcriber"])
app.include_router(pipeline.router, prefix="/pipeline", tags=["Pipeline"])
app.include_router(rag.router, prefix="/rag", tags=["RAG"])
app.include_router(diary.router, prefix="/diary", tags=["Diary"])


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "ok", "service": "gaik-demo-api"}


@app.get("/")
async def root():
    """Root endpoint with API info"""
    return {
        "name": "GAIK Toolkit Demo API",
        "version": gaik_version,
        "docs": "/docs",
        "endpoints": {
            "parse": "/parse - Document parsing (PDF, DOCX)",
            "classify": "/classify - Document classification",
            "extract": "/extract - Data extraction",
            "transcribe": "/transcribe - Audio/video transcription",
            "pipeline": "/pipeline - End-to-end pipelines (audio/document to structured data)",
            "rag": "/rag - RAG pipeline (document indexing and Q&A with citations)",
            "diary": "/diary - Construction diary (Työmaapäiväkirja) workflow",
        },
    }
