"""Draft Reviewer Example

Fact-checks a short draft with a planted wrong year against a reference text.
"""

import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / ".env")

# Allow running without `pip install -e .`
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from gaik.software_components.draft_reviewer import DraftReviewer, get_llm_config  # noqa: E402

REFERENCE = """\
Inspection notes, 12 March 2024. The office building at Tammikatu 4 was completed in 1998.
The roof membrane was replaced in 2015. Moisture readings in the basement walls were normal.
The ventilation units date from the original construction."""

DRAFT = """\
The office building at Tammikatu 4 was completed in 1999. Its roof membrane was replaced \
in 2015, and moisture readings in the basement walls were normal. The ventilation units \
were renewed in 2020."""


def review_example():
    """Review the draft and print the edit log."""
    reviewer = DraftReviewer(get_llm_config())
    result = reviewer.review(DRAFT, reference=REFERENCE)

    print(f"Reviewed text:\n{result.text}\n")
    print(f"Applied edits ({len(result.applied)}):")
    for edit in result.applied:
        print(f"  {edit.search!r} -> {edit.replace!r}: {edit.reason}")
    print(f"Unresolved edits ({len(result.unresolved)}):")
    for edit in result.unresolved:
        print(f"  {edit.search!r} -> {edit.replace!r}: {edit.reason}")


if __name__ == "__main__":
    review_example()
