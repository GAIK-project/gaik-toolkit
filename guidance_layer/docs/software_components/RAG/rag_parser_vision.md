# RAG Vision Parser

Vision-enhanced RAG parser that combines Docling structure analysis with AI vision
models for concise image interpretation.

## Installation

```bash
pip install gaik[rag-parser-vision]
```

**Note:** Requires Docling, FFmpeg, and OpenAI/Azure OpenAI access.

---

## System Requirements

### FFmpeg (for PDF processing)

FFmpeg is required by Docling for PDF conversion workflows.

**Windows:**
```powershell
winget install ffmpeg
```

**macOS:**
```bash
brew install ffmpeg
```

**Linux:**
```bash
sudo apt-get install ffmpeg  # Ubuntu/Debian
```

**Verify:**
```bash
ffmpeg -version
```

---

### Tesseract CLI (for OCR)

If you enable OCR (`enable_ocr=True`) with `ocr_engine="tesseract_cli"`, install Tesseract:

**Windows:**
```powershell
winget install UB-Mannheim.TesseractOCR
```

**macOS:**
```bash
brew install tesseract
```

**Linux:**
```bash
sudo apt-get install tesseract-ocr  # Ubuntu/Debian
```

**Verify:**
```bash
tesseract --version
```

If needed, set:
```powershell
$env:TESSDATA_PREFIX="C:\Program Files\Tesseract-OCR\tessdata"
```

---

## Quick Start

```python
from gaik.software_components.RAG.rag_parser_vision import VisionRagParser
from gaik.software_components.config import get_openai_config

vision_config = get_openai_config(use_azure=True)
parser = VisionRagParser(vision_config=vision_config)

chunks = parser.convert_doc_to_chunks_with_vision("document.pdf")
print(chunks[0].metadata)
```

---

## Features

- **Docling + Vision** - Text extraction plus concise image interpretation
- **RAG Chunks** - Returns LangChain `Document` chunks with metadata
- **Markdown Export** - Optional markdown output with image descriptions
- **CUDA First** - Uses CUDA when available, falls back to CPU

---

## Basic API

### VisionRagParser

```python
from gaik.software_components.RAG.rag_parser_vision import VisionRagParser

parser = VisionRagParser(
    vision_config: dict,
    enable_ocr: bool = True,
    ocr_engine: str = "tesseract_cli",
    enable_table_structure: bool = True,
    enable_formula_enrichment: bool = True,
    num_threads: int = 4,
    verbose: bool = True,
    save_markdown: bool = False,
    vision_prompt: str | None = None,
)
```

### Methods

```python
chunks = parser.convert_doc_to_chunks_with_vision(
    pdf_path: str,
    output_path: str | None = None,
    return_markdown: bool = False,
)
```

---

## Configuration

This software component uses the OpenAI/Azure configuration from `gaik.software_components.config`.

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `AZURE_API_KEY` | Azure only | Azure OpenAI API key |
| `AZURE_ENDPOINT` | Azure only | Azure OpenAI endpoint URL |
| `OPENAI_API_KEY` | OpenAI only | Standard OpenAI API key |
| `AZURE_API_VERSION` | Optional | API version (default: 2025-03-01-preview) |

---

## Version Notes

- Docling version: 2.64.1
- Docling core version: >=2.50.1,<3.0.0 (with chunking extra)
- Docling IBM models: >=3.9.1,<4
- Docling parse: >=4.7.0,<5.0.0
- FFmpeg version: 8.0.1 (system dependency)

---

## Examples

See [implementation_layer/examples/software_components/RAG/](../../../../implementation_layer/examples/software_components/RAG/) for usage:
- `rag_parser_vision_example.py` - Vision-enhanced RAG chunks and markdown export

---

## Resources

- **Repository**: [github.com/GAIK-project/gaik-toolkit](https://github.com/GAIK-project/gaik-toolkit)
- **Examples**: [implementation_layer/examples/software_components/](https://github.com/GAIK-project/gaik-toolkit/tree/main/implementation_layer/examples/software_components)
- **Contributing**: [CONTRIBUTING.md](../../../../CONTRIBUTING.md)
- **Issues**: [github.com/GAIK-project/gaik-toolkit/issues](https://github.com/GAIK-project/gaik-toolkit/issues)

## License

MIT - see [LICENSE](../../../../LICENSE)
