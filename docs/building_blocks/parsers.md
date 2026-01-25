# Parsers

Convert PDFs and Word documents to structured text using multiple parsing backends.

## Installation

```bash
pip install gaik[parser]
```

**Note:** Requires OpenAI or Azure OpenAI API access for vision-based parsing

---

## Available Parsers

GAIK provides four different parsers, each optimized for different use cases:

| Parser | Use Case | Speed | Requirements |
|--------|----------|-------|--------------|
| [VisionParser](vision.md) | High-quality PDF/image parsing with table extraction | Slow | OpenAI/Azure API |
| [PyMuPDFParser](pymupdf.md) | Fast PDF text extraction | Fast | None (local) |
| [DocxParser](docx.md) | Word document parsing | Fast | None (local) |
| [DoclingParser](docling.md) | Advanced OCR with multi-format support | Medium | Optional GPU |

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
- Advanced table extraction with OCR
- GPU acceleration available

---

## Environment Variables

For VisionParser only:

| Variable | Required | Description |
|----------|----------|-------------|
| `AZURE_API_KEY` | Azure only | Azure OpenAI API key |
| `AZURE_ENDPOINT` | Azure only | Azure OpenAI endpoint URL |
| `AZURE_DEPLOYMENT` | Azure only | Azure deployment name |
| `OPENAI_API_KEY` | OpenAI only | Standard OpenAI API key |
| `AZURE_API_VERSION` | Optional | API version (default: 2024-02-15-preview) |

**Note:** PyMuPDFParser, DocxParser, and DoclingParser do not require API keys.

---

## Examples

See [examples/building_blocks/parsers/](../../examples/building_blocks/parsers/) for complete examples.

---

## Resources

- **Repository**: [github.com/GAIK-project/gaik-toolkit](https://github.com/GAIK-project/gaik-toolkit)
- **Examples**: [examples/building_blocks/](https://github.com/GAIK-project/gaik-toolkit/tree/main/examples/building_blocks)
- **Contributing**: [CONTRIBUTING.md](../../CONTRIBUTING.md)
- **Issues**: [github.com/GAIK-project/gaik-toolkit/issues](https://github.com/GAIK-project/gaik-toolkit/issues)

## License

MIT - see [LICENSE](../../LICENSE)






