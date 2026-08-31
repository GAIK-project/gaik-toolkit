# Parser configuration and credentials

Read this when a parser needs credentials, when a provider raises an auth error, or when
deciding which extra to install.

## Contents
- Install extras
- Credentials per parser
- Choosing a provider for vision parsing
- Escalation ladder

## Install extras

| Extra | Brings | Needed by |
|---|---|---|
| `gaik[parser]` | PyMuPDF, python-docx, Docling | `PyMuPDFParser`, `DocxParser`, `DoclingParser`, `VisionPlusParser` |
| `gaik[parser-cpu]` | same, CPU-only wheels | everything except `DoclingParser` |
| `gaik[multimodal-parser]` | Anthropic + Google SDKs, markdown-it | `MultimodalParser` |

`DoclingParser` needs `parser`, not `parser-cpu`. Components swallow a missing optional
dependency in `__init__.py` (`try: from .x import Y / except ImportError: pass`), so a
class installed under the wrong extra is not an error — it is simply **absent** from the
namespace, and the import fails with `ImportError: cannot import name`. If a documented
class will not import, suspect the extra before suspecting the code.

## Credentials per parser

Local parsers (`PyMuPDFParser`, `DocxParser`, `DoclingParser`) need nothing.

**`VisionParser` and `VisionPlusParser`** — OpenAI or Azure only:

| Variable | When |
|---|---|
| `OPENAI_API_KEY` | standard OpenAI |
| `AZURE_API_KEY`, `AZURE_ENDPOINT`, `AZURE_DEPLOYMENT` | Azure |
| `AZURE_API_VERSION` | optional, has a default |

**`MultimodalParser`** — the provider is chosen by `model_provider`, and each combination
of provider and hosting flag reads a different variable:

| `model_provider` | flag | Variables |
|---|---|---|
| `openai` | `use_azure=True` (default) | `AZURE_API_KEY`, `AZURE_ENDPOINT` |
| `openai` | `use_azure=False` | `OPENAI_API_KEY` |
| `claude` | `use_azure=True` (default) | `AZURE_API_KEY`, `ANTHROPIC_FOUNDRY_RESOURCE` |
| `claude` | `use_azure=False` | `ANTHROPIC_API_KEY` |
| `google` | `vertex_ai=True` (default) | `GOOGLE_PROJECT_ID`, `GOOGLE_SERVICE_ACCOUNT_JSON` |
| `google` | `vertex_ai=False` | `GOOGLE_API_KEY` |

The defaults are `use_azure=True` and `vertex_ai=True`, so a plain
`MultimodalParser(model_provider="claude")` looks for Azure/Foundry credentials, not
`ANTHROPIC_API_KEY`. Passing a direct API key without also passing the flag is the usual
cause of an auth error that looks like a wrong key.

**`DoclingApiClientParser`** — `API_BASE` and `PASSWORD` for the remote service.

## Choosing a provider for vision parsing

Across measured runs the provider mattered less than the format: three vision models from
two providers all cleared the specialized parsers on table structure, and the cheapest of
them already won. Start with the cheap model and only move up if a verification check
fails — the larger models bought a few points, not a category change.

Cross-region note when using Vertex: multi-region endpoints live on the *unprefixed* host,
so setting a location like `eu` with a default client template can produce an invalid
hostname such as `eu-aiplatform.googleapis.com`. Single regions use the default template.
Some regions do not serve these models at all.

## Escalation ladder

Each rung costs more and fixes a specific failure. Do not skip ahead — the check tells you
which rung you need.

1. **`PyMuPDFParser`** — free. Fails when pages have no text layer, or tables matter.
2. **`DoclingParser`** — OCR fixes missing text layers. Its shipped markdown still cannot
   express merged cells, so tables may remain wrong even when text appears.
3. **`VisionPlusParser`** — Docling plus vision descriptions of images placed inline. Use
   when figures carry meaning that must sit in the right position for RAG chunks.
4. **`MultimodalParser` / `VisionParser`** — the model reads the rendered page. This is the
   rung that recovers merged cells and stacked headers, because it can emit HTML.
5. **`merge_table=True`** — for tables broken across a page boundary, which no
   page-at-a-time parser can reassemble.
