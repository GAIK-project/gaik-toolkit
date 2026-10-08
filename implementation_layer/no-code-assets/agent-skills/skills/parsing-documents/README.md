# parsing-documents

An [Agent Skill](https://agentskills.io/specification) that helps a coding agent turn PDFs,
scans and Word files into text or markdown with the [`gaik`](https://pypi.org/project/gaik/)
parsers, and pick the parser that keeps the structure the next step depends on.

## Use it when

- you read a PDF or DOCX into text, pull tables out of a document, or run OCR on scans;
- you feed documents into a RAG pipeline or an LLM;
- you choose between PyMuPDF, Docling and vision-LLM parsing;
- a parse looked fine but tables, columns or whole pages came out wrong or empty;
- parsing costs more time or money than expected.

Example request:

```text
Use the parsing-documents skill to choose a parser for my PDFs and check that the tables
came through intact.
```

## What it covers

- Choosing a parser by what must survive (tables, layout, page numbers), not by file type.
- Why the cheap local path loses table structure, and when to move up to a vision model.
- Calling each parser correctly and reading its result.
- Checking the output page by page before building on it.

## Files

| File | Content |
|---|---|
| `SKILL.md` | The workflow the agent follows |
| `references/parser-selection.md` | Parser comparison, read when choosing a parser |

## Needs

`pip install "gaik[parser]"`, or `gaik[multimodal-parser]` for vision parsing. Vision parsers
also need an LLM provider key.

Install the skill with the [gaik-toolkit plugin](../../README.md#installing).
