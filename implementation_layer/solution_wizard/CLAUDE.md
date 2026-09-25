# Solution Wizard — Claude Code Notes

## Schema generation constraints

Two constraints must be checked every time a GAIK extraction schema is generated or manually edited. Both caused runtime failures during a hospital admissions PoC (2026-06-06) and are now enforced in SKILL.md Phase 4.

### 1. ExtractionRequirements `field_type` enum

When editing `output_schema_requirements.json` directly, `field_type` must be one of:
`str` | `int` | `float` | `bool` | `list[str]` | `date` | `decimal` | `list[dict]`

`"dict"` is **not** in this enum — it causes `pydantic_core.ValidationError` at runtime when `ExtractionRequirements(**data)` is called. Use:
- `"str"` for a single nested object field
- `"list[dict]"` for an array of objects

### 2. Azure OpenAI structured output rejects bare `dict` types

When `provider: azure` (also the legacy `azure_openai` alias or Azure through LiteLLM), `output_schema.py` must never contain `dict | None` or `list[dict]` as field types. The API requires `additionalProperties: false` on every JSON object; bare Python `dict` does not satisfy this and returns HTTP 400.

Replace with a named Pydantic sub-model:

```python
class Medication(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str | None = None
    dose: str | None = None
    frequency: str | None = None
```

Then use `list[Medication] | None` instead of `list[dict] | None`.

This applies to any field described as a nested object: medications, social history, address, line items, etc. If the GAIK SchemaGenerator emits `list[dict]` for such a field, replace it with a named sub-model before presenting the schema to the user.

**Where these rules are enforced in code:**
- `SKILL.md` Phase 4 — constraint checklist before schema approval (Step 4.6)
- `registries/gaik_component_registry.json` — Extractor `known_limitations`
- `src/solution_wizard/schema_designer.py` — `_TYPE_MAP` maps `dict`/`object` to `str`, not bare `dict`

## Provider configuration when wiring a PoC

Use the generated `provider_config.get_stage_config(config, stage)` helper for
`transcription`, `parser`, `extraction`, `embedding`, `answer`, and `judge`.
It resolves the selected provider through `get_llm_config`; do not reduce all
providers to the old `use_azure` flag or copy a credential-bearing config while
changing its provider. Reference-card constructs assume this helper is imported.

`gpt-6-luna` is the default OpenAI/Azure text-model suggestion, subject to actual
account access and Azure deployment naming. Native provider IDs include `azure`,
`anthropic_foundry` and `vertex`; `azure_openai` remains a legacy blueprint alias
that the scaffolder and `get_stage_config` map to `azure` (gaik's `get_llm_config`
rejects it). Aitta, generic OpenAI-compatible endpoints and the optional LiteLLM
backend use the same component config contract, with model-specific capabilities.
LiteLLM models carry their routing prefix; native model IDs do not.

Keep audio on native OpenAI/Azure (or an explicitly configured existing local
Whisper mode), and select embeddings separately from chat. Image input and
structured output must be supported by the actual selected model. For stage
overrides, use the constructor/config names in the reference cards; they differ
between modules. Secrets belong only in the runtime environment, never blueprints
or saved report configurations.

For the default GPT-6 setup omit temperature unless using supported disabled
reasoning. GPT-6 Astra does not support `reasoning_effort='none'`; Sol/Luna do.
Custom Azure deployment names need `model_family` for family normalization.
PostgresAgent/TabularAgent drop their `0.0` temperature default for GPT-6/GPT-5.6
automatically; pass `temperature=None` only for other reasoning deployments that
reject it (o-series, older gpt-5.x reasoning tiers). Follow SKILL.md Phase 6 and
the card's current options instead of the obsolete blanket restriction against every
model newer than GPT-5.4.
