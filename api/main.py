"""
GAIK Toolkit API

Lightweight FastAPI service for audio transcription and document parsing.
Designed for deployment to CSC Rahti 2 (OpenShift/Kubernetes).
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.config import settings
from api.routers import parse, transcribe

logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan management."""
    logger.info(f"GAIK API starting on {settings.HOST}:{settings.PORT}")
    logger.info(f"Debug mode: {settings.DEBUG}")
    logger.info(f"Using Azure: {settings.USE_AZURE}")
    yield
    logger.info("GAIK API shutting down")


app = FastAPI(
    title="GAIK Toolkit API",
    description="API for audio transcription and document parsing using GAIK building blocks.",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
    openapi_url="/openapi.json" if settings.DEBUG else None,
)

# CORS middleware (if configured)
if settings.CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

# Include routers
app.include_router(transcribe.router, prefix="/transcribe", tags=["Transcription"])
app.include_router(parse.router, prefix="/parse", tags=["Parsing"])


@app.get("/health", tags=["Health"])
async def health_check():
    """
    Health check endpoint for Kubernetes probes.

    Returns service status for liveness/readiness checks.
    """
    return {
        "status": "healthy",
        "service": "gaik-api",
        "version": "1.0.0",
    }


@app.get("/", tags=["Info"])
async def root():
    """
    API root endpoint with service information.

    Returns available endpoints and basic API info.
    """
    return {
        "name": "GAIK Toolkit API",
        "version": "1.0.0",
        "description": "Audio transcription and document parsing API",
        "endpoints": {
            "POST /transcribe": "Transcribe audio/video files (Whisper + LLM enhancement)",
            "POST /parse": "Parse PDF/DOCX documents",
            "GET /health": "Health check for Kubernetes",
        },
        "authentication": "X-API-Key header required",
        "docs": "/docs" if settings.DEBUG else "Disabled in production",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "api.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
    )
