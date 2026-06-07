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

When `provider: azure_openai`, `output_schema.py` must never contain `dict | None` or `list[dict]` as field types. The API requires `additionalProperties: false` on every JSON object; bare Python `dict` does not satisfy this and returns HTTP 400.

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
