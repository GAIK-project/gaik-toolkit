# Parsers

Convert PDFs and Word documents to structured text using multiple parsing backends.

## Installation

```bash
pip install gaik[parser]
```

**Note:** Requires OpenAI or Azure OpenAI API access for vision-based parsing

---

## Available Parsers

GAIK provides seven parsers, each optimized for different use cases:

| Parser | Use Case | Speed | Requirements |
|--------|----------|-------|--------------|
| `MultimodalParser` | Premium PDF parsing with layout-aware table extraction across multiple LLM providers | Slow | OpenAI/Azure, Anthropic, or Google API |
| `VisionParser` | High-quality PDF/image parsing with table extraction | Medium | OpenAI/Azure API |
| `PyMuPDFParser` | Fast PDF text extraction | Fast | None (local) |
| `DocxParser` | Word document parsing | Fast | None (local) |
| `DoclingParser` | Advanced OCR with multi-format support | Medium | Optional GPU |
| `VisionPlusParser` | Docling + vision parsing returning markdown plus metadata | Medium | OpenAI/Azure + Docling |
| `DoclingApiClientParser` | Remote client for a hosted Docling parsing service | Fast | `API_BASE` + `PASSWORD` |

### Quick Comparison

**Use MultimodalParser when:**
- Documents contain messy, irregular, or complex tables that span multiple pages
- You need the highest accuracy for layout preservation and table extraction
- You want to choose between providers (OpenAI, Claude, Google Gemini)
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
- Advanced table extraction with OCR
- GPU acceleration available (otherwise slow -- roughly 20-30 s/page on CPU)

**Use VisionPlusParser when:**
- You need Docling parsing plus interpretation of images at their correct position
- Downstream RAG chunks need per-element metadata

**Use DoclingApiClientParser when:**
- You want Docling-quality parsing without the local install overhead
- You have credentials for a hosted Docling service

---

## Environment Variables

For MultimodalParser (the variable depends on provider and hosting flag):

| Variable | When |
|----------|------|
| `AZURE_API_KEY` | `openai` or `claude` with `use_azure=True` (the default) |
| `AZURE_ENDPOINT` | `openai` with `use_azure=True` |
| `ANTHROPIC_FOUNDRY_RESOURCE` | `claude` with `use_azure=True` |
| `ANTHROPIC_API_KEY` | `claude` with `use_azure=False` |
| `GOOGLE_PROJECT_ID`, `GOOGLE_SERVICE_ACCOUNT_JSON` | `google` with `vertex_ai=True` (the default) |
| `GOOGLE_API_KEY` | `google` with `vertex_ai=False` |

For VisionParser and VisionPlusParser:

| Variable | Required | Description |
|----------|----------|-------------|
| `AZURE_API_KEY` | Azure only | Azure OpenAI API key |
| `AZURE_ENDPOINT` | Azure only | Azure OpenAI endpoint URL |
| `AZURE_DEPLOYMENT` | Azure only | Azure deployment name |
| `OPENAI_API_KEY` | OpenAI only | Standard OpenAI API key |
| `AZURE_API_VERSION` | Optional | API version (default: 2024-02-15-preview) |

For DoclingApiClientParser: `API_BASE` and `PASSWORD` for the hosted service.

**Note:** PyMuPDFParser, DocxParser, and DoclingParser do not require API keys.

---

## Examples

See [implementation_layer/examples/software_components/parsers/](../../implementation_layer/examples/software_components/parsers/) for complete examples.

---

## Resources

- **Repository**: [github.com/GAIK-project/gaik-toolkit](https://github.com/GAIK-project/gaik-toolkit)
- **Examples**: [implementation_layer/examples/software_components/](https://github.com/GAIK-project/gaik-toolkit/tree/main/implementation_layer/examples/software_components)
- **Contributing**: [CONTRIBUTING.md](../../CONTRIBUTING.md)
- **Issues**: [github.com/GAIK-project/gaik-toolkit/issues](https://github.com/GAIK-project/gaik-toolkit/issues)

## License

MIT - see [LICENSE](../../LICENSE)






