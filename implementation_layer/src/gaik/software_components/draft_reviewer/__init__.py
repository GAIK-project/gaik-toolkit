"""Draft Reviewer

Fact-check generated text (summaries, report sections, incident reports, meeting minutes)
against reference material. An LLM proposes search-and-replace edits; each is applied only
where its search text occurs exactly once, failed edits are retried, and the result keeps
an edit log.

Main Classes:
    - DraftReviewer: Review a text against reference material
    - Edit: One search-and-replace correction and its reason
    - ReviewResult: The reviewed text, the applied edits and the unresolved edits

Configuration:
    - get_llm_config: Build a provider config (Azure, OpenAI, Anthropic, Google, ...)

Example:
    >>> from gaik.software_components.draft_reviewer import DraftReviewer, get_llm_config
    >>> reviewer = DraftReviewer(get_llm_config())
    >>> result = reviewer.review(draft, reference=source_text)
    >>> print(result.text, result.applied, result.unresolved)
"""

from gaik.software_components.llm import get_llm_config

from .draft_reviewer import DraftReviewer
from .models import Edit, ReviewResult

__all__ = [
    "DraftReviewer",
    "Edit",
    "ReviewResult",
    "get_llm_config",
]

__version__ = "0.1.0"
