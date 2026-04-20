# GAIK Software Component Conventions

This reference captures the conventions every new GAIK software component must
follow. These patterns are extracted from existing components like `doc_classifier`,
`enhance_transcript`, `extractor`, `transcriber`, and `parsers`.

## Directory layout

A software component lives at
`implementation_layer/src/gaik/software_components/<component_name>/` and always
contains:

```
<component_name>/
├── __init__.py          # Module docstring, re-exports, __all__, __version__
├── <component_name>.py  # Main class implementation
└── README.md            # User-facing docs: install + quick start
```

Components may add sub-modules (helpers, sub-parsers, prompts) as additional `.py`
files in the same directory. Keep the public surface minimal — only the main
class(es) and factory helpers are re-exported from `__init__.py`.

## `__init__.py` pattern

```python
"""<Component Title>

<One-paragraph description of what the component does.>

Main Classes:
    - MainClass: <one-line purpose>

Configuration:
    - get_openai_config: Get OpenAI/Azure configuration
    - create_openai_client: Create OpenAI client from config

Example:
    >>> from gaik.software_components.<component_name> import MainClass, get_openai_config
    >>> config = get_openai_config(use_azure=True)
    >>> instance = MainClass(config=config)
    >>> result = instance.<method>(...)
"""

from gaik.software_components.config import create_openai_client, get_openai_config

from .<component_name> import MainClass

__all__ = [
    "MainClass",
    "get_openai_config",
    "create_openai_client",
]

__version__ = "0.1.0"
```

Notes:
- Re-export `get_openai_config` and `create_openai_client` only if the component
  is LLM-based. Drop them for pure-Python components.
- `__version__ = "0.1.0"` for a new component.
- The `F401` rule is already ignored for `**/__init__.py` in `pyproject.toml`, so
  unused-import warnings are not an issue.

## Main class constructor pattern

For LLM-based components, the constructor takes a `config` dict from
`get_openai_config()` and creates the client via `create_openai_client()`:

```python
from gaik.software_components.config import create_openai_client


class MainClass:
    """<docstring>"""

    def __init__(self, config: dict, model: str | None = None):
        self.config = config
        self.model = model or config["model"]
        self.client = create_openai_client(config)
```

For provider-agnostic components, drop the `config` / `client` and accept only
the arguments the component actually needs.

Never do these inside a component file:
- `load_dotenv()` — only examples call this.
- `os.getenv("OPENAI_API_KEY")` or other env var reads — config handles this.
- Instantiate `OpenAI(...)` or `AzureOpenAI(...)` directly — use
  `create_openai_client(config)`.

## Result dataclass pattern (optional)

If the component produces a structured result with multiple fields (not a plain
dict), define a `@dataclass` next to the main class. If the result can be
persisted to disk, expose a `save(self, directory: str | Path) -> dict[str, Path]`
method that returns a mapping of logical name → written path.

Not every component needs this. A `dict`, `list`, or primitive return value is
fine if the output is simple.

## Shared config rule

Always import `get_openai_config` and `create_openai_client` from
`gaik.software_components.config`. Do not re-implement them. Do not duplicate
the env-var reading logic inside your component.

Source: `implementation_layer/src/gaik/software_components/config.py`.

## `pyproject.toml` extras

Every component gets its own entry under `[project.optional-dependencies]`:

```toml
[project.optional-dependencies]
# ...existing entries...
<extra-name> = [
    "external-pkg>=x.y",
]
```

Rules:
- **Extra name** is hyphenated, lowercase, descriptive
  (`doc-classifier`, `enhance-transcript`, `parallel-transcriber`).
- **Import name** (used in `software_components/__init__.py` `__all__`) is
  snake_case and matches the directory (`doc_classifier`, `enhance_transcript`).
- **Empty list (`[]`) is valid** for components that only need the core
  dependencies (pydantic, python-dotenv, openai). See `extract`, `enhance-transcript`,
  `text-to-speech`, `parallel-transcriber` for examples.
- **Version pins** — use `>=` for libraries with stable APIs; pin to exact
  versions (`==`) for libraries like `docling` where minor version changes
  have broken APIs historically.

If the component belongs in a composite group like `all` or `all-cpu`, append a
`"gaik[<extra-name>]"` entry to that group too. Skip this for heavy/GPU-only
components — they should stay opt-in.

## Parent namespace `__init__.py`

### Top-level components

Append the new component's snake_case name to the `__all__` list in
`implementation_layer/src/gaik/software_components/__init__.py`. Preserve the
existing ordering; add the new entry at the end.

### Nested sub-components (e.g. a new parser under `parsers/`)

When the component is a variant of an existing category, it lives at
`software_components/<category>/<component_name>/` and is registered in
`<category>/__init__.py` — **not** the top-level `software_components/__init__.py`.

Use the existing `try/except ImportError: pass` guard pattern in that category's
`__init__.py` to keep heavy optional deps opt-in. Canonical example:
`parsers/__init__.py:81-87`:

```python
# Multi-provider PDF parsing (requires anthropic, google-auth, markdown-it-py)
try:
    from .multimodal_parser import MultimodalParser, ParseResult

    __all__.extend(["MultimodalParser", "ParseResult"])
except ImportError:
    pass
```

Append a similar block to the category's `__init__.py`. Do not touch
`software_components/__init__.py`.

## When to pick nested vs top-level

| Component kind | Layout |
|---|---|
| Another PDF/DOCX/document parser | nested under `parsers/` |
| Another vector store, retriever, embedder, or RAG parser | nested under `RAG/` |
| Another transcriber variant | nested under `transcriber/` |
| A new independent capability (e.g. text-to-speech, classifier, extractor) | top-level |

If unsure, prefer top-level. Only nest when there is a clear sibling in an
existing category directory.

## Examples directory

Every component ships with one example at
`implementation_layer/examples/software_components/<component_name>/<component_name>_example.py`.

Conventions for examples (not for the component itself):
- They **do** call `load_dotenv(Path(__file__).parent.parent.parent / ".env")`.
- They **do** insert `src/` into `sys.path` so they work without `pip install`.
- They import from the public package path: `from gaik.software_components.<component_name> import MainClass`.
- They wrap demos in named functions and call them from `if __name__ == "__main__":`.

See `references/file-templates.md` for the exact example template.
