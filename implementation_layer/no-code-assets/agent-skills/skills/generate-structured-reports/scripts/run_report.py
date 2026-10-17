#!/usr/bin/env python3
"""Run the gaik ReportWriter pipeline one checked stage at a time.

  python run_report.py preflight          --spec SPEC --workspace WS [--provider P]
  python run_report.py propose-spec       --spec SPEC --workspace WS --out FILE [--provider P]
                                          [--structure FILE] [--reset-models]
  python run_report.py apply-spec         --spec SPEC --workspace WS --proposal FILE
                                          [--provider P] [--check]
  python run_report.py set-sections       --spec SPEC --workspace WS --structure FILE
  python run_report.py normalize          --spec SPEC --workspace WS [--provider P] [--replace]
  python run_report.py curate             --spec SPEC --workspace WS [--provider P] [--replace]
  python run_report.py validate-knowledge --spec SPEC --workspace WS
  python run_report.py synthesize         --spec SPEC --workspace WS [--provider P] [--replace]
  python run_report.py rebuild            --spec SPEC --workspace WS
  python run_report.py update-sample      --spec SPEC --workspace WS [--provider P]

Every command takes --json to print one JSON result object on stdout; progress always goes to
stderr. Exit codes: 0 done (warnings may remain), 2 invalid input, 3 invalid evidence,
4 a missing dependency or configuration, 5 a stage failed.

This is a thin layer over gaik.software_modules.report_writer. It adds checks before paid
calls, keeps the diagnostics the module does not save, and records what each stage was built
from. It never calls ReportWriter.run(), so the single-call baseline cannot be reached.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import re
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

EXIT_OK, EXIT_INPUT, EXIT_EVIDENCE, EXIT_DEPENDENCY, EXIT_STAGE = 0, 2, 3, 4, 5

# The source types SourceNormalizer converts. Its own table is private (_TYPES), so this is a
# copy; the skill's tests compare the two and fail when gaik adds or drops a type.
AUDIO = {".mp3", ".wav", ".m4a", ".ogg", ".flac", ".webm", ".mp4", ".mpeg", ".mpga"}
IMAGE = {".png", ".jpg", ".jpeg", ".webp"}
SOURCE_TYPES = {
    ".pdf": "pdf",
    ".docx": "docx",
    ".xlsx": "spreadsheet",
    ".csv": "spreadsheet",
    ".txt": "text",
    ".md": "text",
    **dict.fromkeys(AUDIO, "audio"),
    **dict.fromkeys(IMAGE, "image"),
}
# A sample report must convert locally, with no model call (reference: review-and-resume).
SAMPLE_TYPES = {".docx", ".md", ".txt", ".pdf"}
# Providers whose config can transcribe recordings in a ReportWriter run.
AUDIO_PROVIDERS = {"openai", "azure"}
# A PDF page with some text but fewer non-space characters than this may be a scan with a
# page number on it: warned about, never refused. Only a page with no text is textless.
SPARSE_PAGE_CHARS = 20
VAGUE_ITEMS = {
    "other", "misc", "miscellaneous", "details", "detail", "information", "info", "notes",
    "general", "etc", "stuff", "everything", "various", "n/a", "data", "comments",
}  # fmt: skip
SECRET_KEYS = ("key", "token", "secret", "password", "endpoint", "base_url", "url")

STAGES = ("normalize", "curate", "synthesize")
STAGE_DIRS = {"normalize": "normalized", "curate": "knowledge", "synthesize": "report"}


class HelperError(Exception):
    """An error with an exit code and a message that is safe to print and save."""

    def __init__(self, code: int, category: str, message: str, result: dict | None = None):
        super().__init__(message)
        self.code, self.category, self.message = code, category, message
        self.result = result or {}


# ---------------------------------------------------------------------------
# Small utilities
# ---------------------------------------------------------------------------


def progress(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_json(value: Any) -> str:
    text = json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def read_json(path: Path, default: Any = None) -> Any:
    if not path.is_file():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    tmp.replace(path)


def redact(text: str, config: dict | None) -> str:
    """Remove secret values of the config from a message, and shorten it."""
    text = str(text)
    for key, value in (config or {}).items():
        if (
            isinstance(value, str)
            and len(value) >= 6
            and any(s in key.lower() for s in SECRET_KEYS)
        ):
            text = text.replace(value, "***")
    text = re.sub(r"(?i)(api[-_]?key|authorization|bearer)\s*[:=]?\s*\S+", r"\1 ***", text)
    return text if len(text) <= 600 else text[:600] + " ..."


def gaik_info() -> dict:
    """The installed gaik version, and whether it is an editable source checkout."""
    from importlib import metadata

    try:
        dist = metadata.distribution("gaik")
    except metadata.PackageNotFoundError:
        return {"version": None, "editable": None}
    editable = False
    direct = dist.read_text("direct_url.json")
    if direct:
        editable = bool(json.loads(direct).get("dir_info", {}).get("editable"))
    return {"version": dist.version, "editable": editable}


def import_report_writer():
    try:
        from gaik.software_modules import report_writer
    except ImportError as exc:
        raise HelperError(
            EXIT_DEPENDENCY,
            "missing-dependency",
            "gaik with the report writer is not installed: "
            f'pip install "gaik[report-writer]" ({exc})',
        ) from exc
    return report_writer


# The two functions below are the seams the skill's tests replace.


# The provider and models of a run when nothing else names them. A model name only means
# something to the provider it is sent to, so the defaults are per provider family; a provider
# with no entry here (openai_compatible, aitta, litellm) uses its own configured model.
DEFAULT_PROVIDER = "openai"
_OPENAI_MODELS = {"curator": "gpt-6-luna", "writer": "gpt-6-luna", "reviewer": "gpt-6.1-sol"}
_ANTHROPIC_MODELS = {
    "curator": "claude-sonnet-5",
    "writer": "claude-sonnet-5",
    "reviewer": "claude-sonnet-5-5",
}
_GOOGLE_MODELS = {
    "curator": "gemini-3.6-flash",
    "writer": "gemini-3.6-flash",
    "reviewer": "gemini-3.8-flash",
}
DEFAULT_MODELS = {
    "openai": _OPENAI_MODELS,
    "azure": _OPENAI_MODELS,
    "anthropic": _ANTHROPIC_MODELS,
    "anthropic_foundry": _ANTHROPIC_MODELS,
    "google": _GOOGLE_MODELS,
    "vertex": _GOOGLE_MODELS,
}
MODEL_ENV = {
    "curator": "GAIK_REPORT_CURATOR_MODEL",
    "writer": "GAIK_REPORT_WRITER_MODEL",
    "reviewer": "GAIK_REPORT_REVIEWER_MODEL",
}

# Providers whose client needs a package that the report-writer extra does not install:
# provider -> (module to import, gaik extra that installs it).
PROVIDER_PACKAGES = {
    "anthropic": ("anthropic", "llm-anthropic"),
    "anthropic_foundry": ("anthropic", "llm-anthropic"),
    "google": ("google.genai", "llm-google"),
    "vertex": ("google.genai", "llm-google"),
    "litellm": ("litellm", "llm-litellm"),
}


def package_available(module: str) -> bool:
    import importlib.util

    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ValueError):
        return False


def install_provider_extra(provider: str, module: str, extra: str) -> None:
    """Install the gaik extra that provides a provider's package, then check that it imports.

    Only a fixed requirement from PROVIDER_PACKAGES is ever installed, never text from the user
    or the spec. pip's output goes to stderr so that --json keeps stdout clean.
    """
    import shutil
    import subprocess

    requirement = f"gaik[{extra}]"
    commands = [[sys.executable, "-m", "pip", "install", requirement]]
    if shutil.which("uv"):
        commands.append(["uv", "pip", "install", "--python", sys.executable, requirement])
    print(f"The {provider} provider needs the {module} package; installing {requirement}", file=sys.stderr)
    for command in commands:
        code = subprocess.call(command, stdout=sys.stderr, stderr=sys.stderr)
        if code == 0:
            import importlib

            importlib.invalidate_caches()
            if package_available(module):
                return
    raise HelperError(
        EXIT_DEPENDENCY,
        "provider-package",
        f"The {provider} provider needs the {module} package and installing it failed. "
        f'Install it yourself: pip install "{requirement}"',
    )


def load_config(provider: str | None) -> dict:
    """The runtime LLM config. Credentials come from the environment, never from the spec."""
    from gaik.software_components.llm import get_llm_config

    name = provider or os.environ.get("LLM_PROVIDER", "").strip() or DEFAULT_PROVIDER
    try:
        config = get_llm_config(name)
    except ValueError as exc:
        raise HelperError(EXIT_DEPENDENCY, "provider-config", redact(exc, None)) from exc
    needs = PROVIDER_PACKAGES.get(str(config.get("provider")))
    if needs and not package_available(needs[0]):
        install_provider_extra(str(config["provider"]), *needs)
    return config


def apply_model_defaults(spec, config: dict) -> None:
    """Fill the curator, writer and reviewer models the spec leaves open, in memory only.

    Order: the spec's `models`, then the GAIK_REPORT_<STEP>_MODEL variable, then the default
    for the provider, else the provider's configured model. The spec file is never rewritten.
    """
    defaults = DEFAULT_MODELS.get(str(config.get("provider")), {})
    for step, variable in MODEL_ENV.items():
        if getattr(spec.models, step) is not None:
            continue
        value = os.environ.get(variable, "").strip()
        if not value:
            value = defaults.get(step, "")
        if value:
            setattr(spec.models, step, value)


def make_writer(config: dict):
    return import_report_writer().ReportWriter(config)


# ---------------------------------------------------------------------------
# Spec, sources and section checks
# ---------------------------------------------------------------------------


def load_spec(path: Path):
    rw = import_report_writer()
    if not path.is_file():
        raise HelperError(EXIT_INPUT, "spec", f"{path}: no such spec file")
    try:
        return rw.ReportSpec.load(path)
    except Exception as exc:  # pydantic.ValidationError, ValueError, JSON errors
        raise HelperError(EXIT_INPUT, "spec", f"{path.name}: {exc}") from exc


def source_files(spec) -> list[tuple[str, Path]]:
    return [(cls, Path(p)) for cls, paths in spec.sources.items() for p in paths]


def pdf_page_text(path: Path) -> tuple[int, list[int], list[int]]:
    """Return (page count, pages with no text at all, pages with only a little text), 1-based.

    Only a PDF whose every page has no text is a scan the normalizer cannot read; a short
    document such as a one-line receipt is valid.
    """
    import pymupdf

    with pymupdf.open(path) as doc:
        counts = [len("".join(page.get_text().split())) for page in doc]
    empty = [i + 1 for i, n in enumerate(counts) if n == 0]
    sparse = [i + 1 for i, n in enumerate(counts) if 0 < n < SPARSE_PAGE_CHARS]
    return len(counts), empty, sparse


def find_cycle(sections) -> list[str] | None:
    """Return one dependency cycle as a list of ids, or None."""
    deps = {s.id: list(s.depends_on) for s in sections}
    state: dict[str, int] = {}
    stack: list[str] = []

    def visit(node: str) -> list[str] | None:
        state[node] = 1
        stack.append(node)
        for nxt in deps.get(node, []):
            if state.get(nxt) == 1:
                return stack[stack.index(nxt) :] + [nxt]
            if nxt in deps and state.get(nxt) is None:
                found = visit(nxt)
                if found:
                    return found
        stack.pop()
        state[node] = 2
        return None

    for node in deps:
        if state.get(node) is None:
            found = visit(node)
            if found:
                return found
    return None


def section_problems(spec) -> tuple[list[str], list[str]]:
    errors, warnings = [], []
    cycle = find_cycle(spec.sections)
    if cycle:
        errors.append("Section dependencies form a cycle: " + " -> ".join(cycle))
    if not [s for s in spec.sections if not s.depends_on]:
        errors.append(
            "Every section depends on other sections: at least one section must be written from "
            "the sources"
        )
    for s in spec.sections:
        for item in s.required_items:
            if len(item.strip()) < 3 or item.strip().lower() in VAGUE_ITEMS:
                warnings.append(
                    f"Section {s.id!r}: required item {item!r} is too vague to check against the "
                    "sources; name the fact it needs"
                )
    if not spec.instructions.strip():
        warnings.append(
            "The report instructions are empty: state the source hierarchy, or that there is none, "
            "so conflicts are not decided by the curator's own examples"
        )
    return errors, warnings


def pandoc_problem() -> str | None:
    try:
        import pypandoc
    except ImportError:
        return "the pypandoc package is not installed"
    try:
        pypandoc.get_pandoc_version()
    except OSError:
        return "the Pandoc program is not installed or not on PATH"
    return None


# What the pipeline deletes or overwrites in a workspace. An input inside any of them would be
# lost: normalize, curate and synthesize delete their whole folder before writing.
OWNED_DIRS = ("normalized", "knowledge", "report", "diagnostics")
OWNED_FILES = ("sample_report.md",)


def _real(path: Path) -> Path:
    """The path with links and junctions resolved; case-folded where the file system is."""
    return Path(os.path.normcase(path.resolve()))


def path_collisions(spec, spec_path: Path | None, ws: Path | None) -> list[str]:
    """Inputs that sit where a stage would delete or overwrite them, and linked stage folders.

    Both sides are resolved: a stage folder that is a link or junction would make the stage
    delete or overwrite whatever it points to, which a comparison of names would miss.
    """
    if ws is None:
        return []
    root = _real(ws)
    errors, owned = [], []
    for name in OWNED_DIRS + OWNED_FILES:
        real = _real(ws / name)
        if real != root / os.path.normcase(name):
            errors.append(
                f"workspace/{name} is a link to {(ws / name).resolve()}; the pipeline would delete "
                "or overwrite what it points to. Replace it with a plain folder, or use a fresh "
                "workspace"
            )
        owned.append((name, real))
    inputs = [("source", Path(p)) for _, p in source_files(spec)]
    if spec.sample_report is not None:
        inputs.append(("sample report", Path(spec.sample_report)))
    if spec_path is not None:
        inputs.append(("spec", spec_path))
    for role, path in inputs:
        resolved = _real(path)
        for name, place in owned:
            if resolved == place or resolved.is_relative_to(place):
                errors.append(
                    f"The {role} {path.name} is inside workspace/{name} (or what it links to), "
                    "which the pipeline deletes or overwrites; move it out of the workspace's "
                    "stage folders"
                )
                break
    return errors


def preflight_checks(
    spec,
    config: dict | None,
    *,
    docx_blocks: bool = True,
    spec_path: Path | None = None,
    workspace: Path | None = None,
) -> dict:
    """Checks that are free and catch what the module catches late or never."""
    errors, warnings, inventory = [], [], []
    errors += path_collisions(spec, spec_path, workspace)
    seen: dict[str, Path] = {}
    has = {"audio": False, "image": False}

    for cls, path in source_files(spec):
        entry = {"file": path.name, "class": cls}
        inventory.append(entry)
        suffix = path.suffix.lower()
        if not path.is_file():
            errors.append(f"{path}: source file not found")
            continue
        if suffix not in SOURCE_TYPES:
            errors.append(
                f"{path.name}: {suffix or 'no extension'} is not a supported source type; convert "
                "it first (PPTX, DOC, XLS and TIFF are not read)"
            )
            continue
        kind = entry["type"] = SOURCE_TYPES[suffix]
        if path.name in seen:
            errors.append(
                f"{path.name}: listed more than once ({seen[path.name]} and {path}); the file name "
                "is the citation key, so every source needs a unique name"
            )
        seen[path.name] = path
        if kind in has:
            has[kind] = True
        if kind == "pdf":
            pages, empty, sparse = pdf_page_text(path)
            entry["pages"] = pages
            if pages and len(empty) == pages:
                errors.append(
                    f"{path.name}: no page has a text layer (a scan); OCR it first or leave it out"
                )
            elif empty:
                entry["pages_without_text"] = empty
                warnings.append(
                    f"{path.name}: pages {empty} have no text layer, so their content will be "
                    "missing from the report"
                )
            if sparse and len(empty) < pages:
                entry["pages_with_little_text"] = sparse
                warnings.append(
                    f"{path.name}: pages {sparse} have very little text; if they are scans with "
                    "only a page number or a stamp, their content will be missing"
                )
        if kind in ("pdf", "docx"):
            entry["note"] = "figures and images inside the document are not read"

    if has["image"]:
        warnings.append(
            "Image sources are described by the vision model; check that it accepts images"
        )
    if has["audio"] and config is None:
        warnings.append(
            "Recordings need an OpenAI or Azure OpenAI provider; pass --provider to check it"
        )
    if has["audio"] and config is not None and config.get("provider") not in AUDIO_PROVIDERS:
        errors.append(
            f"Recordings need an OpenAI or Azure OpenAI provider; this run uses "
            f"{config.get('provider')!r}. Use one of those, or give a transcript instead"
        )

    if spec.sample_report is not None:
        sample = Path(spec.sample_report)
        if not sample.is_file():
            errors.append(f"{sample}: sample report not found")
        elif sample.suffix.lower() not in SAMPLE_TYPES:
            errors.append(
                f"{sample.name}: a sample report must be DOCX, Markdown, text or a text-based PDF "
                "so it converts without a model call"
            )
        elif sample.suffix.lower() == ".pdf":
            pages, empty, _ = pdf_page_text(sample)
            if pages and len(empty) == pages:
                errors.append(f"{sample.name}: the sample PDF has no text layer")

    sec_errors, sec_warnings = section_problems(spec)
    errors += sec_errors
    warnings += sec_warnings

    if spec.settings.docx:
        problem = pandoc_problem()
        if problem:
            message = (
                f"Word output is on but {problem}. Install Pandoc (scripts/install_pandoc.py, only "
                "after the user agrees), or set settings.docx to false and deliver Markdown only"
            )
            (errors if docx_blocks else warnings).append(message)

    return {
        "errors": errors,
        "warnings": warnings,
        "sources": inventory,
        "uses": [k for k, v in has.items() if v],
    }


# ---------------------------------------------------------------------------
# The per-stage run record (reference: review-and-resume)
# ---------------------------------------------------------------------------


def stage_inputs(spec, stage: str) -> dict:
    """Hashes of what one stage reads. Only fields that change its output are included.

    Sources are keyed by file name, never by path: the name is unique (it is the citation key),
    and a path changes when the run folder is moved or copied while the inputs stay the same.
    """
    # The curator, writer and reviewer models are not hashed here: the helper fills them in from
    # the environment and its defaults, so the spec's own values are not what a stage ran with.
    # effective_models records and compares the names each stage really used.
    dump = spec.model_dump(mode="json")
    if stage == "normalize":
        return {
            "sources": {
                p.name: sha256_file(p) if p.is_file() else None for _, p in source_files(spec)
            },
            "spec": sha256_json(
                {
                    "sources": {
                        cls: sorted(Path(p).name for p in paths)
                        for cls, paths in spec.sources.items()
                    },
                    "vision": dump["models"]["vision"],
                    "transcription": dump["models"]["transcription"],
                    "language": dump["settings"]["transcription_language"],
                }
            ),
        }
    if stage == "curate":
        return {
            "spec": sha256_json(
                {
                    "sections": dump["sections"],
                    "instructions": dump["instructions"],
                    "options": dump["settings"]["curator"],
                }
            )
        }
    settings = dump["settings"]
    return {
        "spec": sha256_json(
            {
                "title": dump["title"],
                "language": dump["language"],
                "sections": dump["sections"],
                "instructions": dump["instructions"],
                # the sample's contents are tracked by its conversion record
                "sample_report": Path(spec.sample_report).name if spec.sample_report else None,
                "review": [settings["review_attempts"], settings["strict_review"]],
                "citations": settings["citations"],
                "options": [settings["writer"], settings["reviewer"]],
            }
        )
    }


def effective_models(spec, config: dict, stage: str, uses: list[str] | None = None) -> dict:
    """The provider and model names a stage runs with. Names only: never keys or endpoints."""
    base = config.get("model") or "component default"
    models = spec.models
    if stage == "normalize":
        uses = uses or []
        return {
            "provider": config.get("provider"),
            "vision": (models.vision or base) if "image" in uses else "not used",
            "transcription": (
                models.transcription or config.get("transcription_model") or "component default"
            )
            if "audio" in uses
            else "not used",
        }
    if stage == "curate":
        return {"provider": config.get("provider"), "curator": models.curator or base}
    return {
        "provider": config.get("provider"),
        "writer": models.writer or base,
        "reviewer": models.reviewer or base,
    }


def record_path(ws: Path) -> Path:
    return ws / "diagnostics" / "run_record.json"


def load_record(ws: Path) -> dict:
    return read_json(record_path(ws), {"stages": {}, "sample": None})


def chain_findings(spec, ws: Path, config: dict | None, uses: list[str] | None = None) -> dict:
    """What no longer matches, per stage. An empty dict means every recorded stage is current."""
    record = load_record(ws)
    stages = record.get("stages", {})
    findings: dict[str, list[str]] = {}

    def add(stage: str, message: str) -> None:
        findings.setdefault(stage, []).append(message)

    for stage in STAGES:
        entry = stages.get(stage)
        if not entry:
            continue
        current = stage_inputs(spec, stage)
        if stage == "normalize":
            for name, digest in entry["inputs"]["sources"].items():
                now_digest = current["sources"].get(name)
                if now_digest is None:
                    add(stage, f"source {name} is no longer in the spec or on disk")
                elif now_digest != digest:
                    add(stage, f"source {name} changed")
            for name in current["sources"]:
                if name not in entry["inputs"]["sources"]:
                    add(stage, f"source {name} was added")
        if current["spec"] != entry["inputs"]["spec"]:
            add(stage, "the spec fields this stage reads changed")
        if config is not None:
            now_models = effective_models(spec, config, stage, uses or entry.get("uses"))
            if now_models != entry.get("models"):
                add(stage, f"provider or model changed: {entry.get('models')} -> {now_models}")
        upstream = {"curate": "normalize", "synthesize": "curate"}.get(stage)
        if upstream:
            up = stages.get(upstream)
            if not up or entry.get("upstream") != up.get("run_id"):
                add(stage, f"it was built from an earlier {upstream} run")
            elif upstream in findings:
                add(stage, f"it was built on a {upstream} run that is no longer current")

    if "synthesize" in stages:
        sample = record.get("sample")
        used = stages["synthesize"].get("sample_conversion")
        if spec.sample_report is None:
            if used:
                add("synthesize", "the spec no longer has a sample report")
        else:
            path = Path(spec.sample_report)
            if not sample or sample.get("conversion_id") != used:
                add("synthesize", "it used an earlier conversion of the sample report")
            elif path.is_file() and sha256_file(path) != sample.get("sha256"):
                add("synthesize", "the sample report file changed since it was converted")
    return findings


def write_stage_record(spec, ws: Path, stage: str, config: dict, extra: dict) -> dict:
    record = load_record(ws)
    stages = record.setdefault("stages", {})
    findings = chain_findings(spec, ws, config)
    upstream = {"curate": "normalize", "synthesize": "curate"}.get(stage)
    inherited = []
    for up_stage in STAGES[: STAGES.index(stage)]:
        inherited += [f"{up_stage}: {m}" for m in findings.get(up_stage, [])]
    entry = {
        "run_id": uuid.uuid4().hex[:12],
        "time": now(),
        "inputs": stage_inputs(spec, stage),
        "models": effective_models(spec, config, stage, extra.get("uses")),
        "warnings": inherited,
        **extra,
    }
    if upstream:
        entry["upstream"] = stages.get(upstream, {}).get("run_id")
    stages[stage] = entry
    record["gaik"] = gaik_info()
    write_json(record_path(ws), record)
    return entry


def write_sample_record(ws: Path, sample: Path | None) -> str | None:
    record = load_record(ws)
    if sample is None:
        record["sample"] = None
        conversion = None
    else:
        conversion = uuid.uuid4().hex[:12]
        record["sample"] = {
            "conversion_id": conversion,
            "file": sample.name,
            "sha256": sha256_file(sample),
            "time": now(),
        }
    write_json(record_path(ws), record)
    return conversion


def stale_summary(findings: dict) -> list[str]:
    return [f"{stage}: {m}" for stage in STAGES for m in findings.get(stage, [])]


# ---------------------------------------------------------------------------
# Knowledge checks the library does not make
# ---------------------------------------------------------------------------


def knowledge_problems(ws: Path) -> tuple[list[str], dict]:
    rw = import_report_writer()
    try:
        sources = rw.NormalizedSources.load(ws / "normalized")
    except FileNotFoundError as exc:
        raise HelperError(EXIT_INPUT, "missing-stage", f"Run normalize first ({exc})") from exc
    try:
        knowledge = rw.KnowledgeBase.load(ws / "knowledge")
    except FileNotFoundError as exc:
        raise HelperError(EXIT_INPUT, "missing-stage", f"Run curate first ({exc})") from exc
    except Exception as exc:  # a malformed edit fails model validation
        return [f"A knowledge file does not match the model: {exc}"], {}

    problems = []
    classes = {s.file: s.source_class for s in sources.sources}
    for unit in knowledge.verify_quotes(sources):
        problems.append(
            f"{unit.id}: quote not found in {unit.source.file!r}: {unit.quote[:120]!r}"
            if unit.source.file in classes
            else f"{unit.id}: cites {unit.source.file!r}, which is not a source"
        )
    for section in knowledge.sections:
        ids = [u.id for u in section.units]
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        if dupes:
            problems.append(f"{section.section_id}: duplicate fact-unit ids {dupes}")
        for conflict in section.conflicts:
            unknown = [i for i in conflict.unit_ids if i not in ids]
            if unknown:
                problems.append(
                    f"{section.section_id}: conflict {conflict.topic!r} refers to unknown units "
                    f"{unknown}"
                )
        for unit in section.units:
            if unit.source.file in classes and unit.source_class != classes[unit.source.file]:
                problems.append(
                    f"{unit.id}: source_class {unit.source_class!r} does not match the class of "
                    f"{unit.source.file!r} ({classes[unit.source.file]!r})"
                )
    summary = {
        s.section_id: {
            "units": len(s.units),
            "missing": s.missing,
            "unresolved_conflicts": [c.topic for c in s.conflicts if c.status == "unresolved"],
            "resolved_conflicts": [c.topic for c in s.conflicts if c.status == "resolved"],
        }
        for s in knowledge.sections
    }
    return problems, summary


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def guard_replace(ws: Path, stage: str, replace: bool) -> None:
    folder = ws / STAGE_DIRS[stage]
    if folder.exists() and any(folder.iterdir()) and not replace:
        raise HelperError(
            EXIT_INPUT,
            "would-replace",
            f"{folder} exists and {stage} replaces it. Rerun with --replace once the user has "
            "agreed, or use a fresh workspace",
        )


def run_stage(stage: str, call, config: dict):
    try:
        return call()
    except HelperError:
        raise
    except Exception as exc:
        raise HelperError(
            EXIT_STAGE, f"{stage}-failed", f"{type(exc).__name__}: {redact(exc, config)}"
        ) from exc


def cmd_preflight(args) -> dict:
    spec = load_spec(args.spec)
    config = (
        load_config(args.provider) if args.provider is not None or args.check_provider else None
    )
    if config is not None:
        apply_model_defaults(spec, config)
    ws = args.workspace
    result = preflight_checks(spec, config, spec_path=args.spec, workspace=ws)
    result["gaik"] = gaik_info()
    result["existing_stages"] = [s for s in STAGES if (ws / STAGE_DIRS[s]).exists()]
    if config is not None:
        result["models"] = {s: effective_models(spec, config, s, result["uses"]) for s in STAGES}
    result["stale"] = stale_summary(chain_findings(spec, ws, config, result["uses"]))
    if result["errors"]:
        raise HelperError(EXIT_INPUT, "preflight", "; ".join(result["errors"]), result)
    return result


def checked(spec, config, args, *, docx_blocks: bool = False) -> dict:
    """Preflight inside a stage command: stop before any paid call if it fails.

    A missing Pandoc stops only synthesis; normalization and curation produce no Word file.
    """
    result = preflight_checks(
        spec, config, docx_blocks=docx_blocks, spec_path=args.spec, workspace=args.workspace
    )
    if result["errors"]:
        raise HelperError(EXIT_INPUT, "preflight", "; ".join(result["errors"]), result)
    return result


def stop_on_collision(spec, args) -> None:
    errors = path_collisions(spec, args.spec, args.workspace)
    if errors:
        raise HelperError(EXIT_INPUT, "path-collision", "; ".join(errors), {"errors": errors})


def cmd_normalize(args) -> dict:
    spec = load_spec(args.spec)
    config = load_config(args.provider)
    apply_model_defaults(spec, config)
    pre = checked(spec, config, args)
    ws = args.workspace
    guard_replace(ws, "normalize", args.replace)
    writer = make_writer(config)
    sources = run_stage(
        "normalize", lambda: writer.normalize(spec, ws, progress_callback=progress), config
    )
    converted = [
        {
            "id": s.id,
            "file": s.file,
            "class": s.source_class,
            "type": s.source_type,
            "tool": s.tool,
            "characters": len(s.text),
        }
        for s in sources.sources
    ]
    empty = [c["file"] for c in converted if not c["characters"]]
    diagnostics = {
        "time": now(),
        "usage": dict(sources.usage),
        "sources": converted,
        "warnings": pre["warnings"] + [f"{f}: converted to empty text" for f in empty],
        "sample_updates": [],
    }
    write_json(ws / "diagnostics" / "normalization.json", diagnostics)
    sample = Path(spec.sample_report) if spec.sample_report else None
    conversion = write_sample_record(ws, sample)
    entry = write_stage_record(
        spec, ws, "normalize", config, {"uses": pre["uses"], "sample_conversion": conversion}
    )
    return {"stage": "normalize", "run_id": entry["run_id"], **diagnostics}


def cmd_curate(args) -> dict:
    spec = load_spec(args.spec)
    config = load_config(args.provider)
    apply_model_defaults(spec, config)
    checked(spec, config, args)
    ws = args.workspace
    if not (ws / "normalized" / "sources.json").is_file():
        raise HelperError(EXIT_INPUT, "missing-stage", "Run normalize first")
    findings = chain_findings(spec, ws, config)
    guard_replace(ws, "curate", args.replace)
    writer = make_writer(config)
    knowledge = run_stage(
        "curate", lambda: writer.curate(spec, ws, progress_callback=progress), config
    )
    # dropped and usage are not saved by KnowledgeBase.save(): keep them now or lose them.
    diagnostics = {
        "time": now(),
        "usage": dict(knowledge.usage),
        "dropped": [d.model_dump() for d in knowledge.dropped],
        "sections": {
            s.section_id: {
                "units": len(s.units),
                "missing": s.missing,
                "unresolved_conflicts": [
                    {"topic": c.topic, "description": c.description}
                    for c in s.conflicts
                    if c.status == "unresolved"
                ],
                "resolved_conflicts": [c.topic for c in s.conflicts if c.status == "resolved"],
            }
            for s in knowledge.sections
        },
    }
    write_json(ws / "diagnostics" / "curation.json", diagnostics)
    entry = write_stage_record(spec, ws, "curate", config, {})
    return {
        "stage": "curate",
        "run_id": entry["run_id"],
        "stale_before_run": stale_summary(findings),
        **diagnostics,
    }


def cmd_validate_knowledge(args) -> dict:
    load_spec(args.spec)
    problems, summary = knowledge_problems(args.workspace)
    result = {"problems": problems, "sections": summary}
    if problems:
        raise HelperError(
            EXIT_EVIDENCE,
            "invalid-knowledge",
            f"{len(problems)} problem(s) in the knowledge files",
            result,
        )
    return result


def export_docx(writer, spec, ws: Path, config: dict | None) -> dict:
    """Word export through rebuild(), recorded apart from synthesis."""
    if not spec.settings.docx:
        return {"status": "off"}
    try:
        writer.rebuild(spec, ws)
    except Exception as exc:
        (ws / "report" / "report.docx").unlink(missing_ok=True)
        return {"status": "failed", "reason": f"{type(exc).__name__}: {redact(exc, config)}"}
    return {"status": "ok", "path": str(ws / "report" / "report.docx")}


def report_summary(report) -> dict:
    unresolved = {
        e.section_id: [{"search": x.search[:120], "reason": x.reason} for x in e.unresolved]
        for e in report.review_log
        if e.unresolved
    }
    markdown = report.markdown
    return {
        "sections": [s.id for s in report.sections],
        "missing_markers": markdown.count("(missing:"),
        "unresolved_review_edits": unresolved,
        "applied_review_edits": sum(len(e.applied) for e in report.review_log),
    }


def cmd_synthesize(args) -> dict:
    spec = load_spec(args.spec)
    config = load_config(args.provider)
    apply_model_defaults(spec, config)
    checked(spec, config, args, docx_blocks=True)
    ws = args.workspace
    problems, _ = knowledge_problems(ws)
    if problems:
        raise HelperError(
            EXIT_EVIDENCE,
            "invalid-knowledge",
            "Fix the knowledge files before writing: " + "; ".join(problems[:5]),
            {"problems": problems},
        )
    if spec.sample_report is not None and not (ws / "sample_report.md").is_file():
        raise HelperError(
            EXIT_INPUT, "missing-sample", "The sample report is not converted: run update-sample"
        )
    findings = chain_findings(spec, ws, config)
    guard_replace(ws, "synthesize", args.replace)
    writer = make_writer(config)
    # Synthesize with Word export off: a failed conversion inside synthesize() would lose the
    # returned report and its usage, and could leave an earlier run's report.docx behind.
    markdown_only = spec.model_copy(deep=True)
    markdown_only.settings.docx = False
    report = run_stage(
        "synthesize",
        lambda: writer.synthesize(markdown_only, ws, progress_callback=progress),
        config,
    )
    diagnostics = {
        "time": now(),
        "usage": dict(report.usage),
        **report_summary(report),
        "export": {"status": "pending"},
    }
    write_json(ws / "diagnostics" / "synthesis.json", diagnostics)
    record = load_record(ws)
    sample = record.get("sample") or {}
    entry = write_stage_record(
        spec,
        ws,
        "synthesize",
        config,
        {"sample_conversion": sample.get("conversion_id") if spec.sample_report else None},
    )
    diagnostics["export"] = export_docx(writer, spec, ws, config)
    write_json(ws / "diagnostics" / "synthesis.json", diagnostics)
    after = chain_findings(spec, ws, config)
    return {
        "stage": "synthesize",
        "run_id": entry["run_id"],
        "report": str(ws / "report" / "report.md"),
        "current": not after,
        "stale_before_run": stale_summary(findings),
        **diagnostics,
    }


def cmd_rebuild(args) -> dict:
    spec = load_spec(args.spec)
    ws = args.workspace
    stop_on_collision(spec, args)
    if not (ws / "report" / "report.md").is_file():
        raise HelperError(EXIT_INPUT, "missing-stage", "Run synthesize first")
    writer = make_writer({})
    markdown_only = spec.model_copy(deep=True)
    markdown_only.settings.docx = False
    report = run_stage("rebuild", lambda: writer.rebuild(markdown_only, ws), None)
    export = export_docx(writer, spec, ws, None)
    path = ws / "diagnostics" / "synthesis.json"
    diagnostics = read_json(path, {})
    diagnostics["export"] = export
    diagnostics["rebuilt"] = now()
    write_json(path, diagnostics)
    return {
        "stage": "rebuild",
        "report": str(ws / "report" / "report.md"),
        "sections": [s.id for s in report.sections],
        "export": export,
        "warnings": [
            "rebuild made no model call: the review log describes the generated text, not the "
            "hand edits",
            "sections that depend on an edited section were not updated",
        ],
        "stale": stale_summary(chain_findings(spec, ws, None)),
    }


def cmd_update_sample(args) -> dict:
    spec = load_spec(args.spec)
    ws = args.workspace
    stop_on_collision(spec, args)
    target = ws / "sample_report.md"
    if spec.sample_report is None:
        target.unlink(missing_ok=True)
        write_sample_record(ws, None)
        return {"sample": None, "removed": str(target)}
    sample = Path(spec.sample_report)
    if not sample.is_file():
        raise HelperError(EXIT_INPUT, "missing-sample", f"{sample}: sample report not found")
    if sample.suffix.lower() not in SAMPLE_TYPES:
        raise HelperError(
            EXIT_INPUT,
            "sample-type",
            f"{sample.name}: a sample report must be DOCX, Markdown, text or a text-based PDF",
        )
    try:
        config = load_config(args.provider)
    except HelperError:
        config = None  # the accepted formats convert locally and need no config
    if config is not None:
        apply_model_defaults(spec, config)
    from gaik.software_components.source_normalizer import SourceNormalizer

    # Built exactly as ReportWriter.normalize() builds it.
    normalizer = SourceNormalizer(
        config,
        vision_model=spec.models.vision,
        transcription_model=spec.models.transcription,
        language=spec.settings.transcription_language,
    )
    text = run_stage("update-sample", lambda: normalizer.to_markdown(sample), config)
    tmp = target.with_suffix(".md.tmp")
    ws.mkdir(parents=True, exist_ok=True)
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(target)  # only after the conversion succeeded
    conversion = write_sample_record(ws, sample)
    path = ws / "diagnostics" / "normalization.json"
    diagnostics = read_json(path, {"sample_updates": []})
    diagnostics.setdefault("sample_updates", []).append(
        {
            "time": now(),
            "file": sample.name,
            "conversion_id": conversion,
            "usage": normalizer.usage.snapshot(),
        }
    )
    write_json(path, diagnostics)
    return {
        "sample": sample.name,
        "conversion_id": conversion,
        "written": str(target),
        "characters": len(text),
    }


def load_structure(path: Path) -> list:
    if not path.is_file():
        raise HelperError(EXIT_INPUT, "structure", f"{path}: no such structure file")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise HelperError(EXIT_INPUT, "structure", f"{path.name}: not valid JSON ({exc})") from exc
    if isinstance(data, dict):
        data = data.get("structure", data.get("sections"))
    if not isinstance(data, list):
        raise HelperError(
            EXIT_INPUT,
            "structure",
            "The structure must be a list of sections, or {'structure': [...]}",
        )
    return data


def structure_to_sections(structure: list) -> tuple[list[dict], list[str]]:
    """The user's structure (titles, prompts) as spec sections, or the errors that stop it."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from template_to_spec import slug

    errors: list[str] = []
    if not structure:
        return [], ["The report needs at least one section"]
    ids: dict[str, str] = {}  # casefolded title -> id
    used: set[str] = set()
    rows = []
    for n, item in enumerate(structure, start=1):
        if not isinstance(item, dict):
            errors.append(f"Section {n}: must be an object with a title and a prompt")
            continue
        title = str(item.get("title") or "").strip()
        prompt = str(item.get("prompt") or "").strip()
        if not title:
            errors.append(f"Section {n}: has no title")
            continue
        if not prompt:
            errors.append(f"Section {n} ({title!r}): has no prompt saying what it should contain")
        key = title.casefold()
        if key in ids:
            errors.append(f"Two sections are titled {title!r}: give them different titles")
            continue
        base = slug(title) or f"section_{n}"
        section_id, k = base, 2
        while section_id in used:
            section_id, k = f"{base}_{k}", k + 1
        used.add(section_id)
        ids[key] = section_id
        items = [str(i).strip() for i in item.get("required_items") or [] if str(i).strip()]
        rows.append((n, title, prompt, items, list(item.get("summary_of") or []), section_id))

    sections = []
    for n, title, prompt, items, summary_of, section_id in rows:
        depends = []
        for ref in summary_of:
            target = ids.get(str(ref).strip().casefold())
            if target is None:
                errors.append(f"Section {n} ({title!r}) summarizes {ref!r}, which is not a section")
            elif target == section_id:
                errors.append(f"Section {n} ({title!r}) cannot summarize itself")
            elif target not in depends:
                depends.append(target)
        section = {"id": section_id, "title": title, "instructions": prompt}
        if items:
            section["required_items"] = items
        if depends:
            section["depends_on"] = depends
        sections.append(section)

    if sections and not errors:
        if all(s.get("depends_on") for s in sections):
            errors.append(
                "Every section summarizes other sections: at least one section must be written "
                "from the sources"
            )
        from types import SimpleNamespace

        cycle = find_cycle(
            [SimpleNamespace(id=s["id"], depends_on=s.get("depends_on", [])) for s in sections]
        )
        if cycle:
            errors.append("The summaries depend on each other in a circle: " + " -> ".join(cycle))
    return sections, errors


