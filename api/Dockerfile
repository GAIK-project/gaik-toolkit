# GAIK Toolkit API - Lightweight Production Dockerfile
# Designed for CSC Rahti 2 (OpenShift/Kubernetes)
# Optimized: No torch/docling, only essential dependencies

FROM python:3.12-slim

# Metadata
LABEL maintainer="GAIK Project"
LABEL description="GAIK Toolkit API for transcription and parsing"
LABEL version="1.0.0"

# Set working directory
WORKDIR /app

# Install minimal system dependencies
# - ffmpeg: Required for audio processing (pydub)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user (OpenShift compatibility)
RUN useradd --create-home --shell /bin/bash --uid 1001 appuser \
    && chown -R appuser:appuser /app

# Copy and install API dependencies first (for Docker layer caching)
COPY api/requirements.txt ./api/
RUN pip install --no-cache-dir -r api/requirements.txt

# Copy the gaik package source
COPY src/ ./src/
COPY pyproject.toml ./

# Install gaik with only required extras (NO docling/torch)
# - transcriber: Whisper transcription via Azure/OpenAI
# - PyMuPDF: PDF parsing
# - python-docx: DOCX parsing
RUN pip install --no-cache-dir -e ".[transcriber]" PyMuPDF python-docx

# Copy API source code
COPY api/ ./api/

# Create workspace directory for transcriber
RUN mkdir -p /app/transcriber_workspace && chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Expose port
EXPOSE 8000

# Health check for Kubernetes
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# Run the application
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
