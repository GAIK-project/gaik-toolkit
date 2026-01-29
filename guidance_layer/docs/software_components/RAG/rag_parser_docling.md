# RAG Docling Parser

Docling-based PDF parser for RAG pipelines. Converts PDFs to markdown or
LangChain `Document` chunks with metadata.

## Installation

```bash
pip install gaik[rag-parser-docling]
```

**Note:** Requires Docling and FFmpeg for PDF processing.

---

## Breaking Changes

### Version 0.2.0

**Removed unused parameters**: `chunk_size` and `chunk_overlap` have been removed from
`convert_pdf_to_chunks_with_metadata()` because they were never used. The implementation
uses HierarchicalChunker, which chunks by document structure.

**Migration**: Simply remove these parameters from your calls. The chunking behavior is unchanged.

**Before:**
```python
chunks = parser.convert_pdf_to_chunks_with_metadata("doc.pdf", chunk_size=3000, chunk_overlap=200)
```

**After:**
```python
chunks = parser.convert_pdf_to_chunks_with_metadata("doc.pdf")
```

---

## System Requirements

### FFmpeg (for PDF processing)

FFmpeg is required by Docling for PDF conversion workflows.

**Installation:**

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
from gaik.software_components.RAG.rag_parser_docling import DoclingRagParser

parser = DoclingRagParser()

chunks = parser.convert_pdf_to_chunks_with_metadata("document.pdf")

print(chunks[0].metadata)
```

---

## Features

- **Docling Parsing** - High-quality PDF conversion with OCR and table extraction
- **RAG Chunks** - Returns LangChain `Document` chunks with metadata
- **Markdown Export** - Save full documents as markdown
- **CUDA First** - Uses CUDA when available, falls back to CPU

---

## Basic API

### DoclingRagParser

```python
from gaik.software_components.RAG.rag_parser_docling import DoclingRagParser

parser = DoclingRagParser(
    enable_ocr: bool = True,
    ocr_engine: str = "tesseract_cli",
    enable_table_structure: bool = True,
    enable_formula_enrichment: bool = True,
    num_threads: int = 4,
    verbose: bool = True,
)
```

### Methods

```python
markdown = parser.convert_pdf_to_markdown(
    pdf_path: str,
    output_path: str | None = None
)

chunks = parser.convert_pdf_to_chunks_with_metadata(
    pdf_path: str,
)  # -> list[Document]
```

### Chunking Behavior

The `convert_pdf_to_chunks_with_metadata` method uses Docling's `HierarchicalChunker`,
which chunks documents by **document structure** rather than by fixed size:

- Chunks follow semantic boundaries (headings, sections, paragraphs)
- Chunk sizes vary based on document structure
- Preserves document hierarchy in metadata (heading field)

This approach ensures chunks maintain semantic coherence and context.

---

## Configuration

This software component is self-contained and does not require OpenAI/Azure configuration.

OCR engines:
- `tesseract_cli` (default) uses the Tesseract CLI binary
- `tesseract` uses the tesserocr Python bindings
- `easyocr` uses EasyOCR
- `rapidocr` uses RapidOCR

---

## Environment Variables

No required environment variables.

---

## Version Notes

- Docling version: 2.64.1
- Docling core version: >=2.50.1,<3.0.0 (with chunking extra)
- Docling IBM models: >=3.9.1,<4
- Docling parse: >=4.7.0,<5.0.0
- FFmpeg version: 8.0.1 (system dependency)

---

## Examples

See [implementation_layer/examples/software_components/](../../../../implementation_layer/examples/software_components/RAG) for more.

---

## Resources

- **Repository**: [github.com/GAIK-project/gaik-toolkit](https://github.com/GAIK-project/gaik-toolkit)
- **Examples**: [implementation_layer/examples/software_components/](https://github.com/GAIK-project/gaik-toolkit/tree/main/implementation_layer/examples/software_components)
- **Contributing**: [CONTRIBUTING.md](../../../../CONTRIBUTING.md)
- **Issues**: [github.com/GAIK-project/gaik-toolkit/issues](https://github.com/GAIK-project/gaik-toolkit/issues)

## License

MIT - see [LICENSE](../../../../LICENSE)
