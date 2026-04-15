---
name: gaik-add-examples
description: >-
  Adds or updates working code examples for GAIK toolkit components and pipelines
  in implementation_layer/examples/. Use when adding a new example, demonstrating
  a feature, creating a usage sample, or showing how a building block or pipeline
  works. Covers software_components (extractor, parsers, transcriber, RAG, etc.)
  and software_modules (AudioToStructuredData, DocumentsToStructuredData, RAGWorkflow).
---

# Add GAIK Examples

Examples live in `implementation_layer/examples/` split into two categories:

- `software_components/` — individual building blocks (extractor, parsers, transcriber, RAG, etc.)
- `software_modules/` — end-to-end pipelines (audio_to_structured_data, documents_to_structured_data, RAG_workflow)

## Steps

1. **Choose the right location**
   - New building block example → `software_components/<component_name>/`
   - New pipeline example → `software_modules/<pipeline_name>/`
   - Adding to existing component → add numbered file: `component_example_2.py`, `component_example_3.py`

2. **Follow the standard file structure**

```python
"""
Example: [one-line summary]
Workflow: [input] -> [step1] -> [step2] -> [output]
"""

from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv

# Load environment variables before importing gaik modules
load_dotenv(Path(__file__).parent.parent.parent / ".env")

# Add src directory to path to import modules (works without pip install)
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from gaik... import ...


def main() -> None:
    # example code here


if __name__ == "__main__":
    main()
```

   **Adjust `.parent` depth** to reach `implementation_layer/` from the example file's location.
   - `software_components/<comp>/example.py` → `.parent.parent.parent` for `.env`, `.parent.parent.parent.parent / "src"` for src
   - `software_modules/<mod>/example.py` → same depth
   - Subdirectory example (e.g. `software_modules/<mod>/subdir/example.py`) → add one more `.parent`

3. **Add or update README.md** in the component/module directory covering:
   - Prerequisites (pip extras: e.g. `pip install "gaik[extract]"`, required env vars)
   - How to run: `python example.py`
   - What the example demonstrates

4. **Update the parent README.md** (`software_components/README.md` or `software_modules/README.md`) to list the new example.

5. **Add sample input files if needed** (PDFs, audio files, images) to an `input/` subdirectory.

## Configuration pattern

All examples use the same config — always import from `gaik.software_components.config`:

```python
from gaik.software_components.config import get_openai_config, create_openai_client

config = get_openai_config(use_azure=True)   # Azure OpenAI
config = get_openai_config(use_azure=False)  # Standard OpenAI
client = create_openai_client(config)        # OpenAI/AzureOpenAI client
```

Pipeline constructors accept `use_azure=True/False` directly:

```python
pipeline = DocumentsToStructuredData(use_azure=True)
```

## Notes

- Examples serve as both usage documentation and integration tests
- Keep each file focused on one concept — add a new numbered file for a new concept
- Real-world complexity examples go in a subdirectory (e.g., `diary_workflow/`)
- After adding examples, also update `guidance_layer/docs/` and `guidance_layer/website/content/docs/` if documenting a new capability — see the `gaik-toolkit` skill for the documentation update table
