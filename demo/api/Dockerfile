# GAIK Demo API - Lightweight Production Dockerfile
# Optimized for CSC Rahti 2 (no GPU/torch)

FROM python:3.12-slim

# Metadata
LABEL maintainer="GAIK Project"
LABEL description="GAIK Demo API Backend"
LABEL version="1.0.0"

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies with uv (faster)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# Copy requirements first (layer caching)
COPY requirements.txt .

# Install dependencies - use all-cpu extra (no torch/docling)
RUN uv pip install --system --no-cache -r requirements.txt && \
    uv pip install --system --no-cache gaik[all-cpu]

# Copy application code
COPY . .

# OpenShift arbitrary UID support
# CSC Rahti 2 assigns random UIDs but always GID=0 (root group)
RUN chgrp -R 0 /app && chmod -R g=u /app

# Run as non-root user (OpenShift will assign arbitrary UID)
USER 1001

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
