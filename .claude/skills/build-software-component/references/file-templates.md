# File Templates

Literal templates for every file the skill creates or edits. Replace
`{{PLACEHOLDER}}` markers with values from the approved plan.

## Contents

- Placeholder reference
- Template 1 — `<component_name>/__init__.py`
- Template 2 — `<component_name>/<component_name>.py` (LLM-based)
- Template 3 — `<component_name>/<component_name>.py` (provider-agnostic)
- Template 4 — `<component_name>/README.md`
- Template 5 — Example file
- Template 6 — `pyproject.toml` edit
- Template 7 — `software_components/__init__.py` edit (top-level)
- Template 8 — category `__init__.py` edit (nested)

## Placeholder reference

- `{{component_name}}` — snake_case directory/import name, e.g. `doc_classifier`.
- `{{ComponentTitle}}` — human-readable title, e.g. `Document Classifier`.
- `{{MainClassName}}` — PascalCase class name, e.g. `DocumentClassifier`.
- `{{one_line_description}}` — single sentence describing the component.
- `{{extra_name}}` — hyphenated extras name, e.g. `doc-classifier`.
- `{{usage_snippet}}` — a minimal working code snippet.
- `{{method_name}}` — the main public method name.
- `{{dep_pins}}` — list of pinned dependency strings (may be empty).

---

## Template 1 — `<component_name>/__init__.py`

Use this for LLM-based components. Drop the `create_openai_client` /
`get_openai_config` re-exports if the component is provider-agnostic.

```python
"""{{ComponentTitle}}

{{one_line_description}}

Main Classes:
    - {{MainClassName}}: {{one_line_description}}

Configuration:
    - get_openai_config: Get OpenAI/Azure configuration
    - create_openai_client: Create OpenAI client from config

Example:
{{usage_snippet_as_doctest}}
"""

from gaik.software_components.config import create_openai_client, get_openai_config

from .{{component_name}} import {{MainClassName}}

__all__ = [
    "{{MainClassName}}",
    "get_openai_config",
    "create_openai_client",
]

__version__ = "0.1.0"
```

Provider-agnostic variant (no LLM calls at all):

```python
"""{{ComponentTitle}}

{{one_line_description}}

Main Classes:
    - {{MainClassName}}: {{one_line_description}}
"""

from .{{component_name}} import {{MainClassName}}

__all__ = [
    "{{MainClassName}}",
]

__version__ = "0.1.0"
```

---

## Template 2 — `<component_name>/<component_name>.py` (LLM-based)

```python
"""{{one_line_description}}

This module implements {{MainClassName}}, which {{one_line_description_lowercase}}.
"""

from __future__ import annotations

import logging
from pathlib import Path

from gaik.software_components.config import create_openai_client

logger = logging.getLogger(__name__)


class {{MainClassName}}:
    """{{one_line_description}}"""

    def __init__(self, config: dict, model: str | None = None):
        """
        Initialize {{MainClassName}}.

        Args:
            config: OpenAI config from `get_openai_config()`.
            model: Optional model override. Defaults to `config["model"]`.
        """
        self.config = config
        self.model = model or config["model"]
        self.client = create_openai_client(config)

    def {{method_name}}(self, *args, **kwargs):
        """<fill in from plan — primary entry point>"""
        raise NotImplementedError
```

Replace the `{{method_name}}` stub with the real method(s) from the plan,
implemented to call `self.client` and return the result shape described in
the plan's Public API section.

---

## Template 3 — `<component_name>/<component_name>.py` (provider-agnostic)

```python
"""{{one_line_description}}"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class {{MainClassName}}:
    """{{one_line_description}}"""

    def __init__(self, **kwargs):
        # Fill in from the plan's Public API section.
        pass

    def {{method_name}}(self, *args, **kwargs):
        """<fill in from plan>"""
        raise NotImplementedError
```

---

## Template 4 — `<component_name>/README.md`

