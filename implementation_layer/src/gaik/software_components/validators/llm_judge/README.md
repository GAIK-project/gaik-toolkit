# LLM-as-Judge Validator

Multi-provider LLM-as-judge validator for structured-extraction outputs. Feeds
page images plus the extractor's JSON to a vision-capable LLM and gets back
per-field `wrong` / `suspect` / `ok` flags with reasons and suggested values.

Useful when an upstream extractor (e.g. `MultimodalParser` + a structured-output
LLM) produced JSON and you want a *second* model to read the source and tell
you which fields look broken before you act on them downstream.

## Installation

```bash
pip install gaik[llm-judge]
```

This pulls in the Anthropic and Google provider SDKs. OpenAI / Azure are
already in the toolkit's core deps.

## Quick Start

```python
from gaik.software_components.validators import LLMJudge, ValidationRubric

judge = LLMJudge(
    model_provider="google",                    # winner of Luvata judge benchmark
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

See the [example](../../../../examples/software_components/validators/demo_llm_judge.py)
for a complete working script that renders a PDF to PNG bytes via PyMuPDF.

## Picking a model

We benchmarked seven judge models on five hand-curated Luvata test cases
(see `ParseBench/results-luvata/judge-bench/BENCHMARK-REPORT.md`):

| Pipeline | F1 | Precision | Recall | Cost / call | Latency |
|---|---:|---:|---:|---:|---:|
| `gemini-3-flash-preview` (Vertex) | 1.000 | 1.000 | 1.000 | $0.0041 | 37.6 s |
| `gpt-5.5` / `gpt-5.4` / `gpt-5.4-mini` | 0.750 | 0.600 | 1.000 | $0.004–0.024 | 11–25 s |
| `gemini-3.1-flash-lite-preview` | 0.750 | 0.600 | 1.000 | $0.0013 | 3.6 s |

Recommendation: **Gemini 3 Flash via Vertex** as the default. For two-tier
setups, Gemini 3.1 Flash Lite is the cheapest screener.

## API

```python
class LLMJudge:
    def __init__(
        self,
        model_provider: Literal["openai", "azure", "anthropic", "google"] = "google",
        model: str | None = None,
        use_azure: bool = True,
        use_vertexai: bool = True,
        max_tokens: int = 4096,
        reasoning_effort: str | None = None,
    ): ...

    def validate(
        self,
        source_pages: list[bytes],
        extracted: list[dict] | dict,
        rubric: ValidationRubric | None = None,
    ) -> ValidationResult: ...
```

The judge reuses provider configuration helpers from
`gaik.software_components.parsers.multimodal_parser.config`, so the same
env-vars work for both:

| Variable | Used by |
|---|---|
| `AZURE_API_KEY`, `AZURE_RESOURCE_NAME`, `AZURE_API_VERSION`, `AZURE_DEPLOYMENT` | Azure OpenAI |
| `OPENAI_API_KEY` | OpenAI |
| `ANTHROPIC_API_KEY` | Anthropic direct |
| `ANTHROPIC_FOUNDRY_API_KEY`, `ANTHROPIC_FOUNDRY_RESOURCE` | Anthropic on Azure AI Foundry (auto-detected) |
| `GOOGLE_VERTEXAI_PROJECT`, `GOOGLE_APPLICATION_CREDENTIALS` | Vertex AI (preferred) |
| `GOOGLE_GEMINI_API_KEY` | Generative Language API (alternative) |

## License

MIT — see [LICENSE](../../../../../LICENSE).
