# Enhance Transcript

Enhance Finnish transcript text using a two-pass LLM workflow.

This software component is currently designed for Finnish transcripts. The prompts, correction policy, and error-repair logic are tuned for Finnish spelling, compounds, colloquial speech, and common ASR failure modes in Finnish. The same structure can be adapted for other languages, but that requires changing the prompts and validation rules for the target language instead of assuming the Finnish behavior transfers directly.

The enhancement runs in two passes:

1. Pass 1 focuses on targeted spelling cleanup and consistency.
   - It corrects obvious spelling mistakes.
   - It normalizes repeated terms to one consistent form across the transcript.
   - It fixes casing and small near-miss errors while preserving the original wording, order, and meaning.

2. Pass 2 focuses on context-based repair.
   - It fixes remaining ASR issues that need more sentence-level context.
   - It repairs split or merged compounds and limited grammar problems when the correction is clear.
   - It preserves spoken Finnish and avoids rewriting the transcript into formal written language.

The goal is not to rewrite the transcript into polished prose. The goal is to keep the transcript faithful to the spoken content while reducing transcription mistakes in a controlled way.

## Installation

```bash
pip install "gaik[enhance-transcript]"
```

`enhance-transcript` does not add extra third-party dependencies beyond the core `gaik` install. The extra exists for consistency with the other software components.

## Quick Start

```python
from gaik.software_components.enhance_transcript import (
    TranscriptEnhancer,
    get_openai_config,
)

config = get_openai_config(use_azure=True)
enhancer = TranscriptEnhancer(api_config=config)

result = enhancer.enhance_text(
    "tama on suomenkielinen litterointi jossa on virheita",
    generate_summary=True,
    diff_chunks=True,
)

print(result.enhanced_text)
print(result.model_dump())
```

## Supported Inputs

- raw transcript as `str`
- transcript file as `.txt`

## API

```python
from gaik.software_components.enhance_transcript import TranscriptEnhancer

enhancer = TranscriptEnhancer(
    api_config=config,         # Optional; uses get_openai_config() if omitted
    use_azure=True,           # Used only when api_config is omitted
    model=None,               # Optional model override
)

result = enhancer.enhance_text(
    transcript_text="...",
    generate_summary=False,
    diff_chunks=False,
    additional_instructions=None,
)

result = enhancer.enhance_file(
    file_path="transcript.txt",
    generate_summary=True,
    diff_chunks=True,
    additional_instructions="Keep company names exactly as they appear.",
)
```

## Optional Parameters

Both `enhance_text(...)` and `enhance_file(...)` support these optional parameters:

### `generate_summary`

When `generate_summary=True`, the result includes a compact correction summary:
- `total_changes`
- `insertions`
- `deletions`
- `substitutions`

Example:

```python
result = enhancer.enhance_text(
    transcript_text="tama on hammas laakari",
    generate_summary=True,
)

print(result.correction_summary)
# CorrectionSummary(total_changes=2, insertions=0, deletions=0, substitutions=2)
```

Use this when you want a quick numeric overview of how much the transcript changed.

### `diff_chunks`

When `diff_chunks=True`, the result includes a list of changed spans between the original and corrected transcript.

The component returns only changed chunks, not unchanged text. The `kind` value can be:
- `substitute`
- `insert`
- `delete`

Example:

```python
result = enhancer.enhance_text(
    transcript_text="tama on hammas laakari",
    diff_chunks=True,
)

for chunk in result.diff_chunks:
    print(chunk)
```

Possible output:

```python
DiffChunk(kind="substitute", original="tama", corrected="tämä")
DiffChunk(kind="substitute", original="hammas laakari", corrected="hammaslääkäri")
```

Use this when you want to inspect exactly what changed, build a UI diff, or analyze correction behavior in more detail.

### `additional_instructions`

When `additional_instructions` is provided, it is appended to the Pass 2 user prompt under an `ADDITIONAL INSTRUCTIONS` section.

This is useful when you want to guide the second pass with task-specific constraints without changing the default Finnish repair policy.

Example:

```python
result = enhancer.enhance_text(
    transcript_text="tama on acme oy projekti",
    additional_instructions="Keep company names and product names exactly as written.",
)
```

This affects only Pass 2. Pass 1 remains unchanged.

### Using Both Together

```python
result = enhancer.enhance_text(
    transcript_text="tama on hammas laakari",
    generate_summary=True,
    diff_chunks=True,
)

print(result.correction_summary)
print(result.diff_chunks)
```

## Default Models

- Azure OpenAI: `gpt-6-luna` (or your `AZURE_DEPLOYMENT`)
- OpenAI: `gpt-6-luna`

## Output Structure

`TranscriptEnhancer` returns a `TranscriptEnhancerResult`, which can be serialized with `model_dump()`:

```json
{
  "original_text": "...",
  "enhanced_text": "...",
  "source_file": "transcript.txt",
  "correction_summary": {
    "total_changes": 4,
    "insertions": 1,
    "deletions": 0,
    "substitutions": 3
  },
  "diff_chunks": [
    {
      "kind": "substitute",
      "original": "hammas laakari",
      "corrected": "hammaslääkäri"
    }
  ],
  "refused_passes": []
}
```

## What the code checks

The prompts tell the model not to change digits and not to rewrite the text. The code
holds each pass to that:

- A pass whose answer changes, adds, removes or reorders any digit is refused.
- A pass that changes more than `max_change_ratio` of its input's letters (default
  `0.25`) is refused. Case, punctuation, spacing (a merged or split compound) and accents
  (a/ä, o/ö) do not count, so `tama on hammas laakari` -> `tämä on hammaslääkäri` passes.
  The result as a whole is held to the same limit against the original, so the two
  passes cannot add up past it.

What this does and does not protect: the ratio stops a wholesale rewrite, such as a
translation or a summary in place of the transcript. It does not stop a small, targeted
change: on a transcript of any length, a dropped negation ("ei vaihdettu" ->
"vaihdettu"), a changed name, a deleted short sentence or a number word changed
(`yhdeksän` -> `kahdeksan`) are well under 25% and pass. The digit check also covers
superscripts, full-width digits and number characters such as ½ and Ⅸ.

A refused pass keeps its input, so the next pass works on it, and it is listed in
`refused_passes` with its reason. `original_text` always keeps the raw transcript and
`correction_summary` is always computed (`generate_summary` is kept for older callers).
`Transcriber(enhanced_transcript=True)` passes `enhancement_max_change_ratio` on and
returns the refusals in `TranscriptionResult.enhancement_refused_passes`.

`TranscriptEnhancer(..., max_change_ratio=None)` turns the ratio check off; the digit
check always applies. What the checks do not catch: a changed decimal separator, sign or
unit next to the same digits (`2,5 mg` -> `2.5 g`), a magnitude word (`miljoonaa` ->
`tuhatta`), a number written as words (`kolme` -> `neljä`) and a changed name
(`Matti` -> `Mikko`). Where figures and names matter, compare `diff_chunks` with the raw
transcript, or keep the raw transcript as the record.

The transcript reaches the model in its own `<source_material>` block, apart from the
rules, which lowers the chance that a sentence spoken in the recording is taken as an
instruction; it does not remove it, and the checks above catch only large or numeric
changes.

## Environment Variables

Azure mode:
- `AZURE_API_KEY`
- `AZURE_ENDPOINT`
- `AZURE_DEPLOYMENT` (optional, default `gpt-6-luna`)
- `AZURE_API_VERSION` (optional override)

OpenAI mode:
- `OPENAI_API_KEY`

## Example

- `implementation_layer/examples/software_components/enhance_transcript/enhance_transcript_example.py`
