# Draft Reviewer

Fact-check generated text against reference material. Works on any text: summaries,
report sections, incident reports, meeting minutes. An LLM proposes exact
search-and-replace edits with a reason for each; the reviewer applies them and returns the
corrected text with an edit log.

## Installation

```bash
pip install "gaik[draft-reviewer]"
```

Core dependencies only. Works with any provider supported by `get_llm_config`
(Azure, OpenAI, Anthropic, Google and others).

---

## Quick Start

```python
from gaik.software_components.draft_reviewer import DraftReviewer, get_llm_config

reviewer = DraftReviewer(get_llm_config())
# optional: model="...", max_attempts=5, chat_options={"reasoning_effort": "low"}
result = reviewer.review(
    "The building was completed in 1999.",
    reference="Inspection notes: the building was completed in 1998.",
)
print(result.text)  # The building was completed in 1998.
for edit in result.applied:
    print(edit.search, "->", edit.replace, ":", edit.reason)
print(result.unresolved)  # edits that could not be applied
```

`instructions` replaces the default checks, for example
`instructions="Check only numbers and dates. Do not delete sentences."`. The default
checks are: every factual claim must be supported by the reference; numbers, years,
dates, names and attributions that contradict it are corrected; unsupported claims are
removed; style and order are left alone.

`review()` returns a `ReviewResult` with `text`, `applied` and `unresolved`, each edit an
`Edit(search, replace, reason)`. An empty `draft` or `reference` raises `ValueError`.

---

## Exact matching and retries

- Edits are applied in order, each to the text left by the edits before it.
- An edit applies only if its `search` text occurs **exactly once** in the current text.
  There is no fuzzy or case-insensitive matching. An empty `replace` deletes the passage.
- An edit whose search text is not found, or is found more than once, fails. The failed
  edits, their errors and the current text go back to the LLM for new edits, which are
  applied the same way. A retry answer with no edits ends the review and leaves the
  failed edits unresolved.
- This repeats until nothing fails or `max_attempts` requests (the first one included)
  have been made. Edits that still fail are returned in `unresolved`, not raised: the
  caller decides whether they are fatal.

## Use in ReportSynthesizer

`ReportSynthesizer` reviews each drafted section with a `DraftReviewer`, passing the
section's curated knowledge as `reference` and its own section checks as `instructions`.
Each section's `applied` and `unresolved` edits go into the report's `review_log`, and
its `strict_review` flag decides whether an unresolved edit stops the run.

The token usage of every review so far is on `reviewer.client.usage.snapshot()`.

See the [example](../../../../examples/software_components/draft_reviewer/draft_reviewer_example.py)
for a complete script.

## License

MIT - see [LICENSE](../../../../../LICENSE)
