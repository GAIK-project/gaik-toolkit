"""Generic multi-source report generator.

Turns a mixed set of source files (PDF, Word, Excel/CSV, text, Markdown,
audio/video, images) into a long-form Markdown report whose structure is
defined entirely by the user (section titles + per-section instructions).

Design (see the module README):
  * Lean GAIK-module constructor: ``__init__(*, api_config=None, use_azure=True)``.
  * One public method: ``run(...)`` — all per-run settings live here.
  * Pure orchestration over existing GAIK components. Nothing in this module is
    specific to any report domain (no classification, relevance scoring, file
    selection, or fixed section templates).

Pipeline:
    input_paths -> evidence (parse/transcribe/extract each file to markdown)
                -> ONE LLM call that writes the whole report (all user-defined
                   sections + optional sample report as a format/style template)
                -> Markdown report (+ per-section breakdown split from it)
"""

from __future__ import annotations

import csv
import hashlib
import json
import logging
import os
import re
import tempfile
from collections.abc import Callable
from dataclasses import replace
from functools import partial
from pathlib import Path, PurePosixPath
from typing import Any

from gaik.software_components._log_names import file_tag
from gaik.software_components.input_limits import InputLimits
from gaik.software_components.source_material import (
    SourceMaterial,
    clean_label,
    with_source_material_instruction,
)
from gaik.software_components.source_normalizer.paths import SourcePathError, path_inside

from ._material import (
    SOURCE_HEADER_NOTE,
    TRUNCATED_NOTE,
    Evidence,
    EvidenceSource,
    render_evidence,
    source_list,
)
from .models import (
    EvidenceItem,
    GeneratedSection,
    ReportGenerationResult,
    ReportSectionSpec,
    _normalize_heading,
    _slug,
)

# LLM path (monkeypatchable in tests). Imported defensively so the module can be
# imported even in environments without the openai SDK present.
try:
    from gaik.software_components.llm import create_llm_client
except Exception:  # pragma: no cover - optional at import time
    create_llm_client = None  # type: ignore

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Supported source types (by file extension)
# ---------------------------------------------------------------------------

_TEXT_EXT = {".txt"}
_MARKDOWN_EXT = {".md", ".markdown"}
_PDF_EXT = {".pdf"}
_DOCX_EXT = {".docx"}
_CSV_EXT = {".csv"}
_XLSX_EXT = {".xlsx"}
_AUDIO_EXT = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"}
_VIDEO_EXT = {".mp4", ".mov", ".mkv", ".avi", ".webm"}
_IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".tiff", ".tif", ".bmp", ".gif"}
# Sent to a model as PNG: the providers take PNG, JPEG, GIF and WebP only.
_CONVERTED_IMAGE_TYPES = {"tiff", "bmp"}  # by content, as file_type detects it
# Refused before any source is read: openpyxl reads only .xlsx.
_REFUSED_EXT = {".xls": "the old Excel format .xls is not supported; save it as .xlsx"}

_EXT_TO_TYPE: dict[str, str] = {
    **{e: "text" for e in _TEXT_EXT},
    **{e: "markdown" for e in _MARKDOWN_EXT},
    **{e: "pdf" for e in _PDF_EXT},
    **{e: "docx" for e in _DOCX_EXT},
    **{e: "csv" for e in _CSV_EXT},
    **{e: "xlsx" for e in _XLSX_EXT},
    **{e: "audio" for e in _AUDIO_EXT},
    **{e: "video" for e in _VIDEO_EXT},
    **{e: "image" for e in _IMAGE_EXT},
}

SUPPORTED_EXTENSIONS = frozenset(_EXT_TO_TYPE)

_SOURCE_SEPARATOR = "\n\n---\n\n"


# ---------------------------------------------------------------------------
# Prompt templates (generic — no domain-specific wording)
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are a professional report writer. You write a COMPLETE report from the \
evidence the user provides.

VERY IMPORTANT:
- Do not make up anything. Generate content only from the given evidence. If the \
evidence does not contain information for a section, state this clearly within \
that section rather than inventing or inferring content.
- The EVIDENCE is your ONLY source of content. A FORMAT REFERENCE (if given) is a \
layout example, usually about a completely DIFFERENT subject — copy its shape, \
never its content. Never reuse its facts, topic, names, numbers, examples, or wording.
- Use simple, direct language without fluff, filler phrases, or em dashes (—).
- Maintain a neutral and professional tone throughout.

Rules:
- Use only the provided evidence. Do not invent facts, figures, names, or events.
- Output clean Markdown. Begin with a single level-1 title (`# <report title>`).
- Include EXACTLY the requested sections, in the given order, each as a level-2 \
heading (`## <section title>`) using the exact titles provided. Do not add, drop, \
merge, or reorder sections.
- Follow each section's content instructions. If the evidence lacks information \
for a section, say so explicitly within that section.
- FORMAT: If a FORMAT REFERENCE is provided, it governs BOTH structure AND length. \
Reproduce its formatting choices exactly — how each section is structured \
internally, whether it uses prose paragraphs, bullet lists, or numbered lists, \
the approximate number of paragraphs or bullet points per section, the approximate \
length of each paragraph or item, bold lead-in patterns, and citation style — but \
take ZERO content from it. The reference is about a different topic; if you find \
yourself repeating any fact, name, number, or sentence from it, stop and write from \
the evidence instead. Length rule: each section should be approximately the same \
total length and density as the corresponding reference section — not shorter and \
not longer. Do not pad to seem thorough. If NO reference is provided, write in a \
clean, professional report format of your choice.

Content guidelines:
- When a FORMAT REFERENCE is provided, match its level of brevity and detail. Do \
not write more than the reference demonstrates — "comprehensive coverage" means \
matching the reference's density, not exhausting all available evidence.
- When NO FORMAT REFERENCE is provided: make the most of all relevant information \
and cover each section fully without omitting important details.
- Use direct language that precisely communicates facts and insights.
- Vary sentence structures naturally to maintain reader engagement.
- Use domain-specific terminology where appropriate, but prefer simpler terms \
when they communicate the same meaning.
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _normalize_sections(
    sections: list[ReportSectionSpec | dict[str, Any]],
) -> list[ReportSectionSpec]:
    if not sections:
        raise ValueError("`sections` must contain at least one section.")
    out: list[ReportSectionSpec] = []
    for i, s in enumerate(sections):
        if isinstance(s, ReportSectionSpec):
            # Copy so we can fill in a derived id without mutating the caller's object.
            spec = ReportSectionSpec(
                title=s.title,
                instructions=s.instructions,
                required=s.required,
                id=s.id,
                depends_on=list(s.depends_on),
            )
        elif isinstance(s, dict):
            if not s.get("title"):
                raise ValueError(f"Section {i} is missing a 'title'.")
            spec = ReportSectionSpec(
                title=str(s["title"]),
                instructions=str(s.get("instructions", "")),
                required=bool(s.get("required", True)),
                id=str(s["id"]) if s.get("id") else None,
                depends_on=[str(d) for d in (s.get("depends_on") or [])],
            )
        else:
            raise TypeError(
                f"Section {i} must be a ReportSectionSpec or dict, got {type(s).__name__}."
            )
        # Derive a stable id from the title when not given.
        if not spec.id:
            spec.id = _slug(spec.title)
        out.append(spec)

    # Validate ids and dependencies.
    seen_ids: set[str] = set()
    for spec in out:
        if spec.id in seen_ids:
            raise ValueError(
                f"Duplicate section id '{spec.id}' (derived from title '{spec.title}'). "
                "Give the colliding sections explicit, unique `id` values."
            )
        seen_ids.add(spec.id)
    for spec in out:
        for dep in spec.depends_on:
            if dep == spec.id:
                raise ValueError(f"Section '{spec.id}' cannot depend on itself.")
            if dep not in seen_ids:
                raise ValueError(
                    f"Section '{spec.id}' depends on unknown section id '{dep}'. "
                    f"Known ids: {sorted(seen_ids)}."
                )
    return out


