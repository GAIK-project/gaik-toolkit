# LLM-as-Judge Validator

Multi-provider LLM-as-judge validator for structured-extraction outputs.
Feeds page images plus an extractor's JSON to a vision-capable LLM and
returns per-field flags (`wrong` / `suspect` / `ok`) with reasons and
suggested values.

Useful when an upstream extractor (e.g. `MultimodalParser` + a structured-output
LLM) produced JSON and you want a *second* model to read the source and tell
you which fields look broken before you act on them downstream.

## Installation

```bash
pip install gaik[llm-judge]
```

This pulls in the Anthropic and Google provider SDKs. OpenAI / Azure are
already in the toolkit's core deps.

**Note:** Requires API access to at least one of OpenAI / Azure OpenAI /
Anthropic / Google Vertex.

---

## Quick Start

```python
from gaik.software_components.validators import LLMJudge, ValidationRubric

judge = LLMJudge(
    model_provider="google",                 # winner of the Luvata judge benchmark
    model="gemini-3-flash-preview",
    use_vertexai=True,
)

result = judge.validate(
    source_pages=[png_bytes_page1, png_bytes_page2],
    extracted=[
        {"item_index": 0, "item_number": "0010", "quantity": "940"},
        {"item_index": 1, "item_number": "0020", "quantity": "947"},
    ],
    rubric=ValidationRubric(
        vendor_id="copper-brass",
        field_checks=[
            "Quantity is integer pounds before decimal — '4,279.940 LB' = 4279.",
        ],
    ),
)

for flag in result.flags:
    print(flag.field, flag.severity, flag.reason, flag.suggested_value)

print(f"Cost: ${result.usage.cost_usd:.4f}, duration: {result.usage.duration_s:.1f}s")
```

