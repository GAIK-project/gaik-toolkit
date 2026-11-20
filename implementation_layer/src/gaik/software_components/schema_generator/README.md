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

With a temperature (the default `0.0`) and no `reasoning_effort`, the
requirements parses send GPT-6 Sol/Luna and GPT-5.6 Sol/Luna/Terra (by name, or
by `model_family` in the config) `reasoning_effort="none"`, so the temperature
applies and they do not reason. With reasoning and free sampling these models
sometimes kept only the first field of a task. The structure detection call keeps
the model's default: without reasoning it often ignored a list name the task
gave. An effort in the call or in the config is sent as given to every call.
Other models get no effort, including GPT-6 Astra, gpt-6-rosalind and gpt-6.x,
which reject `"none"`. Through LiteLLM both the routed name and `model_family`
must be on that list, since LiteLLM refuses `"none"` for a name it does not know.

To have a reasoning model reason, omit the temperature from the provider request
and set an appropriate reasoning effort:

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
    approved_structure=None,     # its StructureAnalysis (or dict), or "flat" / "nested_list"
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
    approved_structure=approved_analysis,  # StructureAnalysis, its dict, "flat" or "nested_list"
)
if not result.diff.is_empty:
    print(result.diff)   # ! structure, + added, - removed, ~ changed (old -> new), notes
    # ask for approval before saving result.schema over the approved one
```

- Ask for approval unless `is_empty` is true. `is_empty` is true only when nothing
  differs and nothing is unknown. A reworded description counts: the description is
  what the extraction model reads, so "net amount" becoming "gross amount" changes the
  result. `str(diff)` shows both texts. `changes_output` is the narrower test (fields
  and child containers added or removed as `items[]`, the structure, and each field's
  type, output policy, allowed values in any order, pattern, format and effective
  default).
- A flat and a nested-list schema hold the same fields. Pass `approved_structure`
  (`"flat"`, `"nested_list"`, or the approved `StructureAnalysis` or its saved
  `model_dump()` dict) to compare it; without it `diff.notes` says so and `is_empty` is
  false. A nested-list schema's list container (the output's top-level key) and its
  description are compared only from the `StructureAnalysis` or its dict; with
  `"nested_list"` a note says a renamed container cannot be seen.
- Names and values in `str(diff)` are quoted and cut to 200 characters, so a name or a
  value from a saved or edited dict cannot make up a diff line. Letters that only look
  alike (Latin and Cyrillic) are not told apart on screen.
- A wrong `approved_requirements` type raises `TypeError`, and a wrong
  `approved_structure` raises `ValueError`, before any model call.
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
