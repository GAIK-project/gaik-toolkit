---
name: parsing-documents
description: >-
  Converts PDFs, scans, and Word documents into text or markdown with the gaik
  toolkit's parsers, choosing the parser that will not silently destroy the
  structure the downstream task depends on. Use when reading a PDF or DOCX into
  text, pulling tables out of a document, running OCR on scans, feeding
  documents into a RAG pipeline or an LLM, deciding between PyMuPDF, Docling,
  and vision-LLM parsing, or when a parse appeared to succeed but the tables,
  columns, or whole pages came out wrong or empty. Also use when document
  parsing is costing more time or money than expected. Covers parser selection,
  per-page verification, and escalation from cheap local parsing to vision
  models.
---

# Parsing documents with gaik

```bash
pip install "gaik[parser]"              # PyMuPDF, python-docx, Docling
pip install "gaik[multimodal-parser]"   # multi-provider vision parsing
```

## Choose by what must survive, not by file type

A parse that returns fluent, plausible text can still have destroyed the one thing the
task needed. Decide first what has to still be true afterwards, then pick:

| What must survive | Parser | Cost |
|---|---|---|
| Plain prose, simple single-column layout | `PyMuPDFParser` | free, local, milliseconds |
| A Word document's text | `DocxParser` | free, local |
| Text on scans / no text layer | `DoclingParser` (OCR) | slow on CPU, free |
| **Table structure — merged cells, multi-row headers** | `MultimodalParser` or `VisionParser` | API call per page |
| Images explained in place, for RAG chunks | `VisionPlusParser` | Docling + API call |
| Docling quality without the local install | `DoclingApiClientParser` | needs `API_BASE` + `PASSWORD` |

Escalate only when a check fails — start at the cheapest row that could plausibly work,
verify (below), and move down one row if it did not.

## Why the cheap path scores zero on tables

Measured on a public benchmark's table split (40 documents, GriTS and TEDS scored against
ground-truth HTML table trees):

| Parser | Output format | Table structure score |
|---|---|---|
| Vision-LLM parsing (`MultimodalParser`) | HTML `<table>` | 0.90 – 0.96 |
| Docling, serialized as HTML | HTML `<table>` | 0.89 |
| Docling, as shipped (`use_markdown=True`) | markdown pipe table | **0.00** |
| PyMuPDF | plain text | **0.00** |

The zeros are not "much worse" — they are structurally unable to score, and that is the
transferable point. **The output format decides what can survive.** A markdown pipe table
has no way to express a merged cell or a two-row header, so a document containing one
comes back looking clean and quietly wrong. Plain text loses column boundaries entirely.

So the rule is not "always use vision". It is: if the tables carry merged cells or stacked
headers, the parser must emit HTML — and among the paths that do, vision-LLM parsing led
the specialized parser, with the gap widest on the messiest layouts.

Treat those numbers as a dated snapshot on one corpus, not a constant. What generalizes is
the format argument; re-measure the ranking on documents that look like yours.

## Parsing quality is usually a traceability decision, not an accuracy one

The expensive counterexample, measured on an extraction task: feeding the model the native
PDF, plain extracted text, or model-produced HTML gave **the same F1**. Parsing cost 22–25×
the wall time and was 93% of total spend, and bought no accuracy at all.

What it did buy was **bounding boxes**. When the parser returns coordinates for each
element, a citation can be matched to a box afterwards, and a human reviewer clicks a
highlighted region on the page. The model cannot invent that, and both halves stay
independently checkable.

Decide on that basis:

- The deliverable is a reviewer clicking a highlighted box → pay for the rich parse.
- Page-level evidence is enough, or nothing is reviewed by hand → do not. Feed the model
  the document and skip the parsing bill.

## Use the API correctly

The class method and the module-level function of the same name **do not return the same
type**, which is the easiest mistake to make here:

```python
from gaik.software_components.parsers import PyMuPDFParser, parse_pdf

text = PyMuPDFParser().parse_pdf("doc.pdf")     # -> str
result = parse_pdf("doc.pdf")                   # -> dict
text = result["text_content"]
```

Every `parse_document` returns a dict, and the key differs by parser:

```python
from gaik.software_components.parsers import (
    DocxParser, DoclingParser, VisionPlusParser, MultimodalParser,
)

DocxParser().parse_docx("doc.docx")                        # -> str
DoclingParser().parse_document("scan.pdf")["text_content"]      # OCR
VisionPlusParser().parse_document("doc.pdf")["parsed_markdown"] # note: different key
MultimodalParser(model_provider="openai").parse("doc.pdf")      # -> ParseResult
```

`MultimodalParser` takes **keyword arguments only** and has no `config` parameter — it
reads credentials from the environment. `ParseResult` is a plain dataclass with
`raw_markdown`, `clean_markdown`, `html` (populated only when `create_html=True`) and
`usage`; it has no `save()` method, so write the files yourself. `DoclingParser` has no
`parse()` method.

Set `merge_table=True` when a table runs across a page break — it instructs the model to
stitch the halves back together, which no local parser can do.

For which environment variables each provider needs, read
`references/parser-selection.md`.

## Verify before building on the output

Parsers fail quietly far more often than they raise, so check the output rather than the
exception. Three checks catch nearly everything:

**1. Emptiness, per page — never per document.** In one measured corpus 18 of 66 pages had
no text layer, spread across half the documents. A document-level `if not text` check
passes such a document as normal and those pages simply never reach the model: no error, no
warning, no missing file. Loop the pages and assert each one produced characters; report
which page numbers came back empty.

**2. Table structure, if tables matter.** Search the output for `<table>` (or pipe rows).
If the source has a merged cell and the output has no `<table>`, the structure is already
gone — escalate rather than patch the text.

**3. A known token round-trip.** Pick a handful of values you can see in the document — a
total, an invoice number, a date — and assert they appear in the parsed text. This catches
column-collapse and page-drop, which both otherwise read as fine prose.

## Gotchas

- `parse_document` returns `text_content` on `PyMuPDFParser` and `DoclingParser`, but
  `parsed_markdown` on `VisionPlusParser` and `DoclingApiClientParser`. Same method name,
  different key — read the dict, don't assume.
- Docling on CPU runs roughly 20–30 s/page. A GPU makes it faster but does **not** change
  its accuracy, so never reach for Docling to improve a *quality* result you measured on
  CPU — the number will be identical.
- `DoclingParser` requires the `parser` extra, not `parser-cpu`.
- Vision and audio components only accept OpenAI/Azure credentials and raise
  `NotImplementedError` for native Anthropic or Google. `MultimodalParser` is the
  multi-provider path.
- On Windows, write parsed output with `encoding="utf-8"` explicitly. `Path.write_text()`
  defaults to the platform codepage, which raises on characters a document parser routinely
  produces — and a crashed write downstream looks exactly like a bad parse.
- A parser returning fluent text is not evidence it read the whole document. Only the
  per-page check is.
