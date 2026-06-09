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
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

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
_XLSX_EXT = {".xlsx", ".xls"}
_AUDIO_EXT = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"}
_VIDEO_EXT = {".mp4", ".mov", ".mkv", ".avi", ".webm"}
_IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".tiff", ".tif", ".bmp", ".gif"}

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


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class ReportSectionSpec:
    """A user-defined report section."""

    title: str
    instructions: str
    required: bool = True


@dataclass
class EvidenceItem:
    """One normalized source, ready to feed the report writer."""

    source_path: str
    source_type: str
    content_markdown: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class GeneratedSection:
    title: str
    content_markdown: str
    usage: dict[str, Any] | None = None


@dataclass
class ReportGenerationResult:
    title: str
    evidence_items: list[EvidenceItem]
    sections: list[GeneratedSection]
    markdown: str
    markdown_path: Path | None
    usage: dict[str, Any]


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
- FORMAT: If a FORMAT REFERENCE is provided, it is the HIGHEST PRIORITY instruction \
and overrides everything else about format. Analyse the reference carefully and \
reproduce its formatting choices exactly: how each section is structured \
internally, whether it uses prose paragraphs, bullet lists, or numbered lists, \
the length and style of each item, any bold lead-in patterns, and the citation \
style. Achieve comprehensive coverage by writing more items at the same brevity \
the reference demonstrates, not by making individual items longer. If NO \
reference is provided, write in a clean, professional report format of your \
choice.

Content guidelines:
- Make the most of all relevant information provided in the evidence.
- Cover each section fully without omitting important details.
- Use direct language that precisely communicates facts and insights.
- Vary sentence structures naturally to maintain reader engagement.
- Use domain-specific terminology where appropriate, but prefer simpler terms \
when they communicate the same meaning.
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _slug(text: str, *, max_len: int = 40) -> str:
    keep = [c.lower() if c.isalnum() else "_" for c in text.strip()]
    s = "".join(keep)
    while "__" in s:
        s = s.replace("__", "_")
    return s.strip("_")[:max_len] or "section"


def _normalize_sections(
    sections: list[ReportSectionSpec | dict[str, Any]],
) -> list[ReportSectionSpec]:
    if not sections:
        raise ValueError("`sections` must contain at least one section.")
    out: list[ReportSectionSpec] = []
    for i, s in enumerate(sections):
        if isinstance(s, ReportSectionSpec):
            spec = s
        elif isinstance(s, dict):
            if not s.get("title"):
                raise ValueError(f"Section {i} is missing a 'title'.")
            spec = ReportSectionSpec(
                title=str(s["title"]),
                instructions=str(s.get("instructions", "")),
                required=bool(s.get("required", True)),
            )
        else:
            raise TypeError(
                f"Section {i} must be a ReportSectionSpec or dict, got {type(s).__name__}."
            )
        out.append(spec)
    return out


def _collect_input_files(input_paths: list[str | Path]) -> list[Path]:
    """Expand files/folders into a flat list of supported source files."""
    if not input_paths:
        raise ValueError("`input_paths` must contain at least one file or folder.")
    collected: list[Path] = []
    seen: set[Path] = set()
    for raw in input_paths:
        p = Path(raw)
        if not p.exists():
            raise FileNotFoundError(f"Input path does not exist: {p}")
        candidates = sorted(p.rglob("*")) if p.is_dir() else [p]
        for c in candidates:
            if not c.is_file():
                continue
            if c.suffix.lower() not in SUPPORTED_EXTENSIONS:
                continue
            rp = c.resolve()
            if rp in seen:
                continue
            seen.add(rp)
            collected.append(c)
    return collected


def _csv_to_markdown(path: Path) -> str:
    with open(path, encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.reader(fh))
    if not rows:
        return "_(empty CSV)_"
    return _rows_to_markdown_table(rows)


