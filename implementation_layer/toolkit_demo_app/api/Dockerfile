# GAIK Demo API - Lightweight Production Dockerfile
# Optimized for CSC Rahti 2 (no GPU/torch)
# Build context: repository root

FROM python:3.12-slim

# Metadata
LABEL maintainer="GAIK Project"
LABEL description="GAIK Demo API Backend"
LABEL version="1.0.0"

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    tesseract-ocr \
    tesseract-ocr-fin \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies with uv (faster)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# Copy requirements first (layer caching)
COPY implementation_layer/toolkit_demo_app/api/requirements.txt .

# Install PyTorch CPU-only first (prevents CUDA download ~2GB)
RUN uv pip install --system --no-cache \
    --extra-index-url https://download.pytorch.org/whl/cpu \
    torch torchvision

# Install API dependencies. The local gaik package is installed from repository
# source below because the published PyPI wheel may lag new demo modules.
RUN uv pip install --system --no-cache -r requirements.txt

# Install gaik from this repository, including the Report Writer extras.
COPY pyproject.toml README.md LICENSE ./
COPY implementation_layer/src ./implementation_layer/src
RUN uv pip install --system --no-cache \
    ".[all-cpu,multimodal-parser,postgres-agent,multi-source-report-generator-agentic,multi-source-report-generator-docx]"

# Solution Wizard assets (SKILL.md, scripts, registries, templates). The wizard
# session runs the bundled claude CLI (shipped inside the claude-agent-sdk
# wheel) with cwd=WIZARD_DIR. Foundry credentials come from deployment env.
COPY implementation_layer/solution_wizard ./implementation_layer/solution_wizard
ENV WIZARD_DIR=/app/implementation_layer/solution_wizard

# Copy API application code
COPY implementation_layer/toolkit_demo_app/api/ .

# Copy example files for RAG demo
COPY implementation_layer/toolkit_demo_app/public/GAIK_Test_Document_Demo.pdf ./public/
COPY implementation_layer/toolkit_demo_app/public/example-index.json ./public/

# OpenShift arbitrary UID support
# CSC Rahti 2 assigns random UIDs but always GID=0 (root group)
# Create cache directory for Huggingface models
RUN useradd -u 1001 -g 0 -d /app -s /sbin/nologin appuser && \
    mkdir -p /app/.cache && \
    chgrp -R 0 /app && chmod -R g=u /app

# Set HOME and HF_HOME for Python/Huggingface libraries
ENV HOME=/app
ENV HF_HOME=/app/.cache

# Run as non-root user (OpenShift will assign arbitrary UID)
USER 1001

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
