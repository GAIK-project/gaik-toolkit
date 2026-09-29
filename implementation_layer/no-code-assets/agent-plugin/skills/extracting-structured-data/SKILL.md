---
name: extracting-structured-data
description: >-
  Extracts structured data — fields, tables, line items — out of documents into
  a validated schema using the gaik toolkit, and designs schemas that stay
  inside provider limits and produce checkable evidence. Use when pulling fields
  from invoices, forms, contracts, reports, or scanned documents into JSON or a
  Pydantic model; when an extraction request fails with a 400, returns a
  truncated list, or silently drops its deepest fields; when deciding whether to
  parse a document first or feed the PDF straight to the model; when adding page
  numbers, quotes, or confidence scores as evidence; or when extraction accuracy
  needs to be measured rather than guessed. Covers schema design, property
  limits, prompt-versus-schema tuning, and citation verification.
---

# Extracting structured data with gaik

```bash
pip install "gaik[extract]"
pip install "gaik[vision-extract]"   # PDF/image extraction
# Add llm-google for shared Google/Vertex configs, or llm-litellm for LiteLLM.
```

Two entry points, and the choice is about where the document is in its lifecycle:

- **`VisionExtractor`** — PDF or image straight to structured data in one call. It renders
  the pages, so it sees layout, stamps, and handwriting.
- **`DataExtractor`** — takes document **text** you already parsed. Pair it with the
  `parsing-documents` skill.

```python
from gaik.software_components.vision_extractor import VisionExtractor
from gaik.software_components.llm import get_llm_config

config = get_llm_config("azure")   # or another supported vision/structured-output model
result = VisionExtractor(api_config=config).extract(
    file_paths=["invoice.pdf"],
    user_requirements="Supplier name, invoice number, and every line item with quantity and unit price.",
)
result.data          # dict
result.usage         # None on the shared structured-output path; do not invent token cost
```

Arguments are keyword-only. With no `extraction_model`, gaik generates the schema from the
prose (an extra LLM call); pass `schema_dir=...` and it caches the generated schema to disk
and reuses it, which makes runs both cheaper and reproducible.

For text extraction, `DataExtractor(config=get_llm_config(provider))` accepts the shared
configuration from `gaik.software_components.llm`. Choose `azure`, `openai`, `google`,
`vertex`, `anthropic`, `anthropic_foundry`, `aitta`, `openai_compatible`, or optional
`litellm`; the model must support structured output. Native Google/Vertex and Anthropic
need the `llm-google` and `llm-anthropic` extras respectively. LiteLLM requires
`gaik[llm-litellm]` and a provider-prefixed model identifier. Aitta uses
`AITTA_API_KEY` (aliases `AITTA_API_TOKEN`, `AITTA_TOKEN`) and `AITTA_MODEL`, defaulting to
`google/gemma-4-31b-it`. Other compatible servers require `OPENAI_API_KEY`, `OPENAI_BASE_URL`,
and `OPENAI_MODEL`, or equivalent explicit config overrides.

`VisionExtractor(api_config=config)` uses the same interface, renders PDF pages as PNG
images, and generates schemas with that provider. Its model must support both images and
structured output. `SchemaGenerator(config=config)` supports the shared provider path;
use a hand-built Pydantic schema and `ExtractionRequirements` when you already know the
schema. `LLMJudge(config=config)` also accepts the shared config; visual judging requires
images, while `judge_text_pair(...)` only needs a chat model. Keep credentials in runtime
configuration or environment variables, not generated source code.

## Choose providers separately for audio, vision and extraction

The modules accept stage configs so transcription can stay on a supported audio service
while text extraction uses Aitta or another chat provider:

```bash
pip install "gaik[audio-to-structured-data,documents-to-structured-data]"
```

```python
from gaik.software_modules.audio_to_structured_data import AudioToStructuredData
from gaik.software_modules.documents_to_structured_data import DocumentsToStructuredData

audio_pipeline = AudioToStructuredData(
    transcription_config=get_llm_config("azure"),
    extraction_config=get_llm_config("aitta"),
)
document_pipeline = DocumentsToStructuredData(
    parser_config=get_llm_config("openai", model="gpt-6-luna"),
    extraction_config=get_llm_config("aitta"),
)
```

Omitted stage configs use `api_config`; without a shared config, missing stages load the
legacy OpenAI/Azure default. Supplying every stage config avoids loading unrelated default
credentials. Audio transcription remains OpenAI/Azure-only: a chat provider selection,
including LiteLLM, does not make toolkit transcription support that provider.

## Fix the schema, not the prompt

This is the highest-leverage thing to know, because the instinct is the opposite.

Five deliberately different extraction prompts — stripped-down, "read the characters
first", a role frame, "walk the pages before answering" — produced **identical** F1 on
every document and every repeat. One of them had been written specifically to counter a
known corpus error and did not move a single value. The verbose variants cost about 30%
more per document for exactly the same answer.

The reason is that a well-specified schema has already pinned the task: a description on
each field, a closed object, and structured output constraining the response shape
regardless of what the prose asks for. Prompt wording only has room to matter when the
schema is vague — and then fixing the schema is still the better move.

So when extraction is wrong: add or sharpen field descriptions, tighten types, close the
object. Do not spend the afternoon rewording the instruction.

## The binding limit is property count, not schema size

Providers reject large schemas, but the thing being counted is **the number of
properties**, not characters. Measured on one provider: 200 properties passed and 250
failed; a 300,000-character schema passed while carrying 100 properties.

