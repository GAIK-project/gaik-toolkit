# RAG Vision Parser

Vision-enhanced RAG parser that combines Docling structure analysis with AI vision
models for concise image interpretation.

## Installation

```bash
pip install gaik[rag-parser-vision]
```

**Note:** Requires Docling, FFmpeg, and a vision-capable model (any `get_llm_config()` provider or a legacy OpenAI/Azure config).

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

If you enable OCR (`enable_ocr=True`) with `ocr_engine="tesseract_cli"` (the default), install
Tesseract with English, Spanish, French and German. These are the languages of Docling's default
Tesseract options, and Docling 2.132 and later raises `OcrLanguageNotSupportedError` on the first
conversion while one of them is missing. `ocr_engine="rapidocr"` needs no system packages.

**Windows:**
```powershell
winget install UB-Mannheim.TesseractOCR
```

The installer adds English only: pick Spanish, French and German among the additional languages
when you run it interactively, or copy `spa`, `fra` and `deu` `.traineddata` files into its
`tessdata` folder.

**macOS:**
```bash
brew install tesseract tesseract-lang
```

**Linux:**
```bash
sudo apt-get install tesseract-ocr tesseract-ocr-spa tesseract-ocr-fra tesseract-ocr-deu  # Ubuntu/Debian
```

**Verify:**
```bash
tesseract --version
tesseract --list-langs  # lists deu, eng, fra and spa
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

`vision_config` accepts a legacy `get_openai_config()` config or a shared
`get_llm_config(...)` config, as `VisionParser` does. See the
[multi-provider guide](https://gaik-project.github.io/gaik-toolkit/toolkit/multi-provider-llm/).

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

- Docling version: 2.150.1
- Docling core version: >=2.106.0,<3.0.0 (with chunking extra)
- Docling IBM models: >=4.0.2,<5
- Docling parse: >=7.22.2,<8.0.0
- FFmpeg version: 8.0.1 (system dependency)

---

## Examples

See [implementation_layer/examples/software_components/RAG/](../../../../implementation_layer/examples/software_components/RAG/) for usage:
- `rag_parser_vision_example.py` - Vision-enhanced RAG chunks and markdown export

---

## Resources

- **Repository**: [github.com/GAIK-project/gaik-toolkit](https://github.com/GAIK-project/gaik-toolkit)
- **Examples**: [implementation_layer/examples/software_components/](https://github.com/GAIK-project/gaik-toolkit/tree/main/implementation_layer/examples/software_components)
- **Contributing**: [CONTRIBUTING.md](../../../CONTRIBUTING.md)
- **Issues**: [github.com/GAIK-project/gaik-toolkit/issues](https://github.com/GAIK-project/gaik-toolkit/issues)

## License

MIT - see [LICENSE](../../../../LICENSE)
