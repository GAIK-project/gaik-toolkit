# Schema Generator

Generate type-safe Pydantic extraction schemas from natural-language requirements.

`schema_generator` is a public import alias for the existing `SchemaGenerator`
implementation in the `extractor` package. It provides a focused namespace for
schema design without duplicating the implementation or creating a second
Solution Wizard component. The original
`gaik.software_components.extractor.SchemaGenerator` import remains supported.

## Installation

```bash
pip install "gaik[extract]"
```

## Quick Start

```python
from gaik.software_components.config import get_openai_config
from gaik.software_components.schema_generator import SchemaGenerator

config = get_openai_config(use_azure=True)

generator = SchemaGenerator(
    config=config,
    model="gpt-6-luna",
    temperature=0.0,
)

schema = generator.generate_schema(
    """
    Extract invoice number, supplier name, invoice date (DD/MM/YYYY),
    and total amount (numeric). Return null for values that are not stated.
    """
)

print(schema.model_json_schema())
print(generator.item_requirements)
```

For reasoning models that do not accept a custom temperature, omit it from the
provider request and set an appropriate reasoning effort:

```python
generator = SchemaGenerator(
    config=config,
    model="gpt-5.6-sol",
    temperature=None,
    reasoning_effort="low",
)
```

`config` can also come from `get_llm_config()` for Google, Anthropic, CSC Aitta,
other OpenAI-compatible servers or optional LiteLLM, e.g.
`SchemaGenerator(config=get_llm_config("aitta"))`. The model must support
structured output. See the
[multi-provider guide](https://gaik-project.github.io/gaik-toolkit/toolkit/multi-provider-llm/).

## API

### `SchemaGenerator`

```python
generator = SchemaGenerator(
    config: dict,
    model: str | None = None,
    *,
    temperature: float | None = 0.0,
    reasoning_effort: str | None = None,
)

schema = generator.generate_schema(user_requirements: str)
result = generator.generate_schema_with_usage(
    user_requirements: str,
    *,
    approved_requirements=None,  # the requirements of the schema a person approved
    approved_structure=None,     # its StructureAnalysis, or "flat" / "nested_list"
)
```

`generate_schema()` returns a Pydantic model class. After generation, parsed
requirements and structure metadata are available through
`generator.item_requirements` and `generator.structure_analysis`.

`generate_schema_with_usage()` returns a `SchemaGenerationResult` containing
the schema, parsed requirements, structure analysis, token usage, duration, and
model identifier, and with `approved_requirements` a `diff`.

### Review a new schema against the approved one

The requirement text steers which fields a generated schema gets, so a field can drop
out or change between two runs. Before a new schema replaces one a person approved,
show them the difference:

```python
result = generator.generate_schema_with_usage(
    text,
    approved_requirements=approved,        # ExtractionRequirements, or the saved dict
    approved_structure=approved_analysis,  # StructureAnalysis or "flat" / "nested_list"
)
if not result.diff.is_empty:
    print(result.diff)   # ! structure, + added, - removed, ~ changed (old -> new)
    # ask for approval before saving result.schema over the approved one
```

- `is_empty` covers what changes the output: fields and child containers added or
  removed (`items[]`), the structure, and each field's type, output policy, allowed
  values (in any order), pattern, format and effective default. A reworded description,
  which a model writes on almost every run, is listed apart in `diff.wording`.
- A flat and a nested-list schema hold the same fields. Pass `approved_structure` to see
  that change; without it `diff.notes` says it cannot be told.
- A wrong `approved_requirements` type raises `TypeError` before any model call.
- `compare_requirements(approved, new, approved_structure=..., new_structure=...)` gives
  the same `SchemaDiff` for any two requirements, e.g. a saved one and an edited one.

gaik does not block a changed schema: the decision stays with the caller.

## Generated Artifacts

When a generated schema is persisted, it consists of two complementary
artifacts:

| Artifact | Purpose |
|----------|---------|
| Pydantic model (`.py`) | The executable structured-output contract used during the LLM call. It defines fields, types, nesting, enums, defaults, descriptions, and extra-field handling. |
| `requirements.json` | The generator's field-level policy metadata, used after the LLM response for deterministic fallback handling and normalization. |

`requirements.json` is not sent to the LLM and does not trigger a second LLM
validation call. Pass the generated model and parsed requirements together to
`DataExtractor`; see the
[Extractor documentation](../extractor/README.md#how-schema-artifacts-are-used)
for the complete runtime flow.

## Example

See the complete
[schema generation example](../../../../examples/software_components/schema-generator/schema_generation_example.py),
including schema and requirements persistence.

## Compatibility

These imports resolve to the same class object:

```python
from gaik.software_components.extractor import SchemaGenerator as ExistingImport
from gaik.software_components.schema_generator import SchemaGenerator as AliasImport

assert AliasImport is ExistingImport
```

The alias package is intentionally excluded from gaik-sync's new-component
discovery. The existing `SchemaGenerator` registry entry remains the single
Solution Wizard representation.

## License

MIT - see [LICENSE](../../../../../LICENSE)
