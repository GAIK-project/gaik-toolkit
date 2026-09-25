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
| `gaik[multimodal-parser]` | PyMuPDF, Anthropic, Google auth, markdown-it | `MultimodalParser` |
| `gaik[llm-google]` | Google Gen AI SDK and auth | Shared `google` and `vertex` clients |
| `gaik[llm-anthropic]` | Anthropic SDK | Shared `anthropic` and `anthropic_foundry` clients |
| `gaik[llm-litellm]` | LiteLLM | Optional `litellm` client; use a provider-prefixed model |

`DoclingParser` needs `parser`, not `parser-cpu`. Components swallow a missing optional
dependency in `__init__.py` (`try: from .x import Y / except ImportError: pass`), so a
class installed under the wrong extra is not an error — it is simply **absent** from the
namespace, and the import fails with `ImportError: cannot import name`. If a documented
class will not import, suspect the extra before suspecting the code.

## Credentials per parser

Local parsers (`PyMuPDFParser`, `DocxParser`, `DoclingParser`) need nothing.

**Shared provider configuration** — prefer `get_llm_config(provider, **overrides)`
from `gaik.software_components.llm`. Supply it through `VisionParser(openai_config=...)`,
`VisionPlusParser(vision_config=...)`, or `MultimodalParser(api_config=...)`.
`VisionRagParser(vision_config=...)` accepts the same dictionary.

| Provider | Settings |
|---|---|
| `openai` | `OPENAI_API_KEY`, optional `OPENAI_MODEL` |
| `azure` | `AZURE_API_KEY`, `AZURE_ENDPOINT`, `AZURE_DEPLOYMENT`; optional `AZURE_API_VERSION` |
| `google` | `GOOGLE_API_KEY` (or `GEMINI_API_KEY`), optional `GOOGLE_MODEL` |
| `vertex` | `GOOGLE_PROJECT_ID` (or `GOOGLE_CLOUD_PROJECT`), optional `GOOGLE_CLOUD_LOCATION` (default `global`); Google application-default credentials or `GOOGLE_SERVICE_ACCOUNT_JSON` / `GOOGLE_APPLICATION_CREDENTIALS` |
| `anthropic` | `ANTHROPIC_API_KEY`, optional `ANTHROPIC_MODEL` |
| `anthropic_foundry` | `ANTHROPIC_FOUNDRY_API_KEY` (or `AZURE_API_KEY`), `ANTHROPIC_FOUNDRY_RESOURCE`, optional `ANTHROPIC_MODEL` |
| `aitta` | `AITTA_API_KEY` (aliases `AITTA_API_TOKEN`, `AITTA_TOKEN`), optional `AITTA_MODEL` |
| `openai_compatible` | `OPENAI_API_KEY`, explicit `OPENAI_BASE_URL` and `OPENAI_MODEL` |
| `litellm` | `LITELLM_MODEL` with a provider prefix (`azure/<deployment>`); optional `LITELLM_API_KEY`, `LITELLM_BASE_URL`, `LITELLM_API_VERSION`, sent with each request — when unset, LiteLLM reads that backend's own variables; `LITELLM_EMBEDDING_MODEL` for embeddings |

Explicit `api_key`, `base_url`, `model`, and other overrides are applied before
validation. Do not copy one provider's credentials into another provider's config.
For shared Vertex, the service-account value can be a JSON object, JSON text or a
file path; standard application-default credentials work when it is omitted.
Aitta defaults to `https://aitta-api.csc.fi/openai/v1` and a 600-second timeout for
cold starts. All vision routes require an image-capable model. Aitta
`google/gemma-4-31b-it` passed the integration vision checks; confirm current
availability in its catalogue. Native Google/Vertex and Anthropic translate inline
image messages.

**`MultimodalParser`** — use `api_config=get_llm_config(...)` for the shared provider
interface. With the legacy `model_provider` interface, each combination of provider
and hosting flag reads a different variable:

| `model_provider` | flag | Variables |
|---|---|---|
| `openai` | `use_azure=True` (default) | `AZURE_API_KEY`, `AZURE_ENDPOINT` |
| `openai` | `use_azure=False` | `OPENAI_API_KEY` |
| `claude` | `use_azure=True` (default) | `AZURE_API_KEY`, `ANTHROPIC_FOUNDRY_RESOURCE` |
| `claude` | `use_azure=False` | `ANTHROPIC_API_KEY` |
| `google` | `vertex_ai=True` (default) | `GOOGLE_PROJECT_ID`, `GOOGLE_SERVICE_ACCOUNT_JSON`, `GOOGLE_SCOPES`, `GOOGLE_GENERATE_CONTENT_URL` |
| `google` | `vertex_ai=False` | `GOOGLE_API_KEY` |

These legacy defaults are `use_azure=True` and `vertex_ai=True`, so a plain
`MultimodalParser(model_provider="claude")` looks for Azure/Foundry credentials, not
`ANTHROPIC_API_KEY`. Passing a direct API key without also passing the flag is the usual
cause of an auth error that looks like a wrong key.
An explicit shared `api_config` supersedes these routing flags.

**`DoclingApiClientParser`** — the remote Docling service's address and password, passed as
the required keyword arguments `api_base=` and `password=`. It reads no environment
variables itself, so load them in your own code.

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
