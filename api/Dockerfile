# GAIK Toolkit API - Production Dockerfile
# Designed for CSC Rahti 2 (OpenShift/Kubernetes)

FROM python:3.11-slim

# Metadata
LABEL maintainer="GAIK Project"
LABEL description="GAIK Toolkit API for transcription and parsing"
LABEL version="1.0.0"

# Set working directory
WORKDIR /app

# Install system dependencies
# - ffmpeg: Required for audio processing (pydub)
# - gcc: Required for some Python packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user (OpenShift compatibility)
# OpenShift runs containers with arbitrary UIDs, so we use a flexible approach
RUN useradd --create-home --shell /bin/bash --uid 1001 appuser \
    && chown -R appuser:appuser /app

# Copy and install API dependencies first (for Docker layer caching)
COPY api/requirements.txt ./api/
RUN pip install --no-cache-dir -r api/requirements.txt

# Copy the gaik package source
COPY src/ ./src/
COPY pyproject.toml ./

# Install gaik package with all extras
RUN pip install --no-cache-dir -e ".[all]"

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