See the [demo example](https://github.com/GAIK-project/gaik-toolkit/blob/main/implementation_layer/examples/software_components/validators/demo_llm_judge.py)
for a complete script that renders a PDF to PNG bytes via PyMuPDF.

---

## Features

- **Multi-Provider** — same code talks to OpenAI, Azure OpenAI, Anthropic
  Foundry, or Google Vertex via the toolkit's existing config helpers.
- **Per-Field Flags** — each flag carries `(item_index, field, severity,
  confidence, reason, suggested_value)`; severity is one of `ok`,
  `suspect`, `wrong`.
- **Document-Level Flags** — `item_index = -1` is reserved for structural
  observations (e.g. "extractor missed 12 of 14 items").
- **Vendor Rubrics** — pass an optional `ValidationRubric` with vendor- or
  use-case-specific checks; the toolkit stays domain-agnostic.
- **Cost Tracking** — `JudgeUsage` returns input/output tokens, duration,
  and USD cost with longest-prefix model-id matching (so a rotated model
  id like `gemini-3-flash-Q3` still resolves to the closest known rate).
- **JSON-Tolerant Parser** — `parse_judge_flags()` strips stray markdown
  fences and silently drops malformed entries.

---

## Basic API

### LLMJudge

```python
from gaik.software_components.validators import LLMJudge

judge = LLMJudge(
    model_provider: Literal["openai", "azure", "anthropic", "google"] = "google",
    model: str | None = None,                # provider default if None
    use_azure: bool = True,                  # only relevant when provider="openai"
    use_vertexai: bool = True,               # only relevant when provider="google"
    max_tokens: int = 4096,
    reasoning_effort: str | None = None,     # "low" | "medium" | "high" for reasoning models
)
```

### `validate(...) -> ValidationResult`

```python
result = judge.validate(
    source_pages=[png_bytes, ...],           # required, ≥1 page
    extracted=[{...}],                       # free-form JSON (list or dict)
    rubric=None,                             # optional ValidationRubric
)
# result.flags          : list[ValidationFlag]
# result.raw_judge_text : str (the model's untouched response)
# result.usage          : JudgeUsage
```

---

## Result Types

```python
@dataclass
class ValidationFlag:
    item_index: int                # -1 for document-level
    field: str
    severity: Literal["ok", "suspect", "wrong"]
    confidence: float
    reason: str
    suggested_value: str | None

@dataclass
class JudgeUsage:
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    duration_s: float
    cost_usd: float
```

---

## Rubric API

```python
@dataclass
class ValidationRubric:
    vendor_id: str | None = None
    field_checks: list[str] = []         # bulleted into the user prompt
    item_level_checks: list[str] = []    # for cross-item / structural checks
    custom_system_suffix: str | None = None
```

The rubric is optional. With no rubric the judge runs a generic prompt
("flag fields whose value doesn't match the page images"). With a rubric
the judge gets a vendor-specific checklist appended to the user prompt.

---

## Picking a Model

We benchmarked eight judge models on five hand-curated Luvata test cases
(see [`ParseBench/results-luvata/judge-bench/BENCHMARK-REPORT.md`](https://github.com/GAIK-project/parse-bench-test/blob/main/results-luvata/judge-bench/BENCHMARK-REPORT.md)):

| Pipeline | F1 | Precision | Recall | Cost / call | Latency |
|---|---:|---:|---:|---:|---:|
| `gemini-3-flash-preview` (Vertex) | **1.000** | 1.000 | 1.000 | $0.0041 | 37.6 s |
| `claude-sonnet-4-6` (Anthropic Foundry) | 0.769 | 0.714 | 0.833 | $0.0274 | 11.2 s |
| `gpt-5.5` / `gpt-5.4` / `gpt-5.4-mini` (Azure) | 0.750 | 0.600 | 1.000 | $0.004–0.024 | 11–25 s |
| `gemini-3.1-flash-lite-preview` (Vertex) | 0.750 | 0.600 | 1.000 | $0.0013 | 3.6 s |
| `claude-opus-4-7` (Anthropic Foundry) | 0.667 | 0.500 | 1.000 | $0.1780 | 10.5 s |
| `claude-haiku-4-5` (Anthropic Foundry) | 0.522 | 0.353 | 1.000 | $0.0059 | 4.1 s |

Recommendation: **Gemini 3 Flash via Vertex** as the default. For two-tier
setups, Gemini 3.1 Flash Lite is the cheapest screener.

---

## Environment Variables

| Variable | Used by |
|---|---|
| `AZURE_API_KEY`, `AZURE_RESOURCE_NAME`, `AZURE_API_VERSION`, `AZURE_DEPLOYMENT` | Azure OpenAI |
| `OPENAI_API_KEY` | Direct OpenAI |
| `ANTHROPIC_API_KEY` | Direct Anthropic |
| `ANTHROPIC_FOUNDRY_RESOURCE` (+ `AZURE_API_KEY`) | Anthropic on Azure AI Foundry (auto-detected) |
| `GOOGLE_VERTEXAI_PROJECT`, `GOOGLE_APPLICATION_CREDENTIALS` | Vertex AI (preferred) |
| `GOOGLE_GEMINI_API_KEY` | Generative Language API (alternative) |

The judge reuses provider configuration helpers from
`gaik.software_components.parsers.multimodal_parser.config`, so the same
env-vars work for both.

---

## Text-vs-Text Equivalence (`judge_text_pair`)

Sometimes there is no source PDF — only two strings to compare. For example,
when scoring an audio-transcription extractor against hand-annotated free-text
ground truth, exact-string match misses paraphrases and morphological variation
("kärsätrukin kärsästä puuttuu pultti" vs "Kärsätrukista puuttui pultti" — same
fact, different wording).

`LLMJudge.judge_text_pair()` solves this by comparing the two values directly,
no images required. Returns a small `TextJudgement` with severity, Likert
score, and reason.

```python
from gaik.software_components.validators import LLMJudge

judge = LLMJudge(model_provider="azure")

verdict = judge.judge_text_pair(
    extracted_text="Tietokonetta ei oltu lukittu.",
    expected_text="Tietokonetta ei ollut lukittu.",
    field_name="Mitä tapahtui",
)
print(verdict.equivalent, verdict.severity, verdict.score, verdict.reason)
# True ok 5 'Identical meaning, only minor verb form variation.'
```

`ExtractionEvaluator(match_mode="semantic", judge=judge)` uses this method
internally to grade ambiguous free-text fields on a 1–5 scale (`score >= 4`
counts as a match).

```python
@dataclass
class TextJudgement:
    equivalent: bool                          # True if the two texts are the same fact
    severity: Literal["ok", "suspect", "wrong"]
    score: int                                 # Likert 1-5
    reason: str
    usage: JudgeUsage
```

See the [demo example](https://github.com/GAIK-project/gaik-toolkit/blob/main/implementation_layer/examples/software_components/validators/demo_llm_judge_text_pair.py)
for a runnable script that scores Finnish field pairs against an Azure-hosted
gpt-5.4 deployment.

---

## Hallucination Detection (`detect_hallucinations`)

The third public method on `LLMJudge` flags fields whose values are not
supported by a source document — a **schema-agnostic** alternative to
hand-written keyword post-validators.

Given a transcript (or any text source) and an extractor's structured
output, the judge inspects the JSON as a whole and returns one
`HallucinationFlag` per problem field. Empty fields are never flagged.

```python
from gaik.software_components.validators import LLMJudge

judge = LLMJudge(model_provider="azure")

report = judge.detect_hallucinations(
    source_text=(
        "Maintenance round on 2025-09-12. Coolant leak under unit B; "
        "absorbent mat applied. Source not yet identified."
    ),
    extracted={
        "report_date": "2025-09-12",
        "location": "unit B",
        "issue_type": "coolant leak",
        "actions_taken": "absorbent mat applied",
        "priority": "high",                     # not stated
        "follow_up_date": "2025-09-15",         # not stated
    },
    field_descriptions={                         # optional per-field rules
        "priority":
            "Return only if explicitly classified in the source.",
    },
)

for flag in report.flags:
    print(flag.field, flag.severity, flag.reason)
# priority         wrong   Source describes the issue but never assigns a priority.
# follow_up_date   wrong   No follow-up date is stated in the source.
```

Use this to clear flagged values before persisting / showing them to the
user. Cost is one LLM call per scrub (typically ≤ 200 output tokens), and
the judge handles all fields in a single call rather than once per field.

```python
@dataclass
class HallucinationFlag:
    field: str                              # exact JSON key
    value: str                              # extracted value (rendered)
    severity: Literal["wrong", "suspect"]   # "ok" entries are dropped
    reason: str                             # ≤25-word explanation


@dataclass
class HallucinationReport:
    flags: list[HallucinationFlag]
    raw_judge_text: str
    usage: JudgeUsage
```

See the [demo example](https://github.com/GAIK-project/gaik-toolkit/blob/main/implementation_layer/examples/software_components/validators/demo_detect_hallucinations.py)
for a runnable script that scrubs a Finnish audio-incident-report
extraction in two LLM calls.

---

## Use Cases

- Purchase-order extraction QA (the original driver — see
  [Luvata OC Builder](https://github.com/GAIK-project/Luvata) for a full
  consumer integration with vendor-specific rubrics).
- Invoice / receipt structured-extraction sanity check.
- Form / claim review where missing or hallucinated fields are
  expensive downstream.
- Two-tier setups: cheap pre-screen + premium judge on flagged rows.

## License

MIT - see [LICENSE](https://github.com/GAIK-project/gaik-toolkit/blob/main/LICENSE)
