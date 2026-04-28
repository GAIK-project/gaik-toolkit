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
