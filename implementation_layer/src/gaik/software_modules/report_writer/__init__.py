"""Report Writer

CURACT report writing from one report spec. SourceNormalizer converts the sources to
Markdown, KnowledgeCurator curates fact units with verbatim quotes per section and
ReportSynthesizer writes and reviews the report. Each stage saves plain files to a
workspace folder that the next stage reads, so any stage can be inspected, edited and
rerun. ``run(..., mode="single_call")`` writes the report in one call as a baseline.

Main Classes:
    - ReportWriter: run the stages of a report spec in a workspace folder
    - ReportSpec: the report spec file, with ModelSettings, RunSettings and SectionSpec
    - NormalizedSources, KnowledgeBase, Report: the saved result of each stage

Configuration:
    - get_llm_config: Get the LLM provider configuration

Example:
    >>> from gaik.software_modules.report_writer import ReportSpec, ReportWriter, get_llm_config
    >>> spec = ReportSpec.load("report_spec.json")
    >>> writer = ReportWriter(get_llm_config())
    >>> report = writer.run(spec, "workspace", progress_callback=print)
    >>> # Edit workspace/knowledge/*.json, then rewrite only the report:
    >>> report = writer.synthesize(spec, "workspace")
"""

from gaik.software_components.knowledge_curator.models import KnowledgeBase, SectionSpec
from gaik.software_components.llm import get_llm_config
from gaik.software_components.report_synthesizer.models import Report
from gaik.software_components.source_normalizer.models import NormalizedSources

from .report_writer import ReportWriter
from .spec import ModelSettings, ReportSpec, RunSettings, StepOptions

__all__ = [
    "ReportWriter",
    "ReportSpec",
    "ModelSettings",
    "RunSettings",
    "StepOptions",
    "SectionSpec",
    "NormalizedSources",
    "KnowledgeBase",
    "Report",
    "get_llm_config",
]

__version__ = "0.1.0"
