"""
GAIK Toolkit Demo API

FastAPI backend that provides REST endpoints for the GAIK toolkit components.
"""

import asyncio
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
load_dotenv(env_path, override=True)

from fastapi import FastAPI, Request  # noqa: E402, I001
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402

from gaik import __version__ as gaik_version  # noqa: E402

try:
    # Docker: routers/ is in same directory as main.py
    from routers import (
        classifier,
        dental_transcription,
        diary,
        extractor,
        llm_judge,
        luvata_order,
        parser,
        pipeline,
        postgres_agent,
        rag,
        text_to_speech,
        transcriber,
        video_search,
        vision_extractor,
    )
except ImportError:
    # Local dev: running from project root with api.main:app
    from api.routers import (
        classifier,
        dental_transcription,
        diary,
        extractor,
        llm_judge,
        luvata_order,
        parser,
        pipeline,
        postgres_agent,
        rag,
        text_to_speech,
        transcriber,
        video_search,
        vision_extractor,
    )

# The Solution Wizard router makes source-tree assumptions at module load: it
# imports the optional `claude_agent_sdk`, spawns the `claude` CLI binary, and
# resolves REPO_ROOT via Path(__file__).parents[4] (which only exists in the
# repo layout, not the flattened container layout, where it raises IndexError).
# Import it defensively so any load failure disables only the wizard instead of
# crashing the entire API (every other demo, including luvata-order).
try:
    try:
        from routers import solution_wizard
    except ImportError:
        from api.routers import solution_wizard
except Exception as exc:  # noqa: BLE001
    solution_wizard = None
    logger.warning("Solution Wizard router unavailable; disabling it (%s)", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("GAIK Demo API starting...")
    cleanup_task = asyncio.create_task(dental_transcription._cleanup_old_subtitles())
    wizard_cleanup_task = (
        asyncio.create_task(solution_wizard.cleanup_idle_sessions())
        if solution_wizard is not None
        else None
    )
    yield
    # Shutdown
    cleanup_task.cancel()
    if wizard_cleanup_task is not None:
        wizard_cleanup_task.cancel()
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
app.include_router(
    vision_extractor.router,
    prefix="/extract-vision",
    tags=["Vision Extractor"],
)
app.include_router(transcriber.router, prefix="/transcribe", tags=["Transcriber"])
app.include_router(text_to_speech.router, prefix="/text-to-speech", tags=["Text-to-Speech"])
app.include_router(pipeline.router, prefix="/pipeline", tags=["Pipeline"])
app.include_router(rag.router, prefix="/rag", tags=["RAG"])
app.include_router(postgres_agent.router, prefix="/postgres-agent", tags=["Postgres Agent"])
app.include_router(diary.router, prefix="/diary", tags=["Diary"])
app.include_router(
    dental_transcription.router,
    prefix="/dental-transcribe",
    tags=["Video Transcription"],
)
app.include_router(video_search.router, prefix="/video-search", tags=["Video Search"])
app.include_router(luvata_order.router, tags=["Luvata Order"])
app.include_router(llm_judge.router, prefix="/llm-judge", tags=["LLM Judge"])
if solution_wizard is not None:
    app.include_router(solution_wizard.router, prefix="/wizard", tags=["Solution Wizard"])


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
            "extract-vision": (
                "/extract-vision - Single-pass vision extraction (PDF/image → structured data)"
            ),
            "transcribe": "/transcribe - Audio/video transcription",
            "text-to-speech": "/text-to-speech - Text-to-speech audio generation",
            "pipeline": "/pipeline - End-to-end pipelines (audio/document to structured data)",
            "rag": "/rag - RAG pipeline (document indexing and Q&A with citations)",
            "postgres-agent": "/postgres-agent - PostgreSQL text-to-SQL query agent",
            "diary": "/diary - Construction diary (Työmaapäiväkirja) workflow",
            "dental-transcribe": "/dental-transcribe - Dental transcription with SRT/VTT subtitles",
            "video-search": "/video-search - Semantic dental video search (pgvector)",
            "luvata-order": "/luvata-order - Luvata ABB order processing with BOM matching",
            "llm-judge": "/llm-judge - LLM-as-judge: text-pair, hallucinations, validate, panel",
        },
    }