```markdown
# {{ComponentTitle}}

{{one_line_description}}

## Installation

```bash
pip install gaik[{{extra_name}}]
```

**Note:** Requires OpenAI or Azure OpenAI API access (for LLM-based components).

---

## Quick Start

```python
{{usage_snippet}}
```

---

## API

### {{MainClassName}}

```python
from gaik.software_components.{{component_name}} import {{MainClassName}}

instance = {{MainClassName}}(config=config)
result = instance.{{method_name}}(...)
```

See the [example](../../examples/software_components/{{component_name}}/{{component_name}}_example.py)
for a complete working script.

---

## Environment Variables (LLM-based components only)

| Variable | Required | Description |
|----------|----------|-------------|
| `AZURE_API_KEY` | Azure only | Azure OpenAI API key |
| `AZURE_ENDPOINT` | Azure only | Azure OpenAI endpoint URL |
| `AZURE_DEPLOYMENT` | Azure only | Azure deployment name |
| `OPENAI_API_KEY` | OpenAI only | Standard OpenAI API key |

## License

MIT - see [LICENSE](../../../../LICENSE)
```

---

## Template 5 — Example file

Path: `implementation_layer/examples/software_components/{{component_name}}/{{component_name}}_example.py`

```python
"""{{ComponentTitle}} Example

Demonstrates how to use the {{component_name}} component.
"""

import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / ".env")

# Allow running without `pip install -e .`
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from gaik.software_components.{{component_name}} import {{MainClassName}}, get_openai_config  # noqa: E402


def basic_example():
    """Minimal usage example."""
    config = get_openai_config(use_azure=True)
    instance = {{MainClassName}}(config=config)

    # Replace with a real call from the plan's Example usage section.
    result = instance.{{method_name}}(...)
    print(result)


if __name__ == "__main__":
    basic_example()
```

For provider-agnostic components, drop the `get_openai_config` import and the
`config = ...` line — construct the main class with its real arguments.

---

## Template 6 — `pyproject.toml` edit

Use the `Edit` tool to insert a new block under `[project.optional-dependencies]`.
Insert it alphabetically near related entries or at the end of the section —
pick whichever keeps the file readable.

New block:

```toml
# {{ComponentTitle}}
{{extra_name}} = [
    {{dep_pins}}
]
```

If the component belongs in a composite group, also add an entry to that group.
For `[all]` or `[all-cpu]`:

```toml
all = [
    # ...existing entries...
    "gaik[{{extra_name}}]",
]
```

Skip the composite-group edit for GPU-heavy / opt-in-only components.

---

## Template 7 — `implementation_layer/src/gaik/software_components/__init__.py` edit

Before:

```python
__all__ = [
    "config",
    "extractor",
    # ... other entries ...
    "agents",
]
```

After (append `{{component_name}}` to the list while preserving existing order):

```python
__all__ = [
    "config",
    "extractor",
    # ... other entries ...
    "agents",
    "{{component_name}}",
]
```

Use the `Edit` tool with a targeted `old_string` of the last two entries and the
closing `]` to insert the new line without risking duplicates.

---

## Template 8 — category `__init__.py` edit (nested components only)

Use this instead of Template 7 when the component is nested under an existing
category (e.g. `parsers/`, `RAG/`, `transcriber/`). Do NOT also edit the
top-level `software_components/__init__.py`.

Append a new try/except block at the end of the category's `__init__.py`:

```python
# {{ComponentTitle}} ({{one_line_description}})
try:
    from .{{component_name}} import {{MainClassName}}  # add more classes as needed

    __all__.extend(["{{MainClassName}}"])
except ImportError:
    pass
```

If the component exports more than one public name (e.g. main class plus a
result dataclass), include them all in the import and the `__all__.extend(...)`.

Canonical example in the repo: `implementation_layer/src/gaik/software_components/parsers/__init__.py:81-87`.

Use the `Edit` tool with an `old_string` that ends at the file's final line
(typically a `pass` in the last try/except block) to append cleanly.
