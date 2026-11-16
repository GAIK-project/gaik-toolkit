# GAIK Demo API - Lightweight Production Dockerfile
# Optimized for CSC Rahti 2 (no GPU/torch)
# Build context: repository root

# Pinned by digest (python:3.12-slim, 3.12.16 when pinned); README "Pinned
# images and the API lock" says how to move it.
FROM python:3.12-slim@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b

# Metadata
LABEL maintainer="GAIK Project"
LABEL description="GAIK Demo API Backend"
LABEL version="1.0.0"

WORKDIR /app

# Install system dependencies
# pandoc: Report Writer DOCX export (pypandoc shells out to the binary)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    tesseract-ocr \
    tesseract-ocr-fin \
    pandoc \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies with uv (faster); uv:latest was 0.13.8 when pinned.
COPY --from=ghcr.io/astral-sh/uv:0.13.8@sha256:5cc1805e2426484abca4ad46ea783bab281fdb225fd82d8ce6d66a81254bac85 /uv /bin/uv

# Copy the lock first (layer caching)
COPY implementation_layer/toolkit_demo_app/api/requirements.lock .

# Install the API dependencies from the lock: every package pinned with its
# hashes, gaik at the published release requirements.txt names, and torch and
# torchvision as CPU builds from the PyTorch index (the lock names both
# indexes), so gaik[all-cpu] never pulls the ~2GB CUDA build. A file whose hash
# is not in the lock fails the build. scripts/lock_api_requirements.sh writes it.
RUN uv pip install --system --no-cache --require-hashes \
    --index-strategy unsafe-best-match \
    -r requirements.lock

# The first Solution Wizard's assets (SKILL.md, scripts, registries, templates).
# A wizard session runs the claude CLI that ships inside the claude-agent-sdk
# wheel, with cwd=WIZARD_DIR. Its model credentials come from the deployment.
COPY implementation_layer/solution_wizard ./implementation_layer/solution_wizard
ENV WIZARD_DIR=/app/implementation_layer/solution_wizard

# Copy API application code
COPY implementation_layer/toolkit_demo_app/api/ .

# Copy example files for RAG demo
COPY implementation_layer/toolkit_demo_app/public/rag-example/ ./public/rag-example/

# Report Writer v2 examples, at their repository paths: routers/report_writer_v2.py
# finds them by walking up from /app/routers, and the specs name their files by
# relative path. Only the files the specs name, not the dataset generator or the
# recording scripts. The multi_source_report_generator folder also gets
# report_config.json because the legacy routers/report_writer.py now finds this
# folder before /app/report_examples and reads its config from it.
COPY implementation_layer/examples/software_modules/report_writer/project_meeting/report_spec.json \
     ./implementation_layer/examples/software_modules/report_writer/project_meeting/
COPY implementation_layer/examples/software_modules/report_writer/house_condition_assessment/report_spec.json \
     implementation_layer/examples/software_modules/report_writer/house_condition_assessment/sample_report.docx \
     ./implementation_layer/examples/software_modules/report_writer/house_condition_assessment/
COPY implementation_layer/examples/software_modules/report_writer/house_condition_assessment/inputs \
     ./implementation_layer/examples/software_modules/report_writer/house_condition_assessment/inputs
COPY implementation_layer/examples/software_modules/multi_source_report_generator/sample_inputs \
     ./implementation_layer/examples/software_modules/multi_source_report_generator/sample_inputs
COPY implementation_layer/examples/software_modules/multi_source_report_generator/sample_report.md \
     implementation_layer/examples/software_modules/multi_source_report_generator/report_config.json \
     ./implementation_layer/examples/software_modules/multi_source_report_generator/

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
