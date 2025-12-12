# DoclingParser

Advanced OCR-capable parser with support for PDFs, images, and multiple formats using the Docling library.

## Installation

```bash
pip install gaik[parser]
```

**Note:** No API keys required - runs locally with optional GPU acceleration

---

## Quick Start

```python
from gaik.building_blocks.parsers import DoclingParser

parser = DoclingParser(
    ocr_engine="easyocr",  # or "tesseract", "rapid"
    use_gpu=False
)

# Parse with OCR
result = parser.parse_document("scanned_document.pdf")

# Convert to markdown
markdown = parser.convert_to_markdown("document.pdf")
```

---

## Features

- **OCR Support** - Extract text from scanned documents and images
- **Multiple OCR Engines** - Choose from EasyOCR, Tesseract, or RapidOCR
- **GPU Acceleration** - Optional GPU support for faster processing
- **Table Extraction** - Advanced table detection and extraction
- **Multi-Format** - Supports PDFs, images, and various document formats
- **Markdown Output** - Convert documents to well-formatted markdown
- **No API Calls** - Runs completely locally

---

## API Reference

### DoclingParser

```python
from gaik.building_blocks.parsers import DoclingParser

parser = DoclingParser(
    ocr_engine: str = "easyocr",  # or "tesseract", "rapid"
    use_gpu: bool = False
)

# Parse with OCR
result = parser.parse_document(file_path: str)

# Convert to markdown
markdown = parser.convert_to_markdown(file_path: str)
```

### OCR Engines

| Engine | Speed | Quality | GPU Support | Notes |
|--------|-------|---------|-------------|-------|
| `easyocr` | Medium | High | Yes | Recommended for general use |
| `tesseract` | Fast | Medium | No | Fast, widely compatible |
| `rapid` | Fast | Medium | No | Lightweight, fast |

---

## When to Use

**Best for:**
- Scanned PDFs requiring OCR
- Documents with complex tables
- Image-based documents
- Multi-format document processing
- GPU-accelerated processing

**Not ideal for:**
- Simple text-based PDFs (use PyMuPDFParser for speed)
- Documents requiring AI understanding (use VisionParser)
- Real-time processing (slower due to OCR)

---

## System Requirements

### Optional: Tesseract (for tesseract OCR engine)

**Windows:**
```powershell
# Download from: https://github.com/UB-Mannheim/tesseract/wiki
# Or use chocolatey:
choco install tesseract
```

**macOS:**
```bash
brew install tesseract
```

**Linux:**
```bash
sudo apt-get install tesseract-ocr  # Ubuntu/Debian
```

### GPU Acceleration

For GPU support with EasyOCR:
```bash
# Install CUDA-enabled PyTorch (if not already installed)
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu118
```

---

## Examples

```python
from gaik.building_blocks.parsers import DoclingParser

# Basic OCR parsing
parser = DoclingParser(ocr_engine="easyocr")
result = parser.parse_document("scanned_invoice.pdf")
print(result)

# With GPU acceleration
parser_gpu = DoclingParser(ocr_engine="easyocr", use_gpu=True)
result = parser_gpu.parse_document("large_document.pdf")

# Convert to markdown
markdown = parser.convert_to_markdown("report.pdf")
with open("output.md", "w") as f:
    f.write(markdown)
```

---

## Resources

- **Back to Parsers**: [docs/parsers/](README.md)
- **Repository**: [github.com/GAIK-project/gaik-toolkit](https://github.com/GAIK-project/gaik-toolkit)
- **Contributing**: [CONTRIBUTING.md](../../CONTRIBUTING.md)
- **Docling Library**: [github.com/DS4SD/docling](https://github.com/DS4SD/docling)

## License

MIT - see [LICENSE](../../LICENSE)