def cmd_set_sections(args) -> dict:
    """Write the user's approved structure into the spec. No model call."""
    path = args.spec
    if not path.is_file():
        raise HelperError(EXIT_INPUT, "spec", f"{path}: no such spec file")
    if args.structure.is_file() and os.path.samefile(args.structure, path):
        raise HelperError(
            EXIT_INPUT, "structure", "The structure file and the spec are the same file"
        )
    original = path.read_text(encoding="utf-8")
    raw = json.loads(original)  # edit the file itself, so its relative paths stay as written
    sections, errors = structure_to_sections(load_structure(args.structure))
    if errors:
        raise HelperError(
            EXIT_INPUT, "structure", "; ".join(errors), {"errors": errors, "sections": sections}
        )
    raw["sections"] = sections
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(raw, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)
    try:
        spec = load_spec(path)
    except HelperError:
        path.write_text(original, encoding="utf-8")  # leave the spec as it was
        raise
    _, warnings = section_problems(spec)
    if (args.workspace / "knowledge").exists():
        warnings.append("The sections changed after curation: curate and synthesize must run again")
    titles = {s["id"]: s["title"] for s in sections}
    return {
        "sections": [
            {
                "n": n,
                "id": s["id"],
                "title": s["title"],
                "prompt": s["instructions"],
                "required_items": s.get("required_items", []),
                "summary_of": [titles[d] for d in s.get("depends_on", [])],
            }
            for n, s in enumerate(sections, start=1)
        ],
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# The whole spec, proposed and agreed (SKILL.md, steps 2 and 5)
# ---------------------------------------------------------------------------

# The run settings propose-spec proposes; the user accepts or changes each one.
# `citations` is not here: it comes from intake, so it is never marked as a default.
PROPOSED_SETTINGS = {
    "transcription_language": "en",
    "curator_workers": 4,
    "review_attempts": 5,
    "strict_review": True,
    "docx": True,
    "curator": {"reasoning_effort": None, "temperature": None},
    "writer": {"reasoning_effort": None, "temperature": None},
    "reviewer": {"reasoning_effort": None, "temperature": None},
}
# Transcription models per provider; a provider missing here cannot transcribe in a run.
DEFAULT_TRANSCRIPTION = {"openai": "gpt-4o-transcribe", "azure": "gpt-4o-transcribe"}
MODEL_STEPS = ("vision", "transcription", "curator", "writer", "reviewer")
SPEC_KEYS = (
    "title", "description", "language", "sections", "instructions", "sources",
    "sample_report", "models", "settings",
)  # fmt: skip
SECTION_ID = re.compile(r"^[A-Za-z0-9_-]+$")


def provider_name(provider: str | None) -> str:
    """The provider a proposal is for. Only its name is used: no config, no credentials."""
    return (provider or os.environ.get("LLM_PROVIDER", "").strip() or DEFAULT_PROVIDER).lower()


def proposed_models(provider: str) -> dict:
    """The model per step for a provider, with GAIK_REPORT_<STEP>_MODEL overriding a default."""
    defaults = DEFAULT_MODELS.get(provider, {})
    models = {"vision": None, "transcription": DEFAULT_TRANSCRIPTION.get(provider)}
    for step, variable in MODEL_ENV.items():
        models[step] = os.environ.get(variable, "").strip() or defaults.get(step)
    return models


def find_secrets(value: Any, path: str = "") -> list[str]:
    """Paths of keys that look like credentials, anywhere in the proposal."""
    found = []
    if isinstance(value, dict):
        for key, inner in value.items():
            where = f"{path}.{key}" if path else str(key)
            if any(s in str(key).lower() for s in SECRET_KEYS) or "api_key" in str(key).lower():
                found.append(where)
            found += find_secrets(inner, where)
    elif isinstance(value, list):
        for n, inner in enumerate(value):
            found += find_secrets(inner, f"{path}[{n}]")
    return found


def complete_spec(raw: dict, provider: str, *, reset_models: bool = False) -> dict:
    """Every key of the spec spelled out: what the spec sets is kept, the rest proposed."""
    out = {
        "title": raw.get("title", ""),
        "description": raw.get("description", ""),
        "language": raw.get("language", "English"),
        "sections": raw.get("sections", []),
        "instructions": raw.get("instructions", ""),
    }
    sources = raw.get("sources") or {}
    out["sources"] = {
        "primary": list(sources.get("primary") or []),
        "secondary": list(sources.get("secondary") or []),
    }
    out["sample_report"] = raw.get("sample_report")
    models = proposed_models(provider)
    given = {} if reset_models else (raw.get("models") or {})
    out["models"] = {
        step: given[step] if given.get(step) is not None else models[step] for step in MODEL_STEPS
    }
    settings = dict(raw.get("settings") or {})
    full = {}
    for key, value in PROPOSED_SETTINGS.items():
        if isinstance(value, dict):
            full[key] = {**value, **(settings.get(key) or {})}
        else:
            full[key] = settings.get(key, value)
    full["citations"] = settings.get("citations", True)
    for key, value in settings.items():  # unknown keys stay, so the schema check names them
        full.setdefault(key, value)
    out["settings"] = full
    for key, value in raw.items():
        out.setdefault(key, value)
    return out


def spec_from_raw(raw: dict, root: Path):
    """Validate a spec dict with the library's own schema; paths resolve against `root`."""
    rw = import_report_writer()
    spec = rw.ReportSpec.model_validate_json(json.dumps(raw, ensure_ascii=False))
    spec.sources = {k: [root / p for p in v] for k, v in spec.sources.items()}
    if spec.sample_report is not None:
        spec.sample_report = root / spec.sample_report
    return spec


def proposal_problems(raw: dict) -> tuple[list[str], list[str]]:
    """The skill's own rules for a spec, before the library's schema check."""
    errors, warnings = [], []
    secrets = find_secrets(raw)
    if secrets:
        errors.append(
            f"The proposal holds keys that look like credentials ({', '.join(secrets)}); "
            "credentials come from the environment, never from the spec"
        )
    sections = raw.get("sections") or []
    if not sections:
        errors.append("The report needs at least one section")
    ids, titles = [], []
    for n, s in enumerate(sections, start=1):
        if not isinstance(s, dict):
            errors.append(f"sections[{n - 1}]: must be an object")
            continue
        sid, title = str(s.get("id") or ""), str(s.get("title") or "").strip()
        if not SECTION_ID.match(sid):
            errors.append(f"sections[{n - 1}]: id {sid!r} may use only letters, digits, _ and -")
        if sid in ids:
            errors.append(f"sections[{n - 1}]: id {sid!r} is used twice")
        if not title:
            errors.append(f"sections[{n - 1}]: has no title")
        elif title.casefold() in titles:
            errors.append(f"Two sections are titled {title!r}: give them different titles")
        if not str(s.get("instructions") or "").strip():
            errors.append(f"sections[{n - 1}] ({title!r}): has no instructions")
        ids.append(sid)
        titles.append(title.casefold())
    for n, s in enumerate(sections):
        if not isinstance(s, dict):
            continue
        for dep in s.get("depends_on") or []:
            if dep == s.get("id"):
                errors.append(f"sections[{n}] ({s.get('title')!r}) cannot depend on itself")
            elif dep not in ids:
                errors.append(f"sections[{n}] ({s.get('title')!r}) depends on {dep!r}, not a section")
    names = [Path(p).name for paths in (raw.get("sources") or {}).values() for p in paths or []]
    sample = raw.get("sample_report")
    if sample and Path(sample).name in names:
        errors.append(
            f"{Path(sample).name} is both a source and the sample report; a sample's facts never "
            "reach the report, so it cannot also be evidence"
        )
    if all(isinstance(s, dict) and s.get("id") == "draft" for s in sections):
        return errors, warnings  # step 2: the instructions are written with the sections
    settings = raw.get("settings") or {}
    if settings.get("citations") is False and "cite each fact" in str(raw.get("instructions", "")).lower():
        warnings.append(
            "Citations are off but the instructions still ask to cite each fact; remove that sentence"
        )
    if settings.get("citations", True) and "cite" not in str(raw.get("instructions", "")).lower():
        warnings.append(
            "Citations are on but the instructions have no citation sentence "
            "(references/report-spec.md)"
        )
    if "(missing:" not in str(raw.get("instructions", "")):
        warnings.append("The instructions have no gap-marker sentence (references/report-spec.md)")
    return errors, warnings


def changed_stages(old: dict, new: dict, ws: Path) -> list[str]:
    """Which existing stages a change from `old` to `new` makes not current."""

    def pick(d: dict, *keys: str) -> Any:
        out = {}
        for key in keys:
            value: Any = d
            for part in key.split("."):
                value = value.get(part) if isinstance(value, dict) else None
            out[key] = value
        return sha256_json(out)

    normalize = (
        "sources", "models.vision", "models.transcription", "settings.transcription_language",
    )  # fmt: skip
    curate = ("sections", "instructions", "models.curator", "settings.curator")
    synthesize = (
        "title", "language", "sections", "instructions", "sample_report", "models.writer",
        "models.reviewer", "settings.review_attempts", "settings.strict_review",
        "settings.citations", "settings.writer", "settings.reviewer",
    )  # fmt: skip
    reads = {"normalize": normalize, "curate": curate, "synthesize": synthesize}
    first = next((s for s in STAGES if pick(old, *reads[s]) != pick(new, *reads[s])), None)
    # A later stage is built on an earlier one, so it must run again too.
    later = STAGES[STAGES.index(first) :] if first else ()
    messages = [f"{s} must run again" for s in later if (ws / STAGE_DIRS[s]).exists()]
    if old.get("sample_report") != new.get("sample_report") and (ws / "sample_report.md").exists():
        messages.append("the sample report changed: run update-sample before synthesize")
    return messages


def review_lines(spec: dict, provider: str) -> list[str]:
    """The whole spec as a review list, defaults marked."""

    def show(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False)

    lines = ["REPORT"]
    for key in ("title", "description", "language"):
        lines.append(f"  {key}: {spec.get(key) or '(empty)'}")
    lines.append("  instructions:")
    for line in (spec.get("instructions") or "(empty)").splitlines():
        lines.append(f"    {line}")
    for cls in ("primary", "secondary"):
        files = spec["sources"].get(cls) or []
        lines.append(f"  sources.{cls}: {', '.join(files) if files else '(none)'}")
    lines.append(f"  sample_report: {spec.get('sample_report') or '(none)'}")
    lines.append("SECTIONS")
    titles = {s.get("id"): s.get("title") for s in spec["sections"] if isinstance(s, dict)}
    for n, s in enumerate(spec["sections"], start=1):
        if not isinstance(s, dict):
            continue
        lines.append(f"  {n}. {s.get('title')}  [id: {s.get('id')}]")
        lines.append(f"     instructions: {s.get('instructions') or '(none)'}")
        items = s.get("required_items") or []
        lines.append(f"     required_items: {'; '.join(items) if items else '(none)'}")
        deps = s.get("depends_on") or []
        lines.append(
            "     depends_on: "
            + (
                ", ".join(f"{d} ({titles.get(d, '?')})" for d in deps)
                if deps
                else "(none: written from the sources)"
            )
        )
    models = proposed_models(provider)
    lines.append(f"MODELS (provider: {provider})")
    for step in MODEL_STEPS:
        value = spec["models"].get(step)
        mark = "  (default)" if value == models[step] else ""
        lines.append(f"  models.{step}: {show(value)}{mark}")
    lines.append("SETTINGS")
    for key, value in spec["settings"].items():
        mark = "  (default)" if key in PROPOSED_SETTINGS and value == PROPOSED_SETTINGS[key] else ""
        lines.append(f"  settings.{key}: {show(value)}{mark}")
    return lines


def ordered(spec: dict) -> dict:
    return {**{k: spec[k] for k in SPEC_KEYS if k in spec}, **spec}


def cmd_propose_spec(args) -> dict:
    """Write the whole spec as a proposal for review. No model call; the spec is not changed."""
    path, out = args.spec, args.out
    if not path.is_file():
        raise HelperError(EXIT_INPUT, "spec", f"{path}: no such spec file")
    if out.exists() and os.path.samefile(out, path):
        raise HelperError(EXIT_INPUT, "proposal", "--out must not be the spec itself")
    # A proposal under review keeps the user's edits: start from it when it exists.
    base = out if out.is_file() else path
    try:
        raw = json.loads(base.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise HelperError(EXIT_INPUT, "spec", f"{base.name}: not valid JSON ({exc})") from exc
    if args.structure is not None:
        sections, errors = structure_to_sections(load_structure(args.structure))
        if errors:
            raise HelperError(EXIT_INPUT, "structure", "; ".join(errors), {"errors": errors})
        raw["sections"] = sections
    provider = provider_name(args.provider)
    proposal = ordered(complete_spec(raw, provider, reset_models=args.reset_models))
    errors, warnings = proposal_problems(proposal)
    try:
        spec_from_raw(proposal, path.resolve().parent)
    except Exception as exc:
        errors.append(f"The library's schema rejects the proposal: {exc}")
    write_json(out, proposal)
    return {
        "proposal_file": str(out),
        "started_from": base.name,
        "provider": provider,
        "review": review_lines(proposal, provider),
        "errors": errors,
        "warnings": warnings,
        "proposal": proposal,
    }


def cmd_apply_spec(args) -> dict:
    """Check a reviewed proposal and, unless --check, write it as the spec. No model call."""
    path, proposal_path, ws = args.spec, args.proposal, args.workspace
    if not proposal_path.is_file():
        raise HelperError(EXIT_INPUT, "proposal", f"{proposal_path}: no such proposal file")
    if path.exists() and os.path.samefile(path, proposal_path):
        raise HelperError(EXIT_INPUT, "proposal", "The proposal and the spec are the same file")
    try:
        new = json.loads(proposal_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise HelperError(EXIT_INPUT, "proposal", f"{proposal_path.name}: not valid JSON ({exc})") from exc
    provider = provider_name(args.provider)
    old = read_json(path, {}) if path.is_file() else {}
    errors, warnings = proposal_problems(new)
    spec = None
    if not errors:
        try:
            spec = spec_from_raw(new, path.resolve().parent)
        except Exception as exc:
            errors.append(f"The library's schema rejects the proposal: {exc}")
    if spec is not None:
        # Only the provider's name is needed to check recordings: no credentials are loaded.
        pre = preflight_checks(
            spec, {"provider": provider}, docx_blocks=True, spec_path=path, workspace=ws
        )
        errors += pre["errors"]
        warnings += [w for w in pre["warnings"] if w not in warnings]
    stages = changed_stages(old, new, ws) if old else []
    result = {
        "review": review_lines(complete_spec(new, provider), provider),
        "warnings": warnings + stages,
        "written": False,
    }
    if errors:
        raise HelperError(EXIT_INPUT, "proposal", "; ".join(errors), {"errors": errors, **result})
    if not args.check:
        original = path.read_text(encoding="utf-8") if path.is_file() else None
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(new, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        tmp.replace(path)
        try:
            load_spec(path)
        except HelperError:
            if original is not None:
                path.write_text(original, encoding="utf-8")  # leave the spec as it was
            raise
        result["written"] = True
    return result


COMMANDS = {
    "preflight": cmd_preflight,
    "propose-spec": cmd_propose_spec,
    "apply-spec": cmd_apply_spec,
    "set-sections": cmd_set_sections,
    "normalize": cmd_normalize,
    "curate": cmd_curate,
    "validate-knowledge": cmd_validate_knowledge,
    "synthesize": cmd_synthesize,
    "rebuild": cmd_rebuild,
    "update-sample": cmd_update_sample,
}
NEEDS_PROVIDER = {
    "normalize", "curate", "synthesize", "update-sample", "preflight", "propose-spec", "apply-spec",
}  # fmt: skip
REPLACES = {"normalize", "curate", "synthesize"}


def parse(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="run_report.py", description="Run the gaik report writer one checked stage at a time."
    )
    sub = parser.add_subparsers(dest="command", required=True)
    for name in COMMANDS:
        p = sub.add_parser(name)
        p.add_argument("--spec", type=Path, required=True, help="the report spec JSON")
        p.add_argument("--workspace", type=Path, required=True, help="the workspace folder")
        p.add_argument("--json", action="store_true", help="print one JSON result on stdout")
        if name in NEEDS_PROVIDER:
            p.add_argument(
                "--provider",
                help="LLM provider for get_llm_config (default: LLM_PROVIDER or openai)",
            )
        if name == "preflight":
            p.add_argument(
                "--check-provider",
                action="store_true",
                help="also load the provider config (no model call)",
            )
        if name in ("set-sections", "propose-spec"):
            p.add_argument(
                "--structure",
                type=Path,
                required=name == "set-sections",
                help="JSON list of sections: title, prompt, required_items, summary_of",
            )
        if name == "propose-spec":
            p.add_argument(
                "--out", type=Path, required=True, help="where to write the proposal JSON"
            )
            p.add_argument(
                "--reset-models",
                action="store_true",
                help="propose the provider's default models again, keeping the other edits",
            )
        if name == "apply-spec":
            p.add_argument(
                "--proposal", type=Path, required=True, help="the reviewed proposal JSON"
            )
            p.add_argument(
                "--check", action="store_true", help="check the proposal only; write nothing"
            )
        if name in REPLACES:
            p.add_argument(
                "--replace",
                action="store_true",
                help="allow replacing this stage's existing output",
            )
    return parser.parse_args(argv)


def human(command: str, result: dict) -> str:
    lines = [f"{command}: done"]
    for line in result.get("review") or []:
        lines.append(f"  {line}")
    if "proposal_file" in result:
        lines.append(f"  proposal: {Path(result['proposal_file']).name}")
    if "written" in result:
        lines.append(f"  written: {result['written']}")
    for key in ("report", "run_id", "current"):
        if key in result:
            lines.append(f"  {key}: {result[key]}")
    labels = {
        "errors": "error",
        "problems": "problem",
        "warnings": "warning",
        "stale": "not current",
        "stale_before_run": "was not current",
    }
    for key, label in labels.items():
        for item in result.get(key) or []:
            lines.append(f"  {label}: {item}")
    for section in result.get("sections") or []:
        if isinstance(section, dict) and "n" in section:
            extra = (
                f" (summary of {', '.join(section['summary_of'])})" if section["summary_of"] else ""
            )
            lines.append(f"  {section['n']}. {section['title']}{extra}: {section['prompt']}")
    if "export" in result:
        lines.append(f"  word export: {result['export'].get('status')}")
    if result.get("dropped"):
        lines.append(f"  dropped facts: {len(result['dropped'])} (see diagnostics/curation.json)")
    if result.get("unresolved_review_edits"):
        lines.append(f"  unresolved review edits: {result['unresolved_review_edits']}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    args = parse(argv)
    # Components print progress to stdout (the transcriber does). While a command runs, stdout
    # goes to stderr, so the result printed afterwards is the only thing on stdout.
    real_stdout = sys.stdout
    try:
        with contextlib.redirect_stdout(sys.stderr):
            result = COMMANDS[args.command](args)
        code = EXIT_OK
        output = {"ok": True, "command": args.command, **result}
    except HelperError as exc:
        code = exc.code
        output = {
            "ok": False,
            "command": args.command,
            "error": {"category": exc.category, "message": exc.message},
            **exc.result,
        }
    if args.json:
        print(json.dumps(output, indent=2, ensure_ascii=False, default=str), file=real_stdout)
    elif output["ok"]:
        print(human(args.command, output), file=real_stdout)
    else:
        print(f"{args.command}: FAILED ({output['error']['category']})", file=sys.stderr)
        listed = output.get("errors") or output.get("problems")
        if not listed:  # the message only repeats a listed error
            print(f"  {output['error']['message']}", file=sys.stderr)
        for key, label in (("errors", "error"), ("problems", "problem"), ("warnings", "warning")):
            for item in output.get(key) or []:
                print(f"  {label}: {item}", file=sys.stderr)
    return code


if __name__ == "__main__":
    sys.exit(main())
