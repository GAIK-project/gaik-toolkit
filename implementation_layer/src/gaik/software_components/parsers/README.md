# Parsers

Convert PDFs and Word documents to structured text using multiple parsing backends.

## Installation

```bash
pip install gaik[parser]
```

**Note:** Vision parsing requires a provider and model that support image input. Shared configs support OpenAI, Azure, Google, Anthropic, Aitta-compatible models, and optional LiteLLM routes.

---

## Available Parsers

GAIK provides eight parser options, each optimized for different use cases:

| Parser | Use Case | Speed | Requirements |
|--------|----------|-------|--------------|
| `MultimodalParser` | PDF parsing with layout-aware table extraction across multiple LLM providers | Slow | Image-capable model through shared or legacy provider config |
| `VisionParser` | High-quality PDF/image parsing with table extraction | Medium | Image-capable model through a shared provider config |
| `PyMuPDFParser` | Fast PDF text extraction | Fast | None (local) |
| `DocxParser` | Word document parsing | Fast | None (local) |
| `DoclingParser` | Advanced OCR with multi-format support | Medium | Optional GPU |
| `VisionPlusParser` | Docling + Vision LLM for advanced parsing | Medium | Image-capable model + Docling |
| `DoclingApiClientParser` | Remote Docling parsing via Haaga-Helia Docling service | Fast | API_BASE + PASSWORD |
| `SpreadsheetParser` | Excel (`.xlsx`) and CSV to Markdown tables with row numbers | Fast | None (local) |

`PyMuPDFParser.parse_pdf(path, page_markers=True)` writes a `[Page N]` line before each page, and `DocxParser.parse_docx(path, keep_structure=True)` keeps headings and tables in document order, so a quote can be traced to its place.

### Quick Comparison

```python
from gaik.software_components.llm import get_llm_config
from gaik.software_components.parsers import VisionParser

parser = VisionParser(get_llm_config("openai", model="gpt-6-luna"))
markdown = parser.convert_image("invoice.jpg")
```

The same configuration shape works with `VisionPlusParser(vision_config=...)` and `VisionRagParser(vision_config=...)`. Native Google and Anthropic adapters translate the image messages. For Aitta or another compatible server, select a model whose catalog entry supports image input.

**Use MultimodalParser when:**
- Documents contain messy, irregular, or complex tables that span multiple pages
- You need the highest accuracy for layout preservation and table extraction
- Quality matters more than speed or cost
- Allows you to choose between providers (OpenAI, Claude, Google Gemini)
- Install separately: `pip install "gaik[multimodal-parser]"`

**Use VisionParser when:**
- You need accurate table extraction
- Documents have complex layouts
- Visual elements are important
- Quality > Speed

**Use PyMuPDFParser when:**
- You need fast text-only extraction
- No API calls/costs desired
- Simple PDF layouts
- Speed > Quality

**Use DocxParser when:**
- Processing Word documents (.docx, .doc)
- Fast local processing needed
- Simple or structured text extraction

**Use DoclingParser when:**
- OCR is required for scanned documents
- Multi-format support needed (PDF, images, etc.)
- You need advanced table extraction 
- You have CUDA-enabled GPU available for fast processing (otherwise slow)


**Use VisionPlusParser when:**
- You need advanced Docling parsing with image interpretation
- You need image interpretation at correct places in the parsed output
- You need advanced table extraction

**Use DoclingApiClientParser when:**
- You need fast Docling parsing with GPU acceleration through the Haaga-Helia hosted service
- You have API access credentials from Haaga-Helia
- You want parsed markdown + metadata 

---

## Input limits

A file over a limit is refused with `InputLimitError` (a `ValueError`) before it is
parsed or sent to a model. Every parser takes `limits=InputLimits(...)`; a field set to
`None` switches that limit off. Defaults: 100 MiB per file (a DOCX or XLSX may unpack to
10 × that), 1,000,000 data rows per sheet or CSV, 89,478,485 pixels per image or rendered
page, and 500 embedded images described per document (`VisionPlusParser`). The 500-page
limit applies where every page becomes a model call (`VisionParser`, `MultimodalParser`);
the parsers that read pages locally (`PyMuPDFParser`, `DoclingParser`,
`DoclingApiClientParser`, `VisionPlusParser`) default to `InputLimits.local_parsing()`,
which has no page limit.

