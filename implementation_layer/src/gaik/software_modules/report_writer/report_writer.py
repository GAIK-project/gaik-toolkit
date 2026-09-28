"""Write a report from a report spec in three inspectable stages, or in one call.

This module implements ReportWriter: SourceNormalizer, KnowledgeCurator and
ReportSynthesizer run in turn, and each stage saves its result as plain files in a
workspace folder that the next stage reads. A person can edit those files and rerun
only the later stages.
"""

from __future__ import annotations

import re
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Literal

from gaik.software_components.knowledge_curator import KnowledgeCurator
from gaik.software_components.knowledge_curator.models import KnowledgeBase
from gaik.software_components.llm import create_llm_client
from gaik.software_components.report_synthesizer import (
    Report,
    ReportSection,
    ReportSynthesizer,
)
from gaik.software_components.source_normalizer import NormalizedSources, SourceNormalizer

from .prompts import SINGLE_CALL_SYSTEM_PROMPT, build_single_call_prompt
from .spec import ReportSpec

Progress = Callable[[str], None] | None


def _workspace(workspace: str | Path) -> Path:
    path = Path(workspace)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _clear(folder: Path) -> None:
    """Delete a stage folder, so no file of an earlier run survives the new result."""
    if folder.exists():
        shutil.rmtree(folder)


def _sample_text(spec: ReportSpec, workspace: Path) -> str | None:
    """The sample report that ``normalize`` wrote, or None if the spec has none."""
    if spec.sample_report is None:
        return None
    return (workspace / "sample_report.md").read_text(encoding="utf-8")


def _split_sections(answer: str, spec: ReportSpec) -> list[ReportSection]:
    """Split a single-call answer into one section per spec section, in spec order."""
    head, *blocks = re.split(r"^## ", answer.strip(), flags=re.MULTILINE)
    expected = [s.title for s in spec.sections]
    found = [block.partition("\n")[0].strip() for block in blocks]
    if found != expected:
        raise ValueError(
            "The single-call answer must have one '## <title>' heading per section, in "
            f"spec order. Expected {expected}, found {found}"
        )
    if head.strip() != f"# {spec.title}":
        raise ValueError(
            f"The single-call answer must start with '# {spec.title}' and have nothing "
            f"else before the first section, found {head.strip()!r}"
        )
    sections = []
    for section, block in zip(spec.sections, blocks, strict=True):
        text = block.partition("\n")[2].strip()
        if not text:
            raise ValueError(f"The single-call answer has an empty section {section.title!r}")
        sections.append(ReportSection(id=section.id, title=section.title, text=text))
    return sections


