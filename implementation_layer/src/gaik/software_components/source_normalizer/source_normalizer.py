"""Convert mixed source files to Markdown texts with their provenance.

This module implements SourceNormalizer, the ingestion stage of the report writer.
Parsers, the transcriber and the vision parser are imported only when a file needs them.
"""

from __future__ import annotations

import re
import tempfile
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

from gaik.software_components.llm.base import UsageCounter, usage_since

from .models import NormalizedSource, NormalizedSources, source_id

_AUDIO = (".mp3", ".wav", ".m4a", ".ogg", ".flac", ".webm", ".mp4", ".mpeg", ".mpga")
_TYPES = {
    ".pdf": "pdf",
    ".docx": "docx",
    ".xlsx": "spreadsheet",
    ".csv": "spreadsheet",
    ".txt": "text",
    ".md": "text",
    **dict.fromkeys(_AUDIO, "audio"),
    **dict.fromkeys((".png", ".jpg", ".jpeg", ".webp"), "image"),
}
_TOOLS = {
    "pdf": "PyMuPDFParser",
    "docx": "DocxParser",
    "spreadsheet": "SpreadsheetParser",
    "text": "text",
    "audio": "Transcriber",
    "image": "VisionParser",
}
_PAGE_MARKER = re.compile(r"^\[Page \d+\]$", re.MULTILINE)


class SourceNormalizer:
    """Convert PDFs, Word files, spreadsheets, text, recordings and images to Markdown.

    Documents are parsed locally. Recordings go to the Transcriber and images to the
    VisionParser, so they need an LLM config.
    """

    def __init__(
        self,
        config: dict | None = None,
        *,
        vision_model: str | None = None,
        transcription_model: str | None = None,
        language: str = "auto",
    ):
        """
        Initialize SourceNormalizer.

        Args:
            config: LLM config from `get_llm_config()` or `get_openai_config()`. Needed only
                for recordings and images.
            vision_model: Optional model override for images. Defaults to `config["model"]`.
            transcription_model: Optional Transcriber model, e.g. `gpt-4o-transcribe`.
            language: Transcription language, or `auto`.
        """
        self.config = config
        self.vision_model = vision_model
        self.transcription_model = transcription_model
        self.language = language
        self.usage = UsageCounter()
        """Usage totals of every transcription and vision call this normalizer made."""

    def normalize(
        self,
        sources: Mapping[str, Sequence[str | Path]] | Sequence[str | Path],
        *,
        progress_callback: Callable[[str], None] | None = None,
    ) -> NormalizedSources:
        """Convert files given as `{source_class: [paths]}` or a plain list, in input order."""
        groups = sources.items() if isinstance(sources, Mapping) else [(None, sources)]
        items: list[tuple[str | None, Path]] = []
        for source_class, paths in groups:
            if isinstance(paths, (str, Path)):
                raise TypeError(f"Expected a list of paths, got {paths!r}")
            items += [(source_class, Path(p)) for p in paths]
        if not items:
            raise ValueError("No source files given")
        # A fact cites its source by file name, so the names must be unique.
        names = [path.name for _, path in items]
        duplicates = sorted({n for n in names if names.count(n) > 1})
        if duplicates:
            raise ValueError(f"Duplicate source file names: {duplicates}")
        # Check every file before the slow conversions start.
        for _, path in items:
            self._source_type(path)

        before = self.usage.snapshot()
        normalized = []
        for i, (source_class, path) in enumerate(items, start=1):
            if progress_callback:
                progress_callback(f"Normalizing {path.name} ({i}/{len(items)})")
            source_type, tool, text = self._convert(path)
            normalized.append(
                NormalizedSource(
                    id=source_id(i, path.name),
                    file=path.name,
                    source_class=source_class,
                    source_type=source_type,
                    tool=tool,
                    text=text,
                )
            )
        return NormalizedSources(
            sources=normalized, usage=usage_since(before, self.usage.snapshot())
        )

    def to_markdown(self, path: str | Path) -> str:
        """Convert one file with the same dispatch as `normalize` and return its text."""
        return self._convert(Path(path))[2]

    def _source_type(self, path: Path) -> str:
        if not path.is_file():
            raise FileNotFoundError(f"{path}: not an existing file")
        suffix = path.suffix.lower()
        if suffix not in _TYPES:
            raise ValueError(f"{path.name}: unsupported file type {suffix}")
        source_type = _TYPES[suffix]
        if source_type in ("audio", "image") and self.config is None:
            raise ValueError(f"{path.name}: {source_type} files need an LLM config")
        return source_type

    def _convert(self, path: Path) -> tuple[str, str, str]:
        """Return `(source_type, tool, text)` for one file."""
        source_type = self._source_type(path)
        try:
            if source_type == "pdf":
                from gaik.software_components.parsers.pymypdf import PyMuPDFParser

                text = PyMuPDFParser().parse_pdf(str(path), page_markers=True)
                if not _PAGE_MARKER.sub("", text).strip():
                    raise ValueError(f"{path.name}: PDF has no text layer")
            elif source_type == "docx":
                from gaik.software_components.parsers.docx_parser import DocxParser

                text = DocxParser().parse_docx(str(path), keep_structure=True)
            elif source_type == "spreadsheet":
                from gaik.software_components.parsers.spreadsheet_parser import SpreadsheetParser

                text = SpreadsheetParser().parse_spreadsheet(path)
            elif source_type == "text":
                text = path.read_text(encoding="utf-8-sig")
            elif source_type == "audio":
                from gaik.software_components.transcriber.transcriber import Transcriber

                with tempfile.TemporaryDirectory() as workspace:
                    transcriber = Transcriber(
                        self.config,
                        output_dir=workspace,
                        transcription_model=self.transcription_model,
                        language=self.language,
                    )
                    result = transcriber.transcribe(path)
                text = result.raw_transcript
                self.usage.add(result.usage)
                if "[Transcription failed" in text:
                    raise RuntimeError(f"{path.name}: transcription failed for a segment")
            else:
                from gaik.software_components.parsers.vision import VisionParser

                config = self.config
                if self.vision_model:
                    config = {**config, "model": self.vision_model}
                parser = VisionParser(config)
                text = parser.convert_image(path)
                self.usage.add(parser.usage.snapshot())
        except Exception as exc:
            exc.add_note(f"While normalizing {path}")
            raise
        if not text.strip():
            raise ValueError(f"{path.name}: no text extracted")
        return source_type, _TOOLS[source_type], text