```python
from gaik.software_components.input_limits import InputLimits
from gaik.software_components.parsers import VisionParser

parser = VisionParser(config, limits=InputLimits(max_pages=30))
first_page = parser.convert_pdf("scan.pdf", clean_output=False, first_pages=1)
```

`convert_pdf(..., first_pages=N)` renders and sends only the first `N` pages; the page
limit then applies to those pages.

## Source material as data

The parsers that send a document to a model (`VisionParser`, `VisionPlusParser`
through it, and `MultimodalParser`) treat the document as material, never as
instructions ([`gaik.software_components.source_material`](../source_material.py)).
Each call states the rule in `SOURCE_MATERIAL_INSTRUCTION`: in the system message
of `MultimodalParser` and of the `VisionParser` clean-up call, and at the start of
the user message of a `VisionParser` page call, since some served vision models
refuse a system message next to an image. The end of the previous page
(`VisionParser` with `use_context=True`), the pages given to the clean-up call
and a PDF's text layer travel in the user message, each inside a
`<source_material>` block with a random id for each call; the clean-up answer
loses those tags if the model repeats them. The local parsers (`PyMuPDFParser`,
`DocxParser`, `DoclingParser`, `SpreadsheetParser`) call no model.

## Environment Variables

For MultimodalParser (see [multimodal_parser/README.md](multimodal_parser/README.md) for full details):

| Variable | When | Description |
|----------|------|-------------|
| `AZURE_API_KEY` | OpenAI or Claude with `use_azure=True` | Azure / Foundry API key |
| `AZURE_ENDPOINT` | OpenAI with `use_azure=True` | Azure OpenAI endpoint URL |
| `ANTHROPIC_FOUNDRY_API_KEY` | Claude with `use_azure=True` | Foundry API key; `AZURE_API_KEY` is the fallback |
| `ANTHROPIC_FOUNDRY_RESOURCE` | Claude with `use_azure=True` | Foundry resource name |
| `ANTHROPIC_API_KEY` | Claude with `use_azure=False` | Direct Anthropic API key |
| `GOOGLE_PROJECT_ID` | Google with `vertex_ai=True` | GCP project ID |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | Google with `vertex_ai=True` | Service account JSON (inline) |
| `GOOGLE_API_KEY` | Google with `vertex_ai=False` | Direct Gemini API key |

For VisionParser/VisionPlusParser only:

| Variable | Required | Description |
|----------|----------|-------------|
| `AZURE_API_KEY` | Azure only | Azure OpenAI API key |
| `AZURE_ENDPOINT` | Azure only | Azure OpenAI endpoint URL |
| `AZURE_DEPLOYMENT` | Azure only | Azure deployment name |
| `OPENAI_API_KEY` | OpenAI only | Standard OpenAI API key |
| `AZURE_API_VERSION` | Optional | API version (default: 2024-12-01-preview with `parsers.get_openai_config()`, 2025-03-01-preview with `get_llm_config("azure")`) |

For DoclingApiClientParser (Haaga-Helia service):

| Variable | Required | Description |
|----------|----------|-------------|
| `API_BASE` | Yes | Service base URL provided by Haaga-Helia (the demo app and generated PoCs read `DOCLING_API_BASE`) |
| `PASSWORD` | Yes | Service password provided by Haaga-Helia |

The client sends the document and the password only to the address set in `DOCLING_API_BASE`
or `API_BASE` (plain http works for that address), to this machine, or to a host in
`GAIK_ALLOWED_ENDPOINT_HOSTS` or `allowed_endpoint_hosts`. Any other `api_base` raises
`EndpointNotAllowedError` when the client is built.

---

## Examples

See [implementation_layer/examples/software_components/parsers/](../../../../examples/software_components/parsers/) for complete examples.

---

## Resources

- **Repository**: [github.com/GAIK-project/gaik-toolkit](https://github.com/GAIK-project/gaik-toolkit)
- **Examples**: [implementation_layer/examples/software_components/parsers/](https://github.com/GAIK-project/gaik-toolkit/tree/main/implementation_layer/examples/software_components/parsers)
- **Contributing**: [CONTRIBUTING.md](../../../../../guidance_layer/CONTRIBUTING.md)
- **Issues**: [github.com/GAIK-project/gaik-toolkit/issues](https://github.com/GAIK-project/gaik-toolkit/issues)

## License

MIT - see [LICENSE](../../../../../LICENSE)