class ReportWriter:
    """Run the CURACT stages of a report spec in a workspace folder.

    ``normalize`` writes ``normalized/`` (and ``sample_report.md``), ``curate`` reads it
    and writes ``knowledge/``, ``synthesize`` reads that and writes ``report/``. Each
    stage replaces its own folder and reads only files, so a stage can be rerun after
    its input files were edited by hand.
    """

    def __init__(self, config: dict):
        """
        Args:
            config: LLM config from `get_llm_config()`. The spec's `models` override its
                model per step, and its `settings` set how each stage runs.
        """
        self.config = config

    def normalize(
        self, spec: ReportSpec, workspace: str | Path, *, progress_callback: Progress = None
    ) -> NormalizedSources:
        """Stage 1: convert the sources to ``normalized/`` and the sample report to
        ``sample_report.md``; without a sample report, a stale ``sample_report.md`` is removed.

        The returned sources carry the usage of the sources and the sample report.
        """
        workspace = _workspace(workspace)
        normalizer = SourceNormalizer(
            self.config,
            vision_model=spec.models.vision,
            transcription_model=spec.models.transcription,
            language=spec.settings.transcription_language,
        )
        sources = normalizer.normalize(spec.sources, progress_callback=progress_callback)
        sample = workspace / "sample_report.md"
        if spec.sample_report is None:
            sample.unlink(missing_ok=True)
        else:
            sample.write_text(normalizer.to_markdown(spec.sample_report), encoding="utf-8")
        _clear(workspace / "normalized")
        sources.save(workspace / "normalized")
        sources.usage = normalizer.usage.snapshot()
        return sources

    def curate(
        self, spec: ReportSpec, workspace: str | Path, *, progress_callback: Progress = None
    ) -> KnowledgeBase:
        """Stage 2: curate ``normalized/`` into one ``knowledge/<section_id>.json`` per section."""
        workspace = _workspace(workspace)
        sources = NormalizedSources.load(workspace / "normalized")
        knowledge = KnowledgeCurator(
            self.config,
            spec.models.curator,
            max_workers=spec.settings.curator_workers,
            chat_options=spec.settings.curator.chat_kwargs(),
        ).curate(
            sources,
            spec.sections,
            instructions=spec.instructions,
            progress_callback=progress_callback,
        )
        _clear(workspace / "knowledge")
        knowledge.save(workspace / "knowledge")
        return knowledge

    def synthesize(
        self, spec: ReportSpec, workspace: str | Path, *, progress_callback: Progress = None
    ) -> Report:
        """Stage 3: write and review the report from ``knowledge/`` into ``report/``.

        The returned report carries the token usage of the writer and reviewer calls.
        """
        workspace = _workspace(workspace)
        knowledge = KnowledgeBase.load(workspace / "knowledge")
        settings = spec.settings
        synthesizer = ReportSynthesizer(
            self.config,
            spec.models.writer,
            reviewer_model=spec.models.reviewer,
            strict_review=settings.strict_review,
            review_attempts=settings.review_attempts,
            writer_options=settings.writer.chat_kwargs(),
            reviewer_options=settings.reviewer.chat_kwargs(),
        )
        report = synthesizer.synthesize(
            knowledge,
            spec.sections,
            title=spec.title,
            language=spec.language,
            instructions=spec.instructions,
            sample_report=_sample_text(spec, workspace),
            progress_callback=progress_callback,
        )
        report.save(workspace / "report", docx=settings.docx)
        return report

    def rebuild(self, spec: ReportSpec, workspace: str | Path) -> Report:
        """Rebuild ``report/report.md`` and, if the spec asks for it, ``report/report.docx``
        from the section files.

        No LLM call: this is how hand edits of ``report/sections/*.md`` reach the report.
        """
        folder = _workspace(workspace) / "report"
        report = Report.load(folder)
        report.save(folder, docx=spec.settings.docx)
        return report

    def run(
        self,
        spec: ReportSpec,
        workspace: str | Path,
        *,
        mode: Literal["curact", "single_call"] = "curact",
        progress_callback: Progress = None,
    ) -> Report:
        """Run every stage: ``normalize``, ``curate`` and ``synthesize``.

        ``mode="single_call"`` runs ``normalize`` and then writes the whole report in one
        writer call from every normalized source, into ``single_call/``. It is the
        curation-free baseline to compare the CURACT report against.
        """
        if mode not in ("curact", "single_call"):
            raise ValueError(f"Unknown mode {mode!r}; use 'curact' or 'single_call'")
        sources = self.normalize(spec, workspace, progress_callback=progress_callback)
        if mode == "curact":
            self.curate(spec, workspace, progress_callback=progress_callback)
            return self.synthesize(spec, workspace, progress_callback=progress_callback)

        workspace = Path(workspace)
        if progress_callback:
            progress_callback("Writing the whole report in one call")
        config = {**self.config, "model": spec.models.writer} if spec.models.writer else self.config
        prompt = build_single_call_prompt(spec, sources, _sample_text(spec, workspace))
        response = create_llm_client(config).chat(
            [
                {"role": "system", "content": SINGLE_CALL_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            **spec.settings.writer.chat_kwargs(),
        )
        report = Report(
            title=spec.title,
            sections=_split_sections(response.text, spec),
            review_log=[],
            usage=response.usage,
        )
        report.save(workspace / "single_call", docx=spec.settings.docx)
        return report
