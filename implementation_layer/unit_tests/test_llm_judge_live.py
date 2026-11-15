"""Live test of LLMJudge.detect_hallucinations: one call over a short service log.

The extracted record has two values the log states and one name it never mentions;
the judge must flag the name and leave the other two alone. The judge takes its client
and model from ``get_llm_config("azure")``, so it calls the ``AZURE_DEPLOYMENT``
deployment; ``LLMJudge(model_provider="azure")`` alone would use its default model name.

Needs Azure OpenAI: ``AZURE_API_KEY`` and ``AZURE_ENDPOINT``, with ``AZURE_DEPLOYMENT``
naming the chat deployment. Skipped when the key or the endpoint is missing.
"""

from __future__ import annotations

import os

import pytest
from gaik.software_components.llm import get_llm_config
from gaik.software_components.validators.llm_judge import HallucinationReport, LLMJudge

_MISSING = [name for name in ("AZURE_API_KEY", "AZURE_ENDPOINT") if not os.getenv(name, "").strip()]

# Calls a real LLM: these assert on model output, so they fail when the model or
# the Azure deployment changes, not only when our code regresses. Kept out of the
# push gate (`-m "not llm"`); see .github/workflows/test.yml.
pytestmark = [
    pytest.mark.llm,
    pytest.mark.skipif(bool(_MISSING), reason=f"live Azure OpenAI test: set {', '.join(_MISSING)}"),
]

SOURCE = (
    "Service log, 3 March 2025. Technician Pekka Virtanen serviced pump P-12 "
    "and replaced its shaft seal. The pump was back in use the same afternoon."
)
EXTRACTED = {
    "technician": "Pekka Virtanen",  # stated in the log
    "pump_id": "P-12",  # stated in the log
    "supervisor": "Jari Korhonen",  # the log names no supervisor
}


def test_detect_hallucinations_flags_only_the_invented_name():
    judge = LLMJudge(config=get_llm_config("azure"))

    report = judge.detect_hallucinations(SOURCE, EXTRACTED)
    print(report.raw_judge_text)

    assert isinstance(report, HallucinationReport)
    assert report.raw_judge_text.strip()
    assert report.usage.total_tokens > 0
    flagged = {flag.field: flag for flag in report.flags}
    assert "supervisor" in flagged, report.raw_judge_text
    assert flagged["supervisor"].severity in ("wrong", "suspect")
    assert "technician" not in flagged, report.raw_judge_text
    assert "pump_id" not in flagged, report.raw_judge_text
