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
- Each failed edit gets an id (`F1`, `F2`, ...) that the retry request shows, and each
  retry edit names the ids of the failed edits it makes in `answers`, such as `["F1"]`,
  or `["F1", "F2"]` when one edit makes two of them, so a retry may word its edit and its
  reason differently. A failed edit that no retry edit names is asked for again in the
  next request under the same id, and is returned in `unresolved` if it is still missing
  when the review ends; one whose retry edit fails too is carried once, as that retry
  edit. A retry edit that carries `answers` makes exactly the ids it names: an empty list,
  or an id that does not exist, makes none of them. Only a retry edit without the field
  (a model or client that leaves it out) is paired with at most one remaining failed edit
  by its text: the same correction (one replacement containing the other) or, for a
  deletion, a deletion of nearly the same text with the same numbers. A shared reason
  alone, such as "Not in the reference.", never pairs two edits.
- This repeats until nothing fails or `max_attempts` requests (the first one included)
  have been made. Edits that still fail are returned in `unresolved`, not raised: the
  caller decides whether they are fatal.

## Source material as data

The reference and the text under review reach the model as material, apart from the
checks: the system message holds the reviewer's rules and the sentence in
`SOURCE_MATERIAL_INSTRUCTION`, and each piece sits in its own `<source_material>` block
with a random id ([`gaik.software_components.source_material`](../source_material.py)).
Each `review()` call draws a new id and keeps it for all of its requests, so the
instruction stays the same across retries; it draws another only when an edit has
written the current id into the text that is sent. Your
`instructions` stay outside the blocks. `reference` may also be a mapping of names to
texts (one entry per source or per earlier section); each entry gets its own block,
labelled with its name. A sentence in the draft or the reference cannot close its block
or change the checks. The edits are still applied without a person's approval; check the
`applied` list where that matters.

## Use in ReportSynthesizer

`ReportSynthesizer` reviews each drafted section with a `DraftReviewer`, passing the
section's curated knowledge as `reference` (for a derived section, a mapping of its
prerequisite sections) and its own section checks as `instructions`.
Each section's `applied` and `unresolved` edits go into the report's `review_log`, and
its `strict_review` flag decides whether an unresolved edit stops the run.

The token usage of every review so far is on `reviewer.client.usage.snapshot()`.

See the [example](../../../../examples/software_components/draft_reviewer/draft_reviewer_example.py)
for a complete script.

## License

MIT - see [LICENSE](../../../../../LICENSE)