def _collect_input_files(input_paths: list[str | Path]) -> list[Path]:
    """Expand files/folders into a flat list of supported source files.

    A file of a refused type (``.xls``), named or inside a folder, raises
    ``ValueError`` here, before any source is parsed or transcribed.
    """
    if not input_paths:
        raise ValueError("`input_paths` must contain at least one file or folder.")
    collected: list[Path] = []
    refused: list[Path] = []
    seen: set[Path] = set()
    for raw in input_paths:
        p = Path(raw)
        if not p.exists():
            raise FileNotFoundError(f"Input path does not exist: {p}")
        candidates = sorted(p.rglob("*")) if p.is_dir() else [p]
        for c in candidates:
            if not c.is_file():
                continue
            if c.suffix.lower() in _REFUSED_EXT:
                refused.append(c)
                continue
            if c.suffix.lower() not in SUPPORTED_EXTENSIONS:
                continue
            rp = c.resolve()
            if rp in seen:
                continue
            seen.add(rp)
            collected.append(c)
    if refused:
        names = ", ".join(c.name for c in refused[:5]) + (" ..." if len(refused) > 5 else "")
        reasons = sorted({_REFUSED_EXT[c.suffix.lower()] for c in refused})
        raise ValueError(f"{names}: {'; '.join(reasons)}. No source was read.")
    return collected


def _csv_to_markdown(path: Path) -> str:
    with open(path, encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.reader(fh))
    if not rows:
        return "_(empty CSV)_"
    return _rows_to_markdown_table(rows)


def _table_cell(value: Any) -> str:
    """One cell's text for a Markdown table: lines joined by a space and ``|`` escaped,
    as SpreadsheetParser writes them, so a value stays in its column and its row."""
    text = "" if value is None else str(value)
    return " ".join(text.splitlines()).replace("|", "\\|")


def _rows_to_markdown_table(rows: list[list[Any]]) -> str:
    width = max(len(r) for r in rows)
    norm = [[_table_cell(c) for c in r] + [""] * (width - len(r)) for r in rows]
    header, *body = norm
    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join(["---"] * width) + " |",
    ]
    lines += ["| " + " | ".join(r) + " |" for r in body]
    return "\n".join(lines)


def _xlsx_to_markdown(path: Path) -> str:
    try:
        from openpyxl import load_workbook
    except ImportError:
        logger.warning(
            "Cannot parse %s: 'openpyxl' is not installed. Install gaik extras "
            "for spreadsheet support. Skipping spreadsheet content.",
            file_tag(path),
        )
        return f"_([.xlsx not parsed: openpyxl not installed] {path.name})_"

    wb = load_workbook(filename=str(path), read_only=True, data_only=True)
    blocks: list[str] = []
    for ws in wb.worksheets:
        rows = [[("" if v is None else v) for v in row] for row in ws.iter_rows(values_only=True)]
        rows = [r for r in rows if any(str(c).strip() for c in r)]
        if not rows:
            continue
        blocks.append(f"### Sheet: {ws.title}\n\n{_rows_to_markdown_table(rows)}")
    wb.close()
    return "\n\n".join(blocks) if blocks else "_(no tabular data found)_"


def _eight_bit(frame: Any) -> Any:
    """A Pillow image in a mode PNG keeps as the model sees it, 8 bits per channel.

    A 16- or 32-bit grayscale page (``I;16``, ``I``) or a float one (``F``) is scaled
    from its darkest to its lightest value: converted directly, Pillow clips every value
    over 255, so a 16-bit scan would turn white and a float one black. Other modes
    (CMYK, YCbCr, ...) become RGB.
    """
    from PIL import Image

    if frame.mode in {"1", "L", "LA", "P", "RGB", "RGBA"}:
        return frame
    if frame.mode.startswith("I") or frame.mode == "F":
        values = frame if frame.mode == "F" else frame.convert("F")
        low, high = values.getextrema()
        if high <= low:
            return Image.new("L", frame.size, 255 if high > 0 else 0)
        scale = 255.0 / (high - low)
        return values.point(lambda v: (v - low) * scale).convert("L")
    return frame.convert("RGB")


def _as_png_pages(path: Path, folder: Path, limits: InputLimits) -> list[Path]:
    """A TIFF or BMP image as one PNG file per page in ``folder``.

    The model providers take PNG, JPEG, GIF and WebP only. The image is checked against
    ``limits`` (size, pixels, and pages for a multi-page TIFF) before it is decoded.
    """

    try:
        from PIL import Image, ImageSequence
    except ImportError as exc:  # pragma: no cover - Pillow comes with the parser extra
        raise ImportError(
            "Reading a TIFF or BMP image needs Pillow. Install it with:\n"
            '    pip install "gaik[multi-source-report-generator]"'
        ) from exc

    limits.check_image_file(path)
    pages: list[Path] = []
    with Image.open(path) as image:
        frames = getattr(image, "n_frames", 1)
        if limits.max_pages is not None and frames > 1:
            limits.check_pages(frames, path.name)
        for number, frame in enumerate(ImageSequence.Iterator(image), start=1):
            limits.check_image_pixels(frame.width, frame.height, path.name)
            frame = _eight_bit(frame)
            page = folder / f"page_{number:04d}.png"
            frame.save(page, format="PNG")
            pages.append(page)
    return pages


def _normalize_report_markdown(text: str | None, report_title: str) -> str:
    """Ensure the model's report starts with a single H1 title and ends cleanly."""
    body = (text or "").strip()
    if not body:
        body = f"# {report_title}"
    elif not body.lstrip().startswith("# "):
        body = f"# {report_title}\n\n{body}"
    return body + "\n"


def _split_into_sections(markdown: str, specs: list[ReportSectionSpec]) -> list[GeneratedSection]:
    """Split the assembled report into per-section objects by its level-2 headings.

    Positional, robust to minor heading rewording: the Nth ``##`` heading maps to
    the Nth requested section title (for stable filenames), with the body taken
    verbatim from the report. Falls back to a single section if no ``##`` headings
    are present.
    """
    lines = markdown.splitlines()
    # Strip any accidental "SECTION:" prefix the model may echo from the prompt.
    heads = [
        (i, line[3:].strip().removeprefix("SECTION:").strip())
        for i, line in enumerate(lines)
        if line.startswith("## ")
    ]
    if not heads:
        return [
            GeneratedSection(
                title=specs[0].title if specs else "Report", content_markdown=markdown.strip()
            )
        ]

    sections: list[GeneratedSection] = []
    for k, (idx, heading_title) in enumerate(heads):
        end = heads[k + 1][0] if k + 1 < len(heads) else len(lines)
        body = "\n".join(lines[idx + 1 : end]).strip()
        title = specs[k].title if k < len(specs) else heading_title
        sections.append(GeneratedSection(title=title, content_markdown=body))
    return sections


# ---------------------------------------------------------------------------
# Sample-report section matching (used by the agentic path only)
# ---------------------------------------------------------------------------


