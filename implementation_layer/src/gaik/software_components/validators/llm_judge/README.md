# LLM-as-Judge Validator (v2)

Multi-provider LLM-as-judge validator for structured-extraction outputs. Feeds
page images plus the extractor's JSON to a vision-capable LLM and returns
per-field flags with severity, reason, suggested values — and (optionally) an
integer Likert 1-5 score.

Useful when an upstream extractor (e.g. `MultimodalParser` + a structured-output
LLM) produced JSON and you want a *second* model to read the source and tell
you which fields look broken before you act on them downstream.

## What's new in v2 (2026 research-backed)

- **Integer Likert 1-5 scoring** alongside severity. HuggingFace cookbook
  reports ~30 % better human-correlation than continuous scales.
- **Few-shot calibration** via `ValidationRubric.few_shot_examples` (1-2 is
  the sweet spot — more give diminishing returns).
- **Per-aspect evaluation focus** via `ValidationRubric.evaluation_aspects`
  (each is one atomic criterion the judge should consider separately).
- **Bias-mitigation guidance** in the system prompt: anti-verbosity,
  anti-formatting-bias, evaluation-before-judgement order.
- **Panel/jury aggregation** via `LLMJudgePanel` (3+ judges, majority vote,
  agreement metric — mitigates single-model self-preference bias).
- **Calibration utility** `calibrate_against_human_labels` returning Pearson
  r vs. human raters and severity-agreement rate.
- **Pairwise A/B** via `compare_pairwise(swap_and_average=True)` — runs the
  comparison twice with A/B swapped and only reports a winner when both
  passes agree (mitigates ~40 % position-bias decision flips).

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
    model_provider="google",                    # winner of internal judge benchmark
    model="gemini-3-flash-preview",
    use_vertexai=True,
)

result = judge.validate(
    source_pages=[png_bytes_page1, png_bytes_page2],
    extracted=[
        {"item_index": 0, "item_number": "0010", "quantity": "10"},
        {"item_index": 1, "item_number": "0020", "quantity": "20"},
    ],
    rubric=ValidationRubric(
        vendor_id="acme-supply",
        scoring_mode="likert_1_5",                              # NEW
        evaluation_aspects=[                                    # NEW
            "Quantity is the ordered amount, not unit price",
        ],
        field_checks=[
            "Quantity is the line-amount column, not the unit-price column.",
        ],
    ),
)

for flag in result.flags:
    print(flag.field, flag.severity, f"{flag.score}/5", flag.reason, flag.suggested_value)

print(f"Cost: ${result.usage.cost_usd:.4f}, duration: {result.usage.duration_s:.1f}s")
```

See the [examples folder](../../../../examples/software_components/validators/)
for working scripts:

- `demo_llm_judge.py` — single-judge basic usage with Likert scoring.
- `demo_likert_scoring.py` — few-shot calibration on top of Likert mode.
- `demo_panel_jury.py` — three-judge majority vote with `LLMJudgePanel`.
- `demo_pairwise.py` — A/B comparison with `compare_pairwise(swap_and_average=True)`.
- `demo_calibration.py` — Pearson-r calibration vs. a human-labeled dataset.

## Picking a model

We benchmarked seven judge models on a small hand-curated set of
purchase-order extraction-validation test cases:

| Pipeline | F1 | Precision | Recall | Cost / call | Latency |
|---|---:|---:|---:|---:|---:|
| `gemini-3-flash-preview` (Vertex) | 1.000 | 1.000 | 1.000 | $0.0041 | 37.6 s |
| `gpt-5.5` / `gpt-5.4` / `gpt-5.4-mini` | 0.750 | 0.600 | 1.000 | $0.004–0.024 | 11–25 s |
| `gemini-3.1-flash-lite-preview` | 0.750 | 0.600 | 1.000 | $0.0013 | 3.6 s |

Recommendation: **Gemini 3 Flash via Vertex** as the default. For two-tier
setups, Gemini 3.1 Flash Lite is the cheapest screener.

## Scoring modes

| `scoring_mode` | Output | When to use |
|---|---|---|
| `"severity"` (default) | severity only — `flag.score = 0` | Simple yes/no/maybe gates; existing v1 callers. |
| `"likert_1_5"` | severity + integer 1-5 score | Calibration, regression-tracking, anywhere you want a stable numeric metric. |
| `"additive"` | severity + 1 point per `evaluation_aspect` | When the rubric is a checklist of independent criteria. |

The severity-to-score mapping the prompt enforces:

- score 1 → "wrong"
- score 2-3 → "suspect"
- score 4-5 → "ok"

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


class LLMJudgePanel:
    def __init__(self, judges: list[LLMJudge]): ...  # 2+ judges required
    def validate(self, source_pages, extracted, rubric=None) -> JudgePanelResult: ...


def compare_pairwise(
    judge: LLMJudge,
    source_pages: list[bytes],
    extracted_a, extracted_b,
    swap_and_average: bool = True,
) -> PairwiseResult: ...


def calibrate_against_human_labels(
    judge: LLMJudge,
    dataset: list[CalibrationItem],
    rubric: ValidationRubric | None = None,
    field_filter: str | None = None,
) -> CalibrationReport: ...
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

## Research references

- [HuggingFace LLM Judge Cookbook](https://huggingface.co/learn/cookbook/llm_judge) — Likert vs. float, few-shot, evaluation order.
- [A Survey on LLM-as-a-Judge (arXiv 2411.15594)](https://arxiv.org/abs/2411.15594) — bias taxonomy, panel/jury patterns.
- [Justice or Prejudice? Quantifying Biases in LLM-as-a-Judge (OpenReview)](https://openreview.net/forum?id=3GTtZFiajM) — position-bias measurement.
- [Self-Preference Bias in LLM Judges (arXiv 2604.22891)](https://arxiv.org/html/2604.22891) — why cross-model judging matters.
- [Evaluating and Mitigating LLM-as-a-judge Bias in Communication Systems (arXiv 2510.12462)](https://arxiv.org/abs/2510.12462) — 11 bias types, mitigation strategies.

## License

MIT — see [LICENSE](../../../../../LICENSE).
