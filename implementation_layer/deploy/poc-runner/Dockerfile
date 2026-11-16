# wizard-v2-poc-runner — the image a sandbox PoC run executes in (S5-1 / #89,
# consumed by #91's SandboxRunner).
#
# Both containers in deploy/openshift/sandbox-job.yaml use this one image: the
# init container fetches and unzips the package (curl + python), the run
# container executes `python run_poc.py` in /workspace/poc.
#
# Dependencies are baked in, not installed per run. The Job sets
# readOnlyRootFilesystem: true and activeDeadlineSeconds: 600, so a
# `pip install -r requirements.txt` at run time would need a writable
# site-packages and would spend minutes of the run's own 10-minute budget —
# on every run, for packages that never change. Installing here also means the
# run needs no PyPI egress, which matters once the NetworkPolicy in #90 limits
# egress to the LLM endpoints.
FROM python:3.11-slim

# curl for the init container's fetch step, ffmpeg because pydub shells out to
# it and the audio use case (UC01) hands it a .wav/.mp3 — without it pydub only
# warns at import and then fails deep inside the transcriber, which reads to the
# user as "the PoC is broken". No build toolchain: every extra below must resolve
# to a wheel, and a missing wheel should fail this build loudly rather than be
# papered over with gcc.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Pin the toolkit the runs execute against. A generated PoC's requirements.txt
# asks for `gaik[extract]` and friends unversioned, so without a pin here two
# runs a week apart could use different toolkits — and the wizard's component
# registry is synced against one specific version (see AGENTS.md, gaik-sync).
# Bump this together with that sync, never on its own. 0.8.2 is the first release
# that ships gaik.software_modules.report_writer (and its extras): the wizard
# selects ReportWriter by default for multi-source report cases (UC04), so a
# runner older than this fails those PoCs on import. The guidance is validated
# against solution_wizard/gaik_validated_version.txt, and a test keeps this pin
# equal to it: on 0.8.2 a PoC written to that guidance failed on
# RunSettings(citations=...), which arrived in 0.8.3.
ARG GAIK_VERSION=0.9.1

# Only the extras the customer's five use cases actually import. `gaik[all-cpu]`
# was the obvious choice and the wrong one: it pulls classifier/RAG/Finnish-NLP
# extras whose dependency trees drag in the CUDA build of torch, and the image
# came out at 7.3 GB with 5.1 GB of GPU stack a sandbox that only calls HTTP APIs
# will never execute. That size is not just waste — a Job's
# activeDeadlineSeconds clock covers the image pull, so a fat image spends the
# run's own 10 minutes on download.
#
# The union below resolves to pydub, requests, anthropic, google-genai,
# google-auth, PyMuPDF and python-docx on top of gaik core. No torch.
#
# A PoC that selects a component outside this set (a classifier, a RAG
# workflow) fails on import. That is the intended trade: the acceptance
# criterion is those five use cases, and adding an extra here is a one-line
# change plus a rebuild. The smoke test below is what makes such a miss legible.
# multimodal-parser is here because gaik.software_components.vision_extractor
# imports the multimodal parser at module import time (markdown-it-py,
# anthropic), and the vision-extract extra alone does not pull those in: the
# first invoice PoC on s4 died on `No module named 'markdown_it'` before any
# model call. The smoke test below imports vision_extractor for that reason.
# tabular-agent is here because the registry offers TabularAgent for questions
# over a spreadsheet or CSV: without it every run of such a PoC ended in
# "TabularAgent requires 'duckdb'" and Gate 3 could not be passed. It adds
# duckdb and sqlglot (openpyxl is already here), no torch.
ARG GAIK_EXTRAS="extract,transcriber,enhance-transcript,audio-to-structured-data,llm-judge,vision-extract,multimodal-parser,documents-to-structured-data-cpu,evaluators,report-writer,vector-store,source-tracing,fields-to-docx,tabular-agent"

# pyyaml is the scaffolded run_poc.py's own import (`import yaml`) and is not a
# gaik dependency; pydantic and python-dotenv arrive with gaik core. reportlab is
# the renderer of the scaffolded pdf_report.py (a PoC whose output types include
# pdf imports it); without it every such run prints "PDF report generation
# failed: No module named 'reportlab'".
# pandas is imported by agent-written run_poc.py files that compute figures from
# a spreadsheet or CSV (UC04's KPI step). No gaik extra in 0.8.2 brings it in
# (spreadsheet-parser requires only openpyxl), and a sandbox run installs nothing,
# so it is named here, in the runner and in the api image alike.
# Each is pinned to one exact version, the same as in the api image, so the api's
# package check looks a PoC's imports up against what the run uses. A test
# (test_deploy_instances) keeps the two lists and their versions equal.
RUN pip install --no-cache-dir "gaik[${GAIK_EXTRAS}]==${GAIK_VERSION}" "pyyaml==6.0.3" "reportlab==5.1.0" "pandas==3.1.1"

# Fail the build, not the run, if the image cannot import what the five use
# cases import. Without this a missing extra surfaces as an ImportError inside a
# sandbox Job, where the user sees it as "the PoC is broken".
RUN python - <<'PY'
import importlib

for module in (
    "gaik.software_modules.audio_to_structured_data",
    "gaik.software_modules.documents_to_structured_data",
    "gaik.software_modules.report_writer",
    "gaik.software_modules.RAG_workflow",
    "gaik.software_components.extractor",
    "gaik.software_components.vision_extractor",
    "gaik.software_components.parsers.multimodal_parser",
    "gaik.software_components.transcriber",
    "gaik.software_components.validators",
    "gaik.software_components.source_tracing",
    "gaik.software_components.tabular_agent",
    # vector-store: gaik imports chromadb inside VectorStore.__init__, at the first
    # call, so only an explicit import here catches a runner without it (#268).
    "chromadb",
    "yaml",
    "reportlab",
    "pandas",
    "pydantic",
    "dotenv",
):
    importlib.import_module(module)
print("import smoke test ok")
PY

# The Job requires runAsNonRoot and OpenShift assigns an arbitrary UID from the
# project's range, so nothing may depend on this specific uid — only on group 0,
# which that arbitrary UID always belongs to.
RUN mkdir -p /workspace && chown -R 1001:0 /workspace && chmod -R g=u /workspace
USER 1001

# The root filesystem is read-only at run time: no .pyc writes, and HOME points
# at the tmp emptyDir the Job mounts (the manifest sets HOME too — this keeps
# `docker run` behaving the same).
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOME=/tmp

WORKDIR /workspace

# The manifest supplies the real command (`python run_poc.py` in
# /workspace/poc). This default makes a bare `docker run` report the image's
# toolkit version instead of dropping into a shell.
CMD ["python", "-c", "import importlib.metadata as m; print('gaik', m.version('gaik'))"]