def _split_sample_sections(sample_markdown: str) -> dict[str, tuple[str, str]]:
    """Split a sample report at its top-level report-section headings.

    Sample reports must use ``##`` Markdown headings for their main sections.
    Detects the shallowest heading level *below* a single document title
    (typically ``##``) and splits only on that level, so each returned block
    keeps its own ``###``/``####`` subsections intact. Returns
    ``{normalized_heading: (original_heading, section_markdown)}`` where the
    section markdown includes the heading line itself.
    """
    if not sample_markdown:
        return {}
    lines = sample_markdown.splitlines()
    headings: list[tuple[int, int, str]] = []  # (line_index, level, text)
    for i, line in enumerate(lines):
        m = re.match(r"^(#{1,6})\s+(.*\S)\s*$", line)
        if m:
            headings.append((i, len(m.group(1)), m.group(2).strip()))
    if not headings:
        return {}

    levels = sorted({lvl for _, lvl, _ in headings})
    top_level = levels[0]
    top_count = sum(1 for _, lvl, _ in headings if lvl == top_level)
    # A single top-level heading is the document title -> sections live one level down.
    if top_count == 1 and len(levels) > 1:
        section_level = levels[1]
    else:
        section_level = top_level

    section_heads = [(i, text) for (i, lvl, text) in headings if lvl == section_level]
    out: dict[str, tuple[str, str]] = {}
    for k, (idx, text) in enumerate(section_heads):
        end = section_heads[k + 1][0] if k + 1 < len(section_heads) else len(lines)
        body = "\n".join(lines[idx:end]).strip()
        norm = _normalize_heading(text)
        if norm and norm not in out:
            out[norm] = (text, body)
    return out


def _match_sample_section(title: str, sample_sections: dict[str, tuple[str, str]]) -> str | None:
    """Match a requested section title to one sample section block, or None.

    Tries an exact heading match first, then a normalized match.
    """
    if not sample_sections:
        return None
    for _norm, (orig, body) in sample_sections.items():
        if orig.strip() == title.strip():
            return body
    match = sample_sections.get(_normalize_heading(title))
    return match[1] if match else None


# ---------------------------------------------------------------------------
# Heading-aware sample report extractors
# ---------------------------------------------------------------------------


def _extract_sample_pdf(path: Path) -> str:
    """Extract a PDF sample report as Markdown with heading structure.

    Uses pymupdf4llm when available (detects headings from font sizes), falling
    back to plain PyMuPDF text extraction.  Proper ``##`` headings are required
    for ``_split_sample_sections`` to find section boundaries.
    """
    try:
        import pymupdf4llm

        return pymupdf4llm.to_markdown(str(path))
    except ImportError:
        pass
    # Fallback: plain text (section matching will not work without headings,
    # but at least the sample content reaches the writer as a style hint).
    import fitz

    doc = fitz.open(str(path))
    pages = [doc[i].get_text() for i in range(doc.page_count)]
    doc.close()
    return "\n\n".join(pages).strip()


def _extract_sample_docx(path: Path) -> str:
    """Extract a DOCX sample report as Markdown with heading structure.

    Maps Word heading styles (Heading 1 … Heading 6) to Markdown ``#`` markers
    so that ``_split_sample_sections`` can detect section boundaries.  Body text
    is included as-is.
    """
    from docx import Document  # python-docx

    doc = Document(str(path))
    lines: list[str] = []
    for para in doc.paragraphs:
        text = para.text.strip()
        if not text:
            continue
        style_name = para.style.name if para.style else ""
        if style_name.startswith("Heading"):
            # "Heading 1" → 1, "Heading 2" → 2, …
            parts = style_name.split()
            try:
                level = int(parts[-1])
            except (ValueError, IndexError):
                level = 2
            level = max(1, min(level, 6))
            lines.append(f"{'#' * level} {text}")
        else:
            lines.append(text)
    return "\n\n".join(lines)


# ---------------------------------------------------------------------------
# Main module
# ---------------------------------------------------------------------------


