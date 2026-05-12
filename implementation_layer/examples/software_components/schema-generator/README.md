# Schema Generator Example

This example demonstrates how to use `SchemaGenerator` independently. The example defines one natural-language extraction task in the script and generates a Pydantic schema plus requirements metadata. The generated schema can then be used later by either `DataExtractor` or `VisionExtractor` for structured data extraction.

`SchemaGenerator` first analyzes the task description to determine the output
structure, then parses the requested fields and builds a dynamic Pydantic model.
It can detect and build three schema shapes:

- **Flat object**: one record with scalar fields, such as one incident report,
  one patient summary, or one contract summary.
- **Nested list**: one repeated collection of records, such as table rows,
  invoice lines, events, or action items.
- **Parent with nested list**: one parent object with document-level fields plus
  one repeated child collection, such as purchase order header fields plus line
  items.

Alongside the Pydantic model, it also creates `requirements.json`, which stores
field metadata used later for post-processing, defaults, date normalization, and
schema reuse.

## Example Script

```text
implementation_layer/examples/software_components/schema-generator/schema_generation_example.py
```

Run it from this folder:

```bash
cd implementation_layer/examples/software_components/schema-generator
python schema_generation_example.py
```

The script creates:

```text
schema_generated_single_doc/
```

The generated folder contains:

```text
schema.py
requirements.json
schema_info.json
```

## API Credentials

`SchemaGenerator` uses OpenAI/Azure OpenAI. Set API credentials before running
the script. In a source checkout, a reliable `.env` location is the repository
root, or export the variables in your shell/session.

For Azure OpenAI:

```text
AZURE_API_KEY=...
AZURE_ENDPOINT=...
AZURE_DEPLOYMENT=...
AZURE_API_VERSION=2025-03-01-preview
```

For standard OpenAI:

```text
OPENAI_API_KEY=...
OPENAI_MODEL=...
```

The example currently uses:

```python
get_openai_config(use_azure=True)
```

Change this to `use_azure=False` if you want to use standard OpenAI.

## Using The Generated Schema With DataExtractor

The generated `schema.py` contains a Pydantic model class. The generated
`requirements.json` contains the field metadata needed for post-processing and
normalization.

Minimal example:

```python
import importlib.util
import json
from pathlib import Path

from gaik.software_components.extractor import DataExtractor
from gaik.software_components.extractor.schema import (
    CompositeExtractionRequirements,
    ExtractionRequirements,
)
from gaik.software_components.config import get_openai_config


schema_dir = Path("schema_generated_single_doc")
schema_path = schema_dir / "schema.py"
requirements_path = schema_dir / "requirements.json"

payload = json.loads(requirements_path.read_text(encoding="utf-8"))
model_name = payload["model_name"]

if payload.get("requirements_type") == "parent_with_nested_list":
    requirements = CompositeExtractionRequirements(**payload["requirements"])
else:
    requirements = ExtractionRequirements(**payload["requirements"])

spec = importlib.util.spec_from_file_location("_generated_schema", schema_path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
extraction_model = getattr(module, model_name)

config = get_openai_config(use_azure=True)
extractor = DataExtractor(config=config)

results = extractor.extract(
    extraction_model=extraction_model,
    requirements=requirements,
    user_requirements="Extract the requested fields from the document text.",
    documents=[
        "Paste or provide already-parsed text/Markdown here."
    ],
)

print(results)
```

Use `DataExtractor` when your input is already reliable text or Markdown. Use
`VisionExtractor` when you need the LLM to inspect the original PDF/image layout
and extract structured data in one call.
