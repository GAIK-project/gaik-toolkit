"""Prepare a folder of mixed documents (PDF / DOCX / TXT) for Open WebUI.

This script reads every supported file under ``INPUT_DIR`` and writes a
matching markdown file to ``OUTPUT_DIR``. The markdown files are then
imported into Open WebUI as a Knowledge collection so that an Ollama-backed
chatbot can answer questions about them.

Per file type:

* ``.pdf``  -> ``MultimodalParser`` (Google Gemini, OpenAI-compatible REST).
              Uses vision so that scanned, dual-PDF, and image-heavy pages
              are extracted accurately as markdown.
* ``.docx`` -> ``DocxParser`` (local, ``python-docx``). No API call needed.
* ``.txt``  -> copied as-is (renamed to ``.md``).

Idempotent: skips files whose ``.md`` is newer than the source.

Environment variables (see ``.env.example``):

    GOOGLE_API_KEY=...                          # Google AI Studio key
    GOOGLE_MODEL=gemini-3-flash-preview         # Gemini model
    INPUT_DIR=./input_docs                      # source folder
    OUTPUT_DIR=./markdown_out                   # destination folder

Run::

    pip install "gaik[multimodal-parser,parser-cpu]"
    python prepare_docs.py
"""

from __future__ import annotations

import logging
import os
import shutil
import sys
import time
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("prepare_docs")

PDF_EXTS = {".pdf"}
DOCX_EXTS = {".docx", ".doc"}
TXT_EXTS = {".txt", ".md"}
SUPPORTED_EXTS = PDF_EXTS | DOCX_EXTS | TXT_EXTS


@dataclass
class FileResult:
    source: Path
    output: Path | None
    status: str  # "ok", "skipped", "error", "unsupported"
    duration_s: float = 0.0
    cost_usd: float = 0.0
    detail: str = ""


def iter_source_files(root: Path) -> Iterable[Path]:
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTS:
            yield path


def output_path_for(source: Path, input_root: Path, output_root: Path) -> Path:
    rel = source.relative_to(input_root).with_suffix(".md")
    return output_root / rel


def needs_update(source: Path, target: Path) -> bool:
    if not target.exists():
        return True
    return source.stat().st_mtime > target.stat().st_mtime


def parse_pdf(parser, source: Path) -> tuple[str, float]:
    """Run MultimodalParser on a PDF and return ``(markdown, cost_usd)``."""
    result = parser.parse(source)
    cost = result.usage.cost_usd if result.usage else 0.0
    return result.clean_markdown, cost


def parse_docx(parser, source: Path) -> str:
    return parser.parse_docx(str(source), use_markdown=True)


def parse_txt(source: Path) -> str:
    return source.read_text(encoding="utf-8", errors="replace")


def write_markdown(target: Path, body: str, source_name: str) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    header = f"# {source_name}\n\n"
    target.write_text(header + body.lstrip(), encoding="utf-8")


def process_file(
    source: Path,
    target: Path,
    *,
    pdf_parser,
    docx_parser,
) -> FileResult:
    if not needs_update(source, target):
        return FileResult(source=source, output=target, status="skipped")

    started = time.perf_counter()
    suffix = source.suffix.lower()
    try:
        cost = 0.0
        if suffix in PDF_EXTS:
            markdown, cost = parse_pdf(pdf_parser, source)
        elif suffix in DOCX_EXTS:
            markdown = parse_docx(docx_parser, source)
        elif suffix in TXT_EXTS:
            markdown = parse_txt(source)
        else:
            return FileResult(
                source=source,
                output=None,
                status="unsupported",
                detail=f"unknown suffix {suffix}",
            )
        write_markdown(target, markdown, source.stem)
        return FileResult(
            source=source,
            output=target,
            status="ok",
            duration_s=time.perf_counter() - started,
            cost_usd=cost,
        )
    except Exception as exc:  # noqa: BLE001 - we want to keep going on per-file errors
        logger.exception("Failed to parse %s", source)
        return FileResult(
            source=source,
            output=None,
            status="error",
            duration_s=time.perf_counter() - started,
            detail=str(exc),
        )


def build_pdf_parser():
    """Create the Gemini-backed MultimodalParser (lazy import)."""
    from gaik.software_components.parsers import MultimodalParser

    if not os.getenv("GOOGLE_API_KEY"):
        raise SystemExit(
            "GOOGLE_API_KEY is not set. Get a free key at "
            "https://aistudio.google.com/app/apikey and add it to .env."
        )

    return MultimodalParser(
        model_provider="google",
        vertex_ai=False,  # use the Google AI Studio API, not Vertex AI
        model=os.getenv("GOOGLE_MODEL", "gemini-3-flash-preview"),
        reasoning_effort="low",
    )


def build_docx_parser():
    from gaik.software_components.parsers import DocxParser

    return DocxParser()


def main() -> int:
    input_dir = Path(os.getenv("INPUT_DIR", "./input_docs")).resolve()
    output_dir = Path(os.getenv("OUTPUT_DIR", "./markdown_out")).resolve()

    if not input_dir.exists():
        logger.error("INPUT_DIR does not exist: %s", input_dir)
        return 1

    output_dir.mkdir(parents=True, exist_ok=True)
    sources = list(iter_source_files(input_dir))

    if not sources:
        logger.warning(
            "No supported files found under %s (looking for: %s)",
            input_dir,
            ", ".join(sorted(SUPPORTED_EXTS)),
        )
        return 0

    logger.info("Found %d source file(s) under %s", len(sources), input_dir)

    pdf_parser = None
    docx_parser = None
    if any(p.suffix.lower() in PDF_EXTS for p in sources):
        pdf_parser = build_pdf_parser()
    if any(p.suffix.lower() in DOCX_EXTS for p in sources):
        docx_parser = build_docx_parser()

    results: list[FileResult] = []
    for source in sources:
        target = output_path_for(source, input_dir, output_dir)
        result = process_file(
            source,
            target,
            pdf_parser=pdf_parser,
            docx_parser=docx_parser,
        )
        results.append(result)
        emoji = {"ok": "OK", "skipped": "SKIP", "error": "FAIL", "unsupported": "SKIP"}[
            result.status
        ]
        logger.info(
            "[%s] %s -> %s (%.2fs%s)",
            emoji,
            source.relative_to(input_dir),
            (
                result.output.relative_to(output_dir)
                if result.output and result.output.is_relative_to(output_dir)
                else "-"
            ),
            result.duration_s,
            f", ${result.cost_usd:.4f}" if result.cost_usd else "",
        )
        if result.detail:
            logger.info("    detail: %s", result.detail)

    summary = {s: 0 for s in ("ok", "skipped", "error", "unsupported")}
    total_cost = 0.0
    for r in results:
        summary[r.status] += 1
        total_cost += r.cost_usd

    logger.info(
        "Done. ok=%d skipped=%d error=%d unsupported=%d  total Gemini cost=$%.4f",
        summary["ok"],
        summary["skipped"],
        summary["error"],
        summary["unsupported"],
        total_cost,
    )
    logger.info(
        "Output written to %s. Import this folder as a Knowledge collection in Open WebUI.",
        output_dir,
    )
    # ensure shutil is referenced so static checkers do not flag it (kept for
    # future: copying images alongside markdown if MultimodalParser exposes them)
    _ = shutil

    return 0 if summary["error"] == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