class MultiSourceReportGenerator:
    """Generate a user-defined Markdown report from many mixed source files.

    Example
    -------
    >>> gen = MultiSourceReportGenerator(use_azure=True)
    >>> result = gen.run(
    ...     input_paths=["materials/"],
    ...     report_title="Project Assessment",
    ...     sections=[{"title": "Findings", "instructions": "Summarize key findings."}],
    ...     output_dir="output/report",
    ... )
    >>> print(result.markdown_path)
    """

    def __init__(
        self,
        *,
        api_config: dict | None = None,
        use_azure: bool = True,
        limits: InputLimits | None = None,
    ) -> None:
        """
        Args:
            api_config: Shared LLM config; read from the environment when omitted.
            use_azure: With no ``api_config``, read the Azure OpenAI config.
            limits: Input limits for every parser, transcriber and image extractor
                this module builds; a ``ctor`` option that sets its own ``limits``
                wins. ``None`` keeps each component's defaults. A file over one
                raises ``InputLimitError``.
        """
        if api_config is None:
            from gaik.software_components.config import get_openai_config

            api_config = get_openai_config(use_azure=use_azure)
        self.api_config = api_config
        self.limits = limits

    def _limited(self, ctor: dict) -> dict:
        """A copy of ``ctor`` with this generator's ``limits``, unless it sets its own."""
        if self.limits is None:
            return dict(ctor)
        return {"limits": self.limits, **ctor}

    # -- public API -------------------------------------------------------

    def run(
        self,
        *,
        input_paths: list[str | Path],
        sections: list[ReportSectionSpec | dict[str, Any]],
        report_title: str = "Generated Report",
        report_description: str | None = None,
        additional_instructions: str | None = None,
        report_language: str | None = None,
        sample_report_path: str | Path | None = None,
        output_dir: str | Path | None = None,
        include_evidence_index: bool = True,
        include_source_references: bool = True,
        max_evidence_chars: int | None = None,
        section_context_mode: str = "all_evidence",
        parser_choice: str = "auto",
        parser_options: dict | None = None,
        transcriber_options: dict | None = None,
        image_options: dict | None = None,
        writer_options: dict | None = None,
        agentic: bool = False,
        review_options: dict | None = None,
        polish: bool = False,
        strict_review: bool = True,
        curate_evidence: bool = False,
        verbose: bool = False,
        progress_callback: Callable[[str], None] | None = None,
        output_docx: bool = False,
    ) -> ReportGenerationResult:
        """Build evidence from ``input_paths`` and write each requested section.

        By default the whole report is written in a single LLM call. Set
        ``agentic=True`` to use the opt-in agentic workflow (independent
        per-section drafting + mandatory diff-editor review); it requires the
        ``multi-source-report-generator-agentic`` extra (``langgraph``).
        """
        specs = _normalize_sections(sections)

        parser_options = parser_options or {}
        transcriber_options = transcriber_options or {}
        image_options = image_options or {}
        writer_options = writer_options or {}

        # 1. Build evidence (shared by both paths).
        evidence_items, evidence_sources, evidence_pack, sample_markdown = self._build_evidence(
            input_paths=input_paths,
            parser_choice=parser_choice,
            parser_options=parser_options,
            transcriber_options=transcriber_options,
            image_options=image_options,
            sample_report_path=sample_report_path,
            max_evidence_chars=max_evidence_chars,
            progress_callback=progress_callback,
        )

        # Suppress inline citations when there is only one source — nothing
        # to distinguish between sources, so citations add noise.
        if len(evidence_items) <= 1:
            include_source_references = False

        source_filenames = [item.metadata.get("filename", "") for item in evidence_items]
        # Every file this run writes under output_dir, for the record of its outputs.
        written: list[Path] = []

        # 2. Write the report — either the agentic path or the single LLM call.
        if agentic:
            markdown, generated, usage_total = self._run_agentic(
                specs=specs,
                evidence_pack=evidence_sources,
                sample_markdown=sample_markdown,
                output_dir=output_dir,
                report_title=report_title,
                report_description=report_description,
                additional_instructions=additional_instructions,
                report_language=report_language,
                include_source_references=include_source_references,
                source_filenames=source_filenames,
                writer_options=writer_options,
                review_options=review_options,
                polish=polish,
                strict_review=strict_review,
                curate_evidence=curate_evidence,
                verbose=verbose,
                progress_callback=progress_callback,
                written_files=written,
            )
        else:
            # Write the whole report in a single LLM call (so a sample report's
            # format applies to the report as a whole, not per section).
            client = self._build_llm_client(writer_options)
            chat_kwargs = {
                k: v
                for k, v in writer_options.items()
                if k not in ("model", "provider", "api_config") and v is not None
            }

            response = self._write_report(
                client,
                specs=specs,
                evidence_pack=evidence_sources,
                report_title=report_title,
                report_description=report_description,
                additional_instructions=additional_instructions,
                report_language=report_language,
                include_source_references=include_source_references,
                source_filenames=source_filenames,
                sample_markdown=sample_markdown,
                chat_kwargs=chat_kwargs,
            )
            markdown = _normalize_report_markdown(response.text, report_title)
            usage_total = (
                {k: v for k, v in response.usage.items() if isinstance(v, int)}
                if getattr(response, "usage", None)
                else {}
            )
            generated = _split_into_sections(markdown, specs)

        # 3. Write outputs
        markdown_path: Path | None = None
        docx_path: Path | None = None
        if output_dir is not None:
            markdown_path = self._write_outputs(
                output_dir,
                report_title=report_title,
                markdown=markdown,
                sections=generated,
                evidence_items=evidence_items,
                evidence_pack=evidence_pack,
                usage=usage_total,
                include_evidence_index=include_evidence_index,
                written=written,
            )
            if output_docx and markdown_path is not None:
                docx_path = self._write_docx(markdown_path)
                written.append(docx_path)
            # Only now that this run's outputs are all written: an earlier run's files
            # that this run did not replace are removed if they are unchanged.
            _replace_earlier_outputs(Path(output_dir), written)

        return ReportGenerationResult(
            title=report_title,
            evidence_items=evidence_items,
            sections=generated,
            markdown=markdown,
            markdown_path=markdown_path,
            usage=usage_total,
            docx_path=docx_path,
        )

    # -- shared evidence building -----------------------------------------

    def _build_evidence(
        self,
        *,
        input_paths: list[str | Path],
        parser_choice: str,
        parser_options: dict,
        transcriber_options: dict,
        image_options: dict,
        sample_report_path: str | Path | None,
        max_evidence_chars: int | None,
        progress_callback: Callable[[str], None] | None = None,
    ) -> tuple[list[EvidenceItem], list[EvidenceSource], str, str | None]:
        """Normalize all inputs to evidence sources and a pack (+ optional sample markdown).

        Each source reaches a model in its own block, labelled with its file name;
        the pack is the same text as plain Markdown, for ``normalized_sources.md``.

        Shared by the single-call and agentic paths. When ``progress_callback``
        is provided, normalization progress is routed through it instead of
        ``print`` so callers (e.g. the demo SSE backend) receive the messages, each
        file by its name. The default ``print`` names a file by its tag
        (``file 3f9a1c2b.pdf``), as the parsers' log lines do: stdout often ends up in
        a log, and a file name can carry personal data.
        """
        _emit = progress_callback or print
        _name = (lambda p: p.name) if progress_callback else file_tag

        files = _collect_input_files(input_paths)
        if not files:
            raise ValueError(
                "No supported source files found in `input_paths`. "
                f"Supported extensions: {sorted(SUPPORTED_EXTENSIONS)}"
            )

        total = len(files)
        evidence_items: list[EvidenceItem] = []
        for index, path in enumerate(files, start=1):
            source_type = _EXT_TO_TYPE[path.suffix.lower()]
            _emit(f"Normalizing [{index}/{total}]: {_name(path)} ({source_type})")
            evidence_items.append(
                self._build_evidence_item(
                    path,
                    index=index,
                    parser_choice=parser_choice,
                    parser_options=parser_options,
                    transcriber_options=transcriber_options,
                    image_options=image_options,
                )
            )

        evidence_sources = self._evidence_sources(
            evidence_items, max_evidence_chars=max_evidence_chars
        )
        evidence_pack = self._render_evidence_pack(evidence_sources)
        _emit(f"Evidence pack assembled: {total} source(s), {len(evidence_pack):,} chars")

        sample_markdown: str | None = None
        if sample_report_path is not None:
            sample_markdown = self._extract_sample_report(
                sample_report_path,
                parser_choice=parser_choice,
                parser_options=parser_options,
            )
            if max_evidence_chars is not None and len(sample_markdown) > max_evidence_chars:
                sample_markdown = (
                    sample_markdown[:max_evidence_chars] + "\n\n[... sample report truncated ...]"
                )

        return evidence_items, evidence_sources, evidence_pack, sample_markdown

    # -- agentic path -----------------------------------------------------

    def _run_agentic(
        self,
        *,
        specs: list[ReportSectionSpec],
        evidence_pack: Evidence,
        sample_markdown: str | None,
        output_dir: str | Path | None,
        report_title: str,
        report_description: str | None,
        additional_instructions: str | None,
        report_language: str | None,
        include_source_references: bool,
        source_filenames: list[str],
        writer_options: dict,
        review_options: dict | None,
        polish: bool,
        strict_review: bool,
        curate_evidence: bool,
        verbose: bool,
        progress_callback: Callable[[str], None] | None,
        written_files: list[Path] | None = None,
    ) -> tuple[str, list[GeneratedSection], dict]:
        from .agentic import run_agentic_report
        from .progress import ProgressReporter

        reporter = ProgressReporter(verbose=verbose, callback=progress_callback)

        writer_client = self._build_llm_client(writer_options)
        writer_kwargs = {
            k: v
            for k, v in writer_options.items()
            if k not in ("model", "provider", "api_config") and v is not None
        }

        # Reviewer client: a separate model via review_options, else reuse the writer.
        if review_options:
            reviewer_client = self._build_llm_client(review_options)
            reviewer_kwargs = {
                k: v
                for k, v in review_options.items()
                if k not in ("model", "provider", "api_config") and v is not None
            }
        else:
            reviewer_client = writer_client
            reviewer_kwargs = writer_kwargs

        # Split the sample by heading and resolve a matched block per section
        # here (so the agentic package never imports pipeline internals).
        sample_sections = _split_sample_sections(sample_markdown) if sample_markdown else {}
        matched_samples = {
            spec.title: _match_sample_section(spec.title, sample_sections) for spec in specs
        }

        markdown, generated, usage_total = run_agentic_report(
            specs=specs,
            evidence_pack=evidence_pack,
            matched_samples=matched_samples,
            report_description=report_description,
            additional_instructions=additional_instructions,
            sample_report_provided=sample_markdown is not None,
            output_dir=output_dir,
            report_title=report_title,
            report_language=report_language,
            include_source_references=include_source_references,
            source_filenames=source_filenames,
            writer_client=writer_client,
            writer_kwargs=writer_kwargs,
            reviewer_client=reviewer_client,
            reviewer_kwargs=reviewer_kwargs,
            curate_evidence=curate_evidence,
            polish=polish,
            strict_review=strict_review,
            reporter=reporter,
            written_files=written_files,
        )
        return _normalize_report_markdown(markdown, report_title), generated, usage_total

    # -- evidence building ------------------------------------------------

    def _build_evidence_item(
        self,
        path: Path,
        *,
        index: int,
        parser_choice: str,
        parser_options: dict,
        transcriber_options: dict,
        image_options: dict,
    ) -> EvidenceItem:
        source_type = _EXT_TO_TYPE[path.suffix.lower()]
        content = self._extract_content(
            path,
            source_type=source_type,
            parser_choice=parser_choice,
            parser_options=parser_options,
            transcriber_options=transcriber_options,
            image_options=image_options,
        )
        metadata = {
            "index": index,
            "filename": path.name,
            "extension": path.suffix.lower(),
            "detected_type": source_type,
            "size_bytes": path.stat().st_size if path.exists() else None,
        }
        return EvidenceItem(
            source_path=str(path),
            source_type=source_type,
            content_markdown=content,
            metadata=metadata,
        )

    def _extract_content(
        self,
        path: Path,
        *,
        source_type: str,
        parser_choice: str,
        parser_options: dict,
        transcriber_options: dict,
        image_options: dict,
    ) -> str:
        if source_type in ("text", "markdown"):
            return path.read_text(encoding="utf-8-sig", errors="replace")
        if source_type == "csv":
            return _csv_to_markdown(path)
        if source_type == "xlsx":
            return _xlsx_to_markdown(path)
        if source_type == "pdf":
            return self._parse_pdf(path, parser_choice=parser_choice, parser_options=parser_options)
        if source_type == "docx":
            return self._parse_docx(path)
        if source_type in ("audio", "video"):
            return self._transcribe(path, transcriber_options=transcriber_options)
        if source_type == "image":
            return self._parse_image(path, image_options=image_options)
        # Should never happen — _collect_input_files filters unsupported types.
        raise ValueError(f"Unsupported source type '{source_type}' for {path}")

    def _extract_sample_report(
        self, sample_report_path: str | Path, *, parser_choice: str, parser_options: dict
    ) -> str:
        """Parse an optional sample/template report to markdown.

        Supports text, Markdown, PDF, and DOCX. The result is used as a strict
        format/style template by the writer — never as content.

        PDF and DOCX files are parsed with heading-aware extraction so that
        ``_split_sample_sections`` can detect section boundaries from Markdown
        heading markers (``##``).  Plain text/Markdown files are read as-is.
        """
        path = Path(sample_report_path)
        if not path.exists():
            raise FileNotFoundError(f"sample_report_path does not exist: {path}")
        ext = path.suffix.lower()
        source_type = _EXT_TO_TYPE.get(ext)
        if source_type not in ("text", "markdown", "pdf", "docx"):
            raise ValueError(
                f"Unsupported sample report type '{ext}'. "
                "Use one of: .txt, .md, .markdown, .pdf, .docx"
            )
        if source_type in ("text", "markdown"):
            return path.read_text(encoding="utf-8-sig", errors="replace")
        if source_type == "pdf":
            return _extract_sample_pdf(path)
        # docx
        return _extract_sample_docx(path)

    def _parse_pdf(self, path: Path, *, parser_choice: str, parser_options: dict) -> str:
        choice = (parser_choice or "auto").lower()
        if choice == "auto":
            choice = "pymupdf"  # local, no API cost; deterministic default for V1

        if choice == "pymupdf":
            from gaik.software_components.parsers import PyMuPDFParser

            return PyMuPDFParser(limits=self.limits).parse_pdf(str(path), use_markdown=True)
        if choice in ("vision", "vision_parser"):
            from gaik.software_components.parsers import VisionParser

            cfg = (
                parser_options.get("api_config")
                or parser_options.get("openai_config")
                or self.api_config
            )
            ctor = self._limited(parser_options.get("ctor", {}))
            pages = VisionParser(cfg, **ctor).convert_pdf(str(path))
            return "\n\n".join(pages)
        if choice == "multimodal":
            from gaik.software_components.parsers import MultimodalParser

            ctor = self._limited(self._shared_ctor(parser_options))
            result = MultimodalParser(**ctor).parse(str(path))
            return result.clean_markdown or result.raw_markdown
        if choice == "docling":
            from gaik.software_components.parsers import DoclingParser

            ctor = self._limited(parser_options.get("ctor", {}))
            result = DoclingParser(**ctor).parse_document(str(path))
            # parse_document returns a dict with the Markdown under "text_content".
            if isinstance(result, dict) and isinstance(result.get("text_content"), str):
                return result["text_content"]
            return _coerce_markdown(result)
        raise ValueError(
            f"Unknown parser_choice '{parser_choice}'. "
            "Use one of: auto, pymupdf, vision, multimodal, docling."
        )

    def _parse_docx(self, path: Path) -> str:
        from gaik.software_components.parsers import DocxParser

        # Document order, headings and every table cell (an empty one too), as
        # SourceNormalizer reads a DOCX; the simple mode drops headings and empty
        # cells and puts every table after the paragraphs.
        return DocxParser(limits=self.limits).parse_docx(
            str(path), use_markdown=True, keep_structure=True
        )

    def _transcribe(self, path: Path, *, transcriber_options: dict) -> str:
        from gaik.software_components.transcriber import Transcriber

        ctor = self._limited(transcriber_options.get("ctor", {}))
        ctor.setdefault("api_config", self.api_config)
        transcriber = Transcriber(**ctor)
        result = transcriber.transcribe(str(path), **transcriber_options.get("call", {}))
        return result.enhanced_transcript or result.raw_transcript

    def _shared_ctor(self, options: dict) -> dict:
        """Constructor kwargs for MultimodalParser/VisionExtractor.

        A ctor that selects its own legacy backend (model_provider, use_azure,
        vertex_ai) keeps it, as before 0.8.0. Otherwise the stage or report config
        is shared, and a ctor reasoning_effort travels inside that config.
        """
        ctor = dict(options.get("ctor", {}))
        if options.get("api_config") is not None:
            ctor.setdefault("api_config", options["api_config"])
        elif not {"model_provider", "use_azure", "vertex_ai"} & ctor.keys():
            effort = ctor.pop("reasoning_effort", None)
            config = self.api_config
            if effort is not None:
                config = {**config, "reasoning_effort": effort}
            ctor.setdefault("api_config", config)
        return ctor

    def _parse_image(self, path: Path, *, image_options: dict) -> str:
        from gaik.software_components.file_type import IMAGE_TYPES, check_file_type

        # The content decides, as in VisionParser: a PNG named .bmp is sent as it is,
        # a TIFF named .png is converted. A file that cannot be read or is no image
        # goes on as it is, for the parser to report as before.
        try:
            detected = check_file_type(path, IMAGE_TYPES)
        except (OSError, ValueError):
            detected = None
        if detected in _CONVERTED_IMAGE_TYPES:
            # TIFF and BMP go to the model as PNG, one per page of a multi-page TIFF.
            limits = self._limited(image_options.get("ctor", {})).get("limits")
            with tempfile.TemporaryDirectory(prefix="gaik-image-") as folder:
                pages = _as_png_pages(path, Path(folder), limits or InputLimits())
                return self._parse_image_files(pages, image_options=image_options)
        return self._parse_image_files([path], image_options=image_options)

    def _parse_image_files(self, paths: list[Path], *, image_options: dict) -> str:
        mode = image_options.get("mode", "parse")  # "parse" | "structured"
        if mode == "structured":
            from gaik.software_components.vision_extractor import VisionExtractor

            extractor = VisionExtractor(**self._limited(self._shared_ctor(image_options)))
            user_requirements = image_options.get(
                "user_requirements",
                "Extract all visible text, tables, figures, and structured content from the image.",
            )
            result = extractor.extract(
                file_paths=[str(p) for p in paths], user_requirements=user_requirements
            )
            return _dict_to_markdown(result.data)

        # default: general parsing to markdown via VisionParser.convert_image()
        from gaik.software_components.parsers import VisionParser

        cfg = (
            image_options.get("api_config") or image_options.get("openai_config") or self.api_config
        )
        ctor = self._limited(image_options.get("ctor", {}))
        parser = VisionParser(cfg, **ctor)
        if len(paths) == 1:
            return parser.convert_image(str(paths[0]))
        return "\n\n".join(
            f"[Page {n}]\n\n{parser.convert_image(str(p))}" for n, p in enumerate(paths, start=1)
        )

    def _evidence_sources(
        self, evidence_items: list[EvidenceItem], *, max_evidence_chars: int | None
    ) -> list[EvidenceSource]:
        """The sources as the writer receives them, cut to ``max_evidence_chars``.

        The budget counts the headings and texts as ``_render_evidence_pack``
        writes them; the source that crosses it is cut and the later ones are left out.
        Labels are file names, never paths.
        """
        sources: list[EvidenceSource] = []
        used = 0
        for item in evidence_items:
            meta = item.metadata
            name = clean_label(str(meta.get("filename") or Path(item.source_path).name))
            heading = f"Source {meta.get('index')}: {name} ({item.source_type})"
            text = item.content_markdown
            source = partial(
                EvidenceSource, name, heading, index=meta.get("index"), source_type=item.source_type
            )
            cost = (len(_SOURCE_SEPARATOR) if sources else 0) + len(f"## {heading}\n\n")
            if max_evidence_chars is not None and used + cost + len(text) > max_evidence_chars:
                room = max_evidence_chars - used - cost
                if room > 0 or not sources:
                    # The first source stays, even with no text, so the cut is visible.
                    text = text[: max(room, 0)]
                    sources.append(source(text, truncated=True))
                else:
                    sources[-1] = replace(sources[-1], truncated=True)
                logger.warning(
                    "Evidence (%d sources) exceeds max_evidence_chars (%d); truncating.",
                    len(evidence_items),
                    max_evidence_chars,
                )
                break
            sources.append(source(text))
            used += cost + len(text)
        return sources

    def _assemble_evidence_pack(
        self, evidence_items: list[EvidenceItem], *, max_evidence_chars: int | None
    ) -> str:
        """The evidence as plain Markdown, for ``evidence/normalized_sources.md``.

        It names each source by its file name and type; the source path stays in
        ``evidence_index.json``.
        """
        return self._render_evidence_pack(
            self._evidence_sources(evidence_items, max_evidence_chars=max_evidence_chars)
        )

    @staticmethod
    def _render_evidence_pack(sources: list[EvidenceSource]) -> str:
        pack = _SOURCE_SEPARATOR.join(f"## {s.heading}\n\n{s.text}" for s in sources)
        if any(s.truncated for s in sources):
            pack += f"\n\n{TRUNCATED_NOTE}"
        return pack

    # -- writing ----------------------------------------------------------

    def _build_llm_client(self, writer_options: dict):
        if create_llm_client is None:
            raise ImportError(
                "The LLM client could not be imported. Install the base GAIK "
                "dependencies (openai) to run the report writer."
            )
        from gaik.software_components.llm import get_llm_config, resolve_provider

        cfg = dict(writer_options.get("api_config") or self.api_config)
        requested_provider = writer_options.get("provider")
        if requested_provider and resolve_provider(requested_provider) != resolve_provider(
            config=cfg
        ):
            # Provider switches must load that provider's credentials. Carrying
            # api_key/base_url across providers can send a key to the wrong service.
            model_override = (
                {"model": writer_options["model"]} if writer_options.get("model") else {}
            )
            cfg = get_llm_config(requested_provider, **model_override)
        if writer_options.get("model"):
            cfg["model"] = writer_options["model"]
        return create_llm_client(cfg)

    def _write_report(
        self,
        client,
        *,
        specs: list[ReportSectionSpec],
        evidence_pack: Evidence,
        report_title: str,
        report_description: str | None,
        additional_instructions: str | None,
        report_language: str | None,
        include_source_references: bool,
        source_filenames: list[str],
        sample_markdown: str | None,
        chat_kwargs: dict,
    ):
        """Write the entire report in one LLM call and return the raw response.

        Each source and the format reference go in their own block; the task, the
        sections and the additional instructions stay outside them.
        """
        blocks = SourceMaterial()
        parts = [f"Report title: {report_title}"]
        if report_description:
            parts.append(f"Report context and purpose: {report_description}")
        if report_language:
            parts.append(f"Write the report in: {report_language}")
        if include_source_references:
            parts.append(
                "Where useful, cite the source that supports a claim using its exact filename "
                "in parentheses, e.g. (notes.txt) or (meeting_recording.mp3). "
                f"Available sources: {source_list(source_filenames)}."
            )
        else:
            parts.append("Do not add inline source citations or filename references in the text.")

        # Present the sample BEFORE the section instructions so the model internalises
        # the expected tone/structure/format (layout, list style, brevity) before
        # reading what content to put in each section.
        if sample_markdown:
            parts.append(
                "FORMAT REFERENCE — governs both structure AND length for every section. "
                "This example is most likely about a DIFFERENT subject. "
                "Mirror it exactly:\n"
                "  • Structure: how each section is laid out internally, list style "
                "(prose/bullets/numbered), bold lead-ins, citation style.\n"
                "  • Length: each section you write should be approximately the same "
                "total length and density as the corresponding section in this reference "
                "— same number of paragraphs or bullet points, similar per-item length. "
                "Do not add extra content to be thorough; do not pad.\n"
                "  • Content: take NONE of its facts, names, numbers, or wording. Every "
                "fact must come from the EVIDENCE below. Section titles come from the "
                "required list. The reference is in the source_material block labelled "
                "format_reference.\n\n" + blocks.wrap(sample_markdown, label="format_reference")
            )

        # Section definitions: use a numbered, titled format so the model never
        # echoes a "SECTION:" prefix into the output headings.
        section_lines = ["Required sections (write each as `## <title>` in this exact order):"]
        for i, spec in enumerate(specs, start=1):
            section_lines.append(f"\n{i}. Heading: {spec.title}")
            section_lines.append(f"   Content to cover: {spec.instructions}")
        parts.append("\n".join(section_lines))

        parts.append(
            "Evidence — this is the ONLY source of facts and content for the report (one "
            f"source_material block per source, labelled with its file name; "
            f"{SOURCE_HEADER_NOTE}):\n" + render_evidence(blocks, evidence_pack)
        )

        if additional_instructions:
            parts.append(f"ADDITIONAL INSTRUCTIONS:\n{additional_instructions}")

        closing = [
            f"Now write the complete report. Start with `# {report_title}`, then write "
            "every required section in order using `## <exact heading title>`."
        ]
        if sample_markdown:
            closing.append(
                "Follow the FORMAT REFERENCE's layout, style, AND length — each section "
                "should be approximately as long as the corresponding reference section. "
                "Ignore its subject matter entirely; all facts come from the evidence."
            )
        else:
            closing.append("Write in a clean, professional report format.")
        closing.append("Use only the evidence for content.")
        parts.append(" ".join(closing))
        user_prompt = "\n\n".join(parts)

        response = client.chat(
            [
                {"role": "system", "content": with_source_material_instruction(_SYSTEM_PROMPT)},
                {"role": "user", "content": user_prompt},
            ],
            **chat_kwargs,
        )
        if isinstance(getattr(response, "text", None), str):
            response.text = blocks.strip_echo(response.text)
        return response

    # -- outputs ----------------------------------------------------------

    def _write_outputs(
        self,
        output_dir: str | Path,
        *,
        report_title: str,
        markdown: str,
        sections: list[GeneratedSection],
        evidence_items: list[EvidenceItem],
        evidence_pack: str,
        usage: dict[str, int],
        include_evidence_index: bool,
        written: list[Path] | None = None,
    ) -> Path:
        """Write the report, its sections and evidence files; add each to ``written``."""
        written = written if written is not None else []
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        (out / "sections").mkdir(exist_ok=True)
        (out / "evidence").mkdir(exist_ok=True)

        report_path = out / "report.md"
        report_path.write_text(markdown, encoding="utf-8")
        written.append(report_path)

        for i, s in enumerate(sections, start=1):
            name = f"{i:02d}_{_slug(s.title)}.md"
            (out / "sections" / name).write_text(
                f"## {s.title}\n\n{s.content_markdown.strip()}\n", encoding="utf-8"
            )
            written.append(out / "sections" / name)

        (out / "evidence" / "normalized_sources.md").write_text(evidence_pack, encoding="utf-8")
        written.append(out / "evidence" / "normalized_sources.md")

        if include_evidence_index:
            index = [
                {
                    "source_path": e.source_path,
                    "source_type": e.source_type,
                    "metadata": e.metadata,
                    "content_chars": len(e.content_markdown),
                }
                for e in evidence_items
            ]
            (out / "evidence_index.json").write_text(
                json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            written.append(out / "evidence_index.json")

        if usage:
            (out / "usage.json").write_text(
                json.dumps(usage, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            written.append(out / "usage.json")

        return report_path

    def _write_docx(self, md_path: Path) -> Path:
        """Convert a Markdown file to DOCX using Pandoc via pypandoc.

        Requires the ``multi-source-report-generator-docx`` extra and the
        Pandoc system binary (https://pandoc.org/installing.html).
        """
        try:
            import pypandoc  # noqa: F401  (checked here for the install hint)
        except ImportError as exc:
            raise ImportError(
                "DOCX export requires 'pypandoc' and the Pandoc system binary. "
                "Install the Python wrapper with:\n"
                '    pip install "gaik[multi-source-report-generator-docx]"\n'
                "Then install Pandoc from https://pandoc.org/installing.html "
                "(or: winget install JohnMacFarlane.Pandoc / brew install pandoc / "
                "apt install pandoc)."
            ) from exc
        from gaik.software_components._pandoc import markdown_file_to_docx

        return markdown_file_to_docx(md_path, md_path.with_suffix(".docx"))


# ---------------------------------------------------------------------------
# The record of a run's outputs
# ---------------------------------------------------------------------------

OUTPUT_RECORD = ".gaik_report_files.json"
"""The file in ``output_dir`` that lists the files a run wrote, with their SHA-256."""


_GENERATED_FILES = frozenset(
    {
        "report.md",
        "report.docx",
        "usage.json",
        "evidence_index.json",
        "evidence/normalized_sources.md",
    }
)
_GENERATED_FOLDERS = ("sections", "evidence/curated_sections")  # their *.md files


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _same_file_key(path: Path) -> str | None:
    """``path`` resolved, in the platform's case, for comparing files; None if it cannot be."""
    try:
        return os.path.normcase(str(path.resolve()))
    except (OSError, ValueError, RuntimeError):
        return None


def _generated_name(rel: str) -> PurePosixPath | None:
    """``rel`` as a path the generator writes (``report.md``, ``sections/<x>.md``, ...),
    or None for any other name, an absolute path, ``..``, a backslash or a NUL."""
    if not isinstance(rel, str) or "\\" in rel or "\x00" in rel:
        return None
    pure = PurePosixPath(rel)
    if pure.is_absolute() or ".." in pure.parts or not pure.parts:
        return None
    text = pure.as_posix()
    if text in _GENERATED_FILES:
        return pure
    if pure.suffix == ".md" and pure.parent.as_posix() in _GENERATED_FOLDERS:
        return pure
    return None


def _replace_earlier_outputs(out: Path, written: list[Path]) -> None:
    """Record this run's files in ``out``; remove the earlier run's files it did not write.

    One output folder holds one report, the one written last. A reused folder would
    otherwise keep, next to this report, the file of a section that was removed or
    renamed, a curated brief, an ``evidence_index.json``, ``usage.json`` or
    ``report.docx`` that this run did not write. The same holds for a second, different
    report written into the folder: it replaces the first one's generated files. A file
    is removed only when all of this holds: the record of the run before lists it, it
    is one of the names the generator writes, it still has the content written then, it
    is not a link, it resolves inside the folder, and it is not a file this run wrote
    (compared by resolved path, so another spelling of a name cannot point at one).
    Everything else stays: your own files, files you changed, and files from a run
    before the record existed; a warning counts them. A record that cannot be read, or
    is a link, removes nothing.
    """
    base = out.resolve()
    written_keys = {key for p in written if (key := _same_file_key(Path(p))) is not None}
    now: dict[str, str] = {}
    for path in written:
        path = Path(path)
        try:
            if not path.resolve().is_relative_to(base):
                continue  # a written file that is not inside the folder is not recorded
            # The name as written (sections/01_x.md), not as the drive spells its
            # folders, so the allowlist recognises it in the next run.
            now[path.relative_to(out).as_posix()] = _digest(path)
        except (OSError, ValueError):
            continue

    record = out / OUTPUT_RECORD
    earlier: dict = {}
    if record.is_symlink():
        logger.warning(
            "The output record %s is a link; it is neither read nor written", OUTPUT_RECORD
        )
    else:
        try:
            data = json.loads(record.read_text(encoding="utf-8-sig"))
            if isinstance(data, dict) and isinstance(data.get("files"), dict):
                earlier = data["files"]
        except (OSError, ValueError):
            pass

    removed = changed = 0
    for rel, digest in earlier.items():
        pure = _generated_name(rel)
        if pure is None or not isinstance(digest, str):
            continue
        path = out.joinpath(*pure.parts)
        key = _same_file_key(path)
        if key is None or key in written_keys:
            continue  # never a file this run wrote, whatever the record says
        if key != os.path.normcase(str(base.joinpath(*pure.parts))):
            continue  # a link or junction somewhere under the folder, even one inside it
        try:
            if path.is_symlink() or not path.is_file():
                continue
            if not path.resolve().is_relative_to(base):
                continue  # through a linked folder out of the output folder
            if _digest(path) != digest:
                changed += 1
                continue
            path.unlink()
            removed += 1
        except (OSError, ValueError):
            continue
    if removed:
        logger.info("Removed %d file(s) of the previous run that this run did not write", removed)
    if changed:
        logger.warning(
            "Kept %d file(s) of the previous run that were changed after it wrote them; "
            "they are not part of this report",
            changed,
        )

    stray = 0
    for folder in _GENERATED_FOLDERS:
        found_folder = out / folder
        if not found_folder.is_dir():
            continue
        for found in found_folder.glob("*.md"):
            if _same_file_key(found) not in written_keys:
                stray += 1
    if stray:
        logger.warning(
            "The output folder keeps %d section or brief file(s) this run did not write; "
            "they are not part of this report",
            stray,
        )

    if not record.is_symlink():
        try:
            record.write_text(json.dumps({"files": now}, indent=2) + "\n", encoding="utf-8")
        except OSError:
            logger.warning("Could not write the output record %s", OUTPUT_RECORD)


# ---------------------------------------------------------------------------
# Config save / load
# ---------------------------------------------------------------------------


def _check_input_folder(folder: Path, root: str | Path) -> None:
    """Raise ``SourcePathError`` for a supported file in ``folder`` that leads out of
    ``root``, e.g. through a symbolic link: it would become source material."""
    for found in sorted(folder.rglob("*")):
        if found.suffix.lower() in SUPPORTED_EXTENSIONS and found.is_file():
            path_inside(found.relative_to(folder), folder, root=root, what="input file")


def save_report_config(
    path: str | Path,
    *,
    input_paths: list[str | Path],
    sections: list[ReportSectionSpec | dict[str, Any]],
    report_title: str = "Generated Report",
    report_description: str | None = None,
    additional_instructions: str | None = None,
    report_language: str | None = None,
    sample_report_path: str | Path | None = None,
    output_dir: str | Path | None = None,
    output_docx: bool = False,
    include_evidence_index: bool = True,
    include_source_references: bool = True,
    max_evidence_chars: int | None = None,
    parser_choice: str = "auto",
    parser_options: dict | None = None,
    transcriber_options: dict | None = None,
    image_options: dict | None = None,
    writer_options: dict | None = None,
    agentic: bool = False,
    review_options: dict | None = None,
    polish: bool = False,
    strict_review: bool = True,
    curate_evidence: bool = False,
    root: str | Path | None = None,
) -> Path:
    """Persist all ``run()`` parameters to a JSON config file for later reuse.

    Paths (``input_paths``, ``output_dir``, ``sample_report_path``) are stored
    relative to the config file's directory so the config is portable. Each one, and
    each supported file in an input folder, must stay inside ``root``, the config's
    folder by default, as ``load_report_config`` checks: one outside it (through
    ``..`` or a symbolic link) or on another drive raises ``SourcePathError`` and
    nothing is written, so a config saved without ``root`` loads without one. A config
    saved with a wider ``root`` stores ``..`` paths and needs the same ``root`` to
    load. A path that is a link is stored under its own name, as ``ReportSpec.save``
    does. All keys
    inside option dicts (``transcriber_options``, ``parser_options``, etc.) are
    stored as-is, except credential-bearing configs are rejected. Keep credentials
    in the environment and persist the provider/model selection instead.

    Not persisted: ``verbose``, ``progress_callback`` (runtime display), and
    ``section_context_mode`` (reserved/unused). Pass them directly to ``run()``
    as needed.
    """
    credential_keys = {
        "api_key",
        "api_token",
        "access_token",
        "azure_ad_token",
        "client_secret",
        "password",
        "service_account_json",
    }

    def _check_credentials(value: Any) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if str(key).lower() in credential_keys and item:
                    raise ValueError(
                        "Report config files must not contain credentials; use environment "
                        "variables and save provider/model options instead."
                    )
                _check_credentials(item)
        elif isinstance(value, (list, tuple)):
            for item in value:
                _check_credentials(item)

    _check_credentials(
        [parser_options, transcriber_options, image_options, writer_options, review_options]
    )
    config_path = Path(path)
    base = config_path.parent

    def _to_rel(p: str | Path | None, what: str) -> str | None:
        if p is None:
            return None
        # Made absolute first: a relative path is relative to the working directory
        # here, while load_report_config reads it relative to the config file. Only the
        # folder is resolved, as in ReportSpec.save: a link keeps its own name.
        p = Path(p)
        absolute = p.parent.resolve() / p.name
        try:
            rel = Path(os.path.relpath(absolute, base.resolve())).as_posix()
        except ValueError:
            raise SourcePathError(
                f"{p.name} is on another drive than the config file; a config stores "
                "paths relative to its own folder"
            ) from None
        # Refused here, as load_report_config would refuse it, not written for it to.
        joined = path_inside(rel, base, root=root, what=what)
        if what == "input path" and joined.is_dir():
            _check_input_folder(joined, root if root is not None else base)
        return rel

    # Normalise sections: dataclasses → plain dicts, preserve all fields.
    section_dicts: list[dict[str, Any]] = []
    for s in sections:
        if isinstance(s, ReportSectionSpec):
            section_dicts.append(
                {
                    "id": s.id,
                    "title": s.title,
                    "instructions": s.instructions,
                    "required": s.required,
                    "depends_on": list(s.depends_on),
                }
            )
        else:
            section_dicts.append(dict(s))

    config: dict[str, Any] = {
        "version": "1",
        "report_title": report_title,
        "report_description": report_description,
        "additional_instructions": additional_instructions,
        "report_language": report_language,
        "sections": section_dicts,
        "input_paths": [_to_rel(p, "input path") for p in input_paths],
        "sample_report_path": _to_rel(sample_report_path, "sample report"),
        "output_dir": _to_rel(output_dir, "output folder"),
        "output_docx": output_docx,
        "include_evidence_index": include_evidence_index,
        "include_source_references": include_source_references,
        "max_evidence_chars": max_evidence_chars,
        "parser_choice": parser_choice,
        "parser_options": parser_options or {},
        "transcriber_options": transcriber_options or {},
        "image_options": image_options or {},
        "writer_options": writer_options or {},
        "agentic": agentic,
        "review_options": review_options,
        "polish": polish,
        "strict_review": strict_review,
        "curate_evidence": curate_evidence,
    }

    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")
    return config_path


def load_report_config(path: str | Path, *, root: str | Path | None = None) -> dict[str, Any]:
    """Load a config file saved by ``save_report_config`` and return a dict
    that can be unpacked directly into ``MultiSourceReportGenerator.run()``.

    The input paths, the sample report and the output folder stored in the config are
    relative to the config file's directory and must stay inside ``root``, that
    directory by default. They are checked before anything is read or written, and so
    is every supported file in an input folder: an absolute path, or one that leads out
    of ``root`` through ``..`` or a symbolic link, raises ``SourcePathError``. Pass a
    wider ``root`` for a config that names files beside its own folder; with ``root``,
    an absolute path inside it is taken too. Paths inside the option dicts (such as a
    transcriber's ``output_dir``) are returned as stored. ``None`` is returned for any
    key that was not present.
    """
    config_path = Path(path)
    base = config_path.parent

    raw: dict[str, Any] = json.loads(config_path.read_text(encoding="utf-8-sig"))

    def _to_abs(p: str | None, what: str) -> Path | None:
        if p is None:
            return None
        return path_inside(p, base, root=root, what=what).resolve()

    def _input(p: str) -> Path:
        joined = path_inside(p, base, root=root, what="input path")
        if joined.is_dir():
            _check_input_folder(joined, root if root is not None else base)
        return joined.resolve()

    return {
        "input_paths": [_input(p) for p in raw.get("input_paths") or []],
        "sections": raw.get("sections", []),
        "report_title": raw.get("report_title", "Generated Report"),
        "report_description": raw.get("report_description"),
        "additional_instructions": raw.get("additional_instructions"),
        "report_language": raw.get("report_language"),
        "sample_report_path": _to_abs(raw.get("sample_report_path"), "sample report"),
        "output_dir": _to_abs(raw.get("output_dir"), "output folder"),
        "output_docx": raw.get("output_docx", False),
        "include_evidence_index": raw.get("include_evidence_index", True),
        "include_source_references": raw.get("include_source_references", True),
        "max_evidence_chars": raw.get("max_evidence_chars"),
        "parser_choice": raw.get("parser_choice", "auto"),
        "parser_options": raw.get("parser_options"),
        "transcriber_options": raw.get("transcriber_options"),
        "image_options": raw.get("image_options"),
        "writer_options": raw.get("writer_options"),
        "agentic": raw.get("agentic", False),
        "review_options": raw.get("review_options"),
        "polish": raw.get("polish", False),
        "strict_review": raw.get("strict_review", True),
        "curate_evidence": raw.get("curate_evidence", False),
    }


# ---------------------------------------------------------------------------
# Markdown coercion helpers
# ---------------------------------------------------------------------------


def _coerce_markdown(result: Any) -> str:
    """Best-effort extraction of markdown text from a parser result object."""
    for attr in ("clean_markdown", "parsed_markdown", "markdown", "text"):
        val = getattr(result, attr, None)
        if isinstance(val, str) and val:
            return val
    if isinstance(result, dict):
        for key in ("clean_markdown", "parsed_markdown", "markdown", "text", "text_content"):
            if isinstance(result.get(key), str):
                return result[key]
    if isinstance(result, str):
        return result
    return str(result)


def _dict_to_markdown(data: Any) -> str:
    """Serialize a VisionExtractor result dict into readable markdown evidence."""
    if isinstance(data, dict) and data:
        lines = []
        for key, value in data.items():
            label = str(key).replace("_", " ").strip().title()
            if isinstance(value, (dict, list)):
                rendered = json.dumps(value, indent=2, ensure_ascii=False)
                lines.append(f"**{label}:**\n```json\n{rendered}\n```")
            else:
                lines.append(f"**{label}:** {value}")
        return "\n\n".join(lines)
    # Fallback: fenced JSON block
    return f"```json\n{json.dumps(data, indent=2, ensure_ascii=False)}\n```"
