# extracting-structured-data

An [Agent Skill](https://agentskills.io/specification) that helps a coding agent pull fields,
tables and line items out of documents into a validated schema with the
[`gaik`](https://pypi.org/project/gaik/) toolkit.

## Use it when

- you extract fields from invoices, forms, contracts, reports or scans into JSON or a
  Pydantic model;
- an extraction request fails with a 400, returns a cut-off list, or drops its deepest fields;
- you decide whether to parse a document first or give the PDF straight to the model;
- you want page numbers, quotes or confidence scores as evidence for each value;
- you need to measure extraction accuracy.

Example request:

```text
Use the extracting-structured-data skill to design a schema for the invoices in this folder
and add page and quote evidence to each field.
```

## What it covers

- The two entry points: `VisionExtractor` for a PDF or image, `DataExtractor` for parsed text.
- Schema design: fixing the schema before the prompt, and the provider's property-count limit.
- Failures that look alike but have different causes: refused, truncated and silently dropped.
- Evidence that can be checked against the document.
- Choosing providers separately for audio, vision and extraction.

## Files

| File | Content |
|---|---|
| `SKILL.md` | The workflow the agent follows |
| `references/measuring-extraction.md` | How to measure accuracy, read before reporting a figure |

## Needs

`pip install "gaik[extract]"`, or `gaik[vision-extract]` for PDFs and images, and an LLM
provider key.

Install the skill with the [gaik-toolkit plugin](../../README.md#installing).