`$ref` reuse does not help. The natural assumption is that a definition appearing once in
`$defs` and referenced eight times counts once — it does not. Tested directly: 8 × 50
properties inline (18,263 characters) and the same thing via `$ref` (2,663 characters) were
rejected identically. The schema is expanded before counting, so the refactor that shrinks
it sevenfold on disk changes nothing.

The numbers are provider-specific and they move. The *method* is what to carry: generate
synthetic schemas at increasing property counts and bisect until one is rejected. That
takes about ten minutes and replaces a guess with a number.

## Three failures that look like degrees of one problem

They are not, and the fix for two of them does nothing for the third:

| Symptom | Cause | Fix |
|---|---|---|
| `400`, request refused outright | schema too large | split the schema |
| Output arrives but the deepest fields are missing | a nesting layer dropped | split the schema |
| `MAX_TOKENS`, truncated or no output | the *output list* ran long | window the document |

Splitting the schema **cannot** help the third: however you divide the fields, one call is
still asked to return the whole list. Staged and one-shot pipelines fail identically at a
thousand rows. That one needs the document chunked into windows and results concatenated.

## Only put fields in the schema that the document actually contains

Two traps, both of which produce numbers that look like model errors:

**A field with no ground truth does not belong in the schema.** Adding a `unit` field with
expected value `null` because the source system does not record it means a correctly
extracted `"KG"` scores as a *mistake*. Leave it out.

**A field the document does not carry measures enrichment, not extraction.** If the truth
holds an internal part number and the page shows the supplier's code, reaching one from the
other needs a lookup table. Scoring it grades the wrong system.

Both are caught the same cheap way: check every expected value against the document text
when building the evaluation set.

## Evidence that is worth something

Ask for evidence **in the same call as the value**. A separate "now justify your previous
answer" call sees its own earlier output and confirms it — that measures the model's
agreement with itself. In the same call, the quote constrains the value instead of
decorating it afterwards.

**Self-reported confidence usually ranks nothing.** In one run, 960 citations carried
**three distinct** confidence values. Raising the threshold to 0.99 dropped the accepted
set's precision *below* what accepting everything gave, while sending three quarters of the
work back to a human. Before building a threshold on a confidence score, run
`len(set(scores))`. Three means there is no ordering to threshold on — no new run required.

**A quote is valuable because it is text you can run a rule over**, not because it points
somewhere. Once you hold the quoted string, a deterministic rule can screen it with no
model, no ground truth, and no annotation — for example, flagging a number written so that
two readings differ by a factor of a thousand. The specific rule is corpus-specific; the
method is not. Look at which quotes separate the wrong values from the right ones, and
write that down as a rule.

**Unverified evidence is not evidence.** The page number and the quote are both tokens the
model generated, and either can be wrong while reading perfectly. What makes them evidence
is opening the document and checking the quoted characters are on the named page. When
checking, look at the *named* page first and on its own terms — scoring every page and
taking the best match reports correct citations as wrong whenever a common string appears
in several places.

gaik ships the wrapping form of this: `VisionExtractor(include_verification=True)` wraps
each scalar in `{value, confidence_score, confidence_reason}`, and results land in
`result.verification`. Wrapping buys paths that cannot drift onto the wrong field, because
the path is a fact about the response tree rather than a string the model wrote. It costs
roughly **four times the property count** — and property count is the limit that decides
whether the request is accepted at all. A separate citation table costs a flat +5
properties regardless of schema size. Choose against your distance from the limit.

## Parse first only when you need boxes

Feeding the model the native PDF, plain extracted text, or model-produced HTML gave the
same F1 in measured comparison, while parsing cost 22–25× the wall time. Parsing earns its
price when the deliverable is a reviewer clicking a highlighted region, because a parser
that returns bounding boxes lets a quote be matched to a box afterwards. See the
`parsing-documents` skill for the full argument.

## Measuring whether any of this worked

Comparing two configurations, or answering "did that change help", has its own set of ways
to get a confidently wrong number — including the fact that **stability can be measured
with no ground truth at all**, which unblocks measurement on the day rather than after the
labelling project. Read `references/measuring-extraction.md` before reporting any figure or
comparing two runs.

## Gotchas

- `generate_schema()` returns only the model, but `DataExtractor.extract()` also needs
  `requirements`. Use `generate_schema_with_usage()`, which returns both on
  `SchemaGenerationResult` (`.schema`, `.requirements`), plus usage when the client
  exposes it. Shared parsed-output clients may not provide token counts.
- `DataExtractor.extract(documents=...)` takes document **text**, not file paths.
  `VisionExtractor.extract(file_paths=...)` takes paths. Passing paths to `DataExtractor`
  extracts from the literal filename string and returns confident nonsense.
- Without a shared `api_config`, `VisionExtractor` and `MultimodalParser` retain legacy
  `use_azure=True` and `vertex_ai=True` defaults. Supplying a direct provider key without
  choosing the direct hosting flag produces an auth error that reads like a bad key.
  An explicit shared provider config supersedes these routing flags.
- Every layer that calls a model must classify its own errors. A rate-limit response
  arriving through a layer that does not recognise it gets re-raised as permanent, the
  runner does not retry, and the affected documents score zero — which is indistinguishable
  from model instability in the aggregate. A run whose variance is 0 but whose score is 0
  is a document that produced nothing, not an unstable model. Read the failure column
  before calling anything unstable.
- A failed document must score zero and stay in the sample. Dropping it lets a pipeline
  improve its own average by crashing on the hardest inputs.
- Stability alone rewards silence: a branch that leaves deep fields empty is perfectly
  repeatable, because empty is always the same empty. Read a stability metric next to a
  completeness metric or it will point the wrong way.