def _rows_to_markdown_table(rows: list[list[Any]]) -> str:
    width = max(len(r) for r in rows)
    norm = [[str(c) if c is not None else "" for c in r] + [""] * (width - len(r)) for r in rows]
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
            path.name,
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

    def __init__(self, *, api_config: dict | None = None, use_azure: bool = True) -> None:
        if api_config is None:
            from gaik.software_components.config import get_openai_config

            api_config = get_openai_config(use_azure=use_azure)
        self.api_config = api_config

    # -- public API -------------------------------------------------------

    def run(
        self,
        *,
        input_paths: list[str | Path],
        sections: list[ReportSectionSpec | dict[str, Any]],
        report_title: str = "Generated Report",
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
    ) -> ReportGenerationResult:
        """Build evidence from ``input_paths`` and write each requested section."""
        specs = _normalize_sections(sections)
        files = _collect_input_files(input_paths)
        if not files:
            raise ValueError(
                "No supported source files found in `input_paths`. "
                f"Supported extensions: {sorted(SUPPORTED_EXTENSIONS)}"
            )

        parser_options = parser_options or {}
        transcriber_options = transcriber_options or {}
        image_options = image_options or {}
        writer_options = writer_options or {}

        # 1. Build evidence
        evidence_items: list[EvidenceItem] = []
        for index, path in enumerate(files, start=1):
            item = self._build_evidence_item(
                path,
                index=index,
                parser_choice=parser_choice,
                parser_options=parser_options,
                transcriber_options=transcriber_options,
                image_options=image_options,
            )
            evidence_items.append(item)

        evidence_pack = self._assemble_evidence_pack(
            evidence_items, max_evidence_chars=max_evidence_chars
        )

        # Optional format template the writer must strictly follow.
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

        # 2. Write the whole report in a single LLM call (so a sample report's
        #    format applies to the report as a whole, not per section).
        client = self._build_llm_client(writer_options)
        chat_kwargs = {
            k: v
            for k, v in writer_options.items()
            if k not in ("model", "provider") and v is not None
        }

        response = self._write_report(
            client,
            specs=specs,
            evidence_pack=evidence_pack,
            report_title=report_title,
            report_language=report_language,
            include_source_references=include_source_references,
            sample_markdown=sample_markdown,
            chat_kwargs=chat_kwargs,
        )

        # 3. Normalize the report markdown and derive per-section breakdown.
        markdown = _normalize_report_markdown(response.text, report_title)
        usage_total: dict[str, int] = (
            {k: v for k, v in response.usage.items() if isinstance(v, int)}
            if getattr(response, "usage", None)
            else {}
        )
        generated = _split_into_sections(markdown, specs)

        # 4. Write outputs
        markdown_path: Path | None = None
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
            )

        return ReportGenerationResult(
            title=report_title,
            evidence_items=evidence_items,
            sections=generated,
            markdown=markdown,
            markdown_path=markdown_path,
            usage=usage_total,
        )

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
            return path.read_text(encoding="utf-8", errors="replace")
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
        return self._extract_content(
            path,
            source_type=source_type,
            parser_choice=parser_choice,
            parser_options=parser_options,
            transcriber_options={},
            image_options={},
        )

    def _parse_pdf(self, path: Path, *, parser_choice: str, parser_options: dict) -> str:
        choice = (parser_choice or "auto").lower()
        if choice == "auto":
            choice = "pymupdf"  # local, no API cost; deterministic default for V1

        if choice == "pymupdf":
            from gaik.software_components.parsers import PyMuPDFParser

            return PyMuPDFParser().parse_pdf(str(path), use_markdown=True)
        if choice in ("vision", "vision_parser"):
            from gaik.software_components.parsers import VisionParser, get_openai_config

            cfg = parser_options.get("openai_config") or get_openai_config(
                use_azure=self.api_config.get("use_azure", True)
            )
            pages = VisionParser(cfg, **parser_options.get("ctor", {})).convert_pdf(str(path))
            return "\n\n".join(pages)
        if choice == "multimodal":
            from gaik.software_components.parsers import MultimodalParser

            result = MultimodalParser(**parser_options.get("ctor", {})).parse(str(path))
            return result.clean_markdown or result.raw_markdown
        if choice == "docling":
            from gaik.software_components.parsers import DoclingParser

            result = DoclingParser(**parser_options.get("ctor", {})).parse_document(str(path))
            return _coerce_markdown(result)
        raise ValueError(
            f"Unknown parser_choice '{parser_choice}'. "
            "Use one of: auto, pymupdf, vision, multimodal, docling."
        )

    def _parse_docx(self, path: Path) -> str:
        from gaik.software_components.parsers import DocxParser

        return DocxParser().parse_docx(str(path), use_markdown=True)

    def _transcribe(self, path: Path, *, transcriber_options: dict) -> str:
        from gaik.software_components.transcriber import Transcriber

        ctor = dict(transcriber_options.get("ctor", {}))
        transcriber = Transcriber(api_config=self.api_config, **ctor)
        result = transcriber.transcribe(str(path), **transcriber_options.get("call", {}))
        return result.enhanced_transcript or result.raw_transcript

    def _parse_image(self, path: Path, *, image_options: dict) -> str:
        mode = image_options.get("mode", "parse")  # "parse" | "structured"
        if mode == "structured":
            from gaik.software_components.vision_extractor import VisionExtractor

            ctor = dict(image_options.get("ctor", {}))
            ctor.setdefault("api_config", self.api_config)
            extractor = VisionExtractor(**ctor)
            user_requirements = image_options.get(
                "user_requirements",
                "Extract all visible text, tables, figures, and structured content from the image.",
            )
            result = extractor.extract(file_paths=[str(path)], user_requirements=user_requirements)
            return _dict_to_markdown(result.data)

        # default: general parsing to markdown via VisionParser.convert_image()
        from gaik.software_components.parsers import VisionParser, get_openai_config

        cfg = image_options.get("openai_config") or get_openai_config(
            use_azure=self.api_config.get("use_azure", True)
        )
        return VisionParser(cfg, **image_options.get("ctor", {})).convert_image(str(path))

    def _assemble_evidence_pack(
        self, evidence_items: list[EvidenceItem], *, max_evidence_chars: int | None
    ) -> str:
        blocks: list[str] = []
        for item in evidence_items:
            meta = item.metadata
            header = (
                f"## Source {meta.get('index')}: {meta.get('filename')}\n"
                f"Type: {item.source_type}\n"
                f"Path: {item.source_path}\n"
            )
            blocks.append(f"{header}\n{item.content_markdown}")
        pack = "\n\n---\n\n".join(blocks)
        if max_evidence_chars is not None and len(pack) > max_evidence_chars:
            logger.warning(
                "Evidence pack (%d chars) exceeds max_evidence_chars (%d); truncating.",
                len(pack),
                max_evidence_chars,
            )
            pack = pack[:max_evidence_chars] + "\n\n[... evidence truncated ...]"
        return pack

    # -- writing ----------------------------------------------------------

    def _build_llm_client(self, writer_options: dict):
        if create_llm_client is None:
            raise ImportError(
                "The LLM client could not be imported. Install the base GAIK "
                "dependencies (openai) to run the report writer."
            )
        cfg = dict(self.api_config)
        if writer_options.get("model"):
            cfg["model"] = writer_options["model"]
        if writer_options.get("provider"):
            cfg["provider"] = writer_options["provider"]
        return create_llm_client(cfg)

    def _write_report(
        self,
        client,
        *,
        specs: list[ReportSectionSpec],
        evidence_pack: str,
        report_title: str,
        report_language: str | None,
        include_source_references: bool,
        sample_markdown: str | None,
        chat_kwargs: dict,
    ):
        """Write the entire report in one LLM call and return the raw response."""
        parts = [f"Report title: {report_title}"]
        if report_language:
            parts.append(f"Write the report in: {report_language}")
        if include_source_references:
            parts.append(
                "Where useful, reference the source (e.g. by filename) that supports a claim."
            )

        # Present the sample BEFORE the section instructions so the model internalises
        # the expected tone/structure/format (layout, list style, brevity) before
        # reading what content to put in each section.
        if sample_markdown:
            parts.append(
                "FORMAT REFERENCE — HIGHEST PRIORITY. Analyse this example and reproduce "
                "its formatting exactly across the whole report:\n"
                "  • Identify how each section is structured internally and replicate it.\n"
                "  • Match the list type (prose, bullets, numbered) and item length used "
                "in the example. If items are short, keep yours short; if they are longer "
                "prose, match that length.\n"
                "  • Replicate any bold lead-in patterns, indentation, or citation style.\n"
                "  • When content instructions ask for comprehensive coverage, achieve "
                "completeness by writing more items at the same brevity the reference "
                "shows, not by making individual items longer.\n"
                "  • Section titles come from the required list below. Facts and wording "
                "come from the evidence. Only the FORMAT comes from this reference.\n\n"
                f"{sample_markdown}"
            )

        # Section definitions: use a numbered, titled format so the model never
        # echoes a "SECTION:" prefix into the output headings.
        section_lines = ["Required sections (write each as `## <title>` in this exact order):"]
        for i, spec in enumerate(specs, start=1):
            section_lines.append(f"\n{i}. Heading: {spec.title}")
            section_lines.append(f"   Content to cover: {spec.instructions}")
        parts.append("\n".join(section_lines))

        parts.append(f"Evidence (all available source material):\n{evidence_pack}")

        closing = [
            f"Now write the complete report. Start with `# {report_title}`, then write "
            "every required section in order using `## <exact heading title>`."
        ]
        if sample_markdown:
            closing.append("Strictly adhere to the FORMAT REFERENCE's tone, style, and structure.")
        else:
            closing.append("Write in a clean, professional report format.")
        closing.append("Use only the evidence.")
        parts.append(" ".join(closing))
        user_prompt = "\n\n".join(parts)

        return client.chat(
            [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            **chat_kwargs,
        )

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
    ) -> Path:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        (out / "sections").mkdir(exist_ok=True)
        (out / "evidence").mkdir(exist_ok=True)

        report_path = out / "report.md"
        report_path.write_text(markdown, encoding="utf-8")

        for i, s in enumerate(sections, start=1):
            name = f"{i:02d}_{_slug(s.title)}.md"
            (out / "sections" / name).write_text(
                f"## {s.title}\n\n{s.content_markdown.strip()}\n", encoding="utf-8"
            )

        (out / "evidence" / "normalized_sources.md").write_text(evidence_pack, encoding="utf-8")

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

        if usage:
            (out / "usage.json").write_text(
                json.dumps(usage, indent=2, ensure_ascii=False), encoding="utf-8"
            )

        return report_path


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
        for key in ("clean_markdown", "parsed_markdown", "markdown", "text"):
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
