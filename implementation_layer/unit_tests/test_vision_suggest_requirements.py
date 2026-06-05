"""Tests for VisionExtractor.suggest_requirements (suggest fields from a sample doc).

Two layers:

* Offline: the suggestion result type and module exports are importable and the
  internal meta-model has the expected single ``requirements_text`` field. These
  run anywhere — no API key needed.
* Live: a single vision pass over a synthesized one-page PDF returns a non-empty
  natural-language requirements description. Requires Azure OpenAI credentials
  (``AZURE_ENDPOINT`` + ``AZURE_API_KEY``) and PyMuPDF to render the fixture;
  skipped cleanly otherwise.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from gaik.software_components.vision_extractor import (
    RequirementsSuggestionResult,
    VisionExtractor,
)
from gaik.software_components.vision_extractor.vision_extractor import (
    _RequirementsSuggestion,
)

HAS_AZURE = bool(os.getenv("AZURE_ENDPOINT")) and bool(os.getenv("AZURE_API_KEY"))


# ---------------------------------------------------------------------------
# Offline tests (no credentials required)
# ---------------------------------------------------------------------------


def test_suggest_methods_exist():
    """Public suggestion API is present on VisionExtractor."""
    assert hasattr(VisionExtractor, "suggest_requirements")
    assert hasattr(VisionExtractor, "suggest_requirements_with_usage")


def test_requirements_suggestion_meta_model_shape():
    """The internal meta-model carries exactly one requirements_text field."""
    fields = _RequirementsSuggestion.model_fields
    assert list(fields) == ["requirements_text"]
    assert fields["requirements_text"].annotation is str
    # Validates as a normal Pydantic model.
    model = _RequirementsSuggestion(requirements_text="Top-level fields: invoice number")
    assert model.requirements_text.startswith("Top-level fields")


# ---------------------------------------------------------------------------
# Live test (requires Azure OpenAI credentials + PyMuPDF)
# ---------------------------------------------------------------------------


def _write_sample_invoice_pdf(path: Path) -> None:
    """Render a tiny one-page invoice PDF used as the sample document."""
    import fitz  # PyMuPDF

    doc = fitz.open()
    page = doc.new_page()
    text = (
        "ACME Supplies Oy\n"
        "INVOICE\n\n"
        "Invoice number: INV-2026-0042\n"
        "Invoice date: 05.06.2026\n"
        "Due date: 19.06.2026\n"
        "Bill to: Northwind Ltd, 12 Market St, 00100 Helsinki\n\n"
        "Line items:\n"
        "1  Widget A   qty 10   unit 5.00 EUR   total 50.00 EUR\n"
        "2  Widget B   qty  2   unit 12.50 EUR  total 25.00 EUR\n\n"
        "Subtotal: 75.00 EUR\n"
        "VAT 24%: 18.00 EUR\n"
        "Total: 93.00 EUR\n"
    )
    page.insert_text((72, 72), text, fontsize=11)
    doc.save(str(path))
    doc.close()


@pytest.mark.skipif(not HAS_AZURE, reason="Azure OpenAI credentials not configured")
def test_suggest_requirements_live(tmp_path: Path):
    """One vision pass over a sample invoice returns usable requirements text."""
    pytest.importorskip("fitz")

    pdf_path = tmp_path / "sample_invoice.pdf"
    _write_sample_invoice_pdf(pdf_path)

    extractor = VisionExtractor(
        model_provider="openai",
        use_azure=True,
        reasoning_effort="low",
        include_verification=False,
    )

    result = extractor.suggest_requirements_with_usage(file_paths=[pdf_path])

    assert isinstance(result, RequirementsSuggestionResult)
    assert isinstance(result.requirements_text, str)
    assert result.requirements_text.strip(), "expected a non-empty suggestion"
    assert result.documents_processed == 1
    assert result.model
    if result.usage is not None:
        assert result.usage.total_tokens > 0

    # The convenience wrapper returns just the text.
    text = extractor.suggest_requirements(
        file_paths=[pdf_path], instructions="Focus on the invoice header fields."
    )
    assert isinstance(text, str)
    assert text.strip()


if __name__ == "__main__":
    # Manual run: requires Azure credentials.
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        test_suggest_requirements_live(Path(d))
        print("live suggestion test passed")
