# Parsers

Convert PDFs and Word documents to structured text using multiple parsing backends.

## Installation

```bash
pip install gaik[parser]
```

**Note:** Vision parsing requires OpenAI or Azure OpenAI API access.

---

## Available Parsers

GAIK provides six parser options, each optimized for different use cases:

| Parser | Use Case | Speed | Requirements |
|--------|----------|-------|--------------|
| `VisionParser` | High-quality PDF/image parsing with table extraction | Slow | OpenAI/Azure API |
| `PyMuPDFParser` | Fast PDF text extraction | Fast | None (local) |
| `DocxParser` | Word document parsing | Fast | None (local) |
| `DoclingParser` | Advanced OCR with multi-format support | Medium | Optional GPU |
| `VisionPlusParser` | Docling + Vision LLM for advanced parsing | Medium | OpenAI/Azure + Docling |
| `DoclingApiClientParser` | Remote Docling parsing via Haaga-Helia Docling service | Fast | API_BASE + PASSWORD |

### Quick Comparison

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

## Environment Variables

For VisionParser/VisionPlusParser only:

| Variable | Required | Description |
|----------|----------|-------------|
| `AZURE_API_KEY` | Azure only | Azure OpenAI API key |
| `AZURE_ENDPOINT` | Azure only | Azure OpenAI endpoint URL |
| `AZURE_DEPLOYMENT` | Azure only | Azure deployment name |
| `OPENAI_API_KEY` | OpenAI only | Standard OpenAI API key |
| `AZURE_API_VERSION` | Optional | API version (default: 2024-02-15-preview) |

For DoclingApiClientParser (Haaga-Helia service):

| Variable | Required | Description |
|----------|----------|-------------|
| `API_BASE` | Yes | Service base URL provided by Haaga-Helia |
| `PASSWORD` | Yes | Service password provided by Haaga-Helia |

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

