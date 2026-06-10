"""Opt-in agentic report workflow (V2).

Independent per-section drafting in parallel, mandatory diff-editor review with
retry, optional knowledge curation and style polish. Requires ``langgraph``
(the ``multi-source-report-generator-agentic`` extra).
"""

from .orchestrator import run_agentic_report
from .reviewer import Correction, CorrectionList

__all__ = ["run_agentic_report", "Correction", "CorrectionList"]
