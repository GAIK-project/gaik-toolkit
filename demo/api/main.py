"""
GAIK Toolkit Demo API

FastAPI backend that provides REST endpoints for the GAIK toolkit components.
"""

from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv

# Load .env.local from demo folder
env_path = Path(__file__).parent.parent / ".env.local"
load_dotenv(env_path)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import classifier, extractor, parser, transcriber


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    print("GAIK Demo API starting...")
    yield
    # Shutdown
    print("GAIK Demo API shutting down...")


app = FastAPI(
    title="GAIK Toolkit Demo API",
    description="REST API for GAIK toolkit components: extractor, parser, classifier, transcriber",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS for Next.js frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(parser.router, prefix="/parse", tags=["Parser"])
app.include_router(classifier.router, prefix="/classify", tags=["Classifier"])
app.include_router(extractor.router, prefix="/extract", tags=["Extractor"])
app.include_router(transcriber.router, prefix="/transcribe", tags=["Transcriber"])


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "ok", "service": "gaik-demo-api"}


@app.get("/")
async def root():
    """Root endpoint with API info"""
    return {
        "name": "GAIK Toolkit Demo API",
        "version": "0.1.0",
        "docs": "/docs",
        "endpoints": {
            "parse": "/parse - Document parsing (PDF, DOCX)",
            "classify": "/classify - Document classification",
            "extract": "/extract - Data extraction",
            "transcribe": "/transcribe - Audio/video transcription",
        },
    }
