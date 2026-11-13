# Fields to Word

Write extracted fields to a Word file: a title, an optional line of facts, a table of labels
and values, an optional evidence column, and an optional appendix with the source text or
transcript. python-docx only: no model call, no template file, no Pandoc, no provider
configuration.

## Installation

```bash
pip install "gaik[fields-to-docx]"
```

## Quick Start

```python
from gaik.software_components.fields_to_docx import FieldsToDocx

result = FieldsToDocx().write(
    [("Site", "Hall 3"), ("Work done", "Replaced the inlet valve"), ("Next visit", None)],
    "service_report.docx",
    title="Service report",
    metadata={"Date": "2026-11-12"},
    appendix="Service visit at Hall 3.\n\nThe technician replaced the inlet valve.",
)
print(result.path, result.rows, result.filled)  # service_report.docx 3 2
```

Leave `output_path` out to get the bytes only (`result.content`).

## API

```python
FieldsToDocx(
    *,
    headers=("Field", "Value", "Evidence"),
    empty_text="—",
    true_text="Yes",
    false_text="No",
    font_name="Calibri",
    font_size=11.0,
    label_width_cm=5.5,
)

writer.write(
    fields,                # one record, or a sequence of rows
    output_path=None,      # a .docx path; None returns the bytes only
    *,
    title="Report",
    metadata=None,         # mapping or (label, value) tuples for the line under the title
    labels=None,           # display labels by field name
    trace=None,            # for a record: a SourceTracing TraceReport or its to_dict()
    evidence=None,         # True shows the evidence column, False hides it, None: when a row has a quote
    appendix=None,         # a string (paragraphs split on blank lines) or a sequence of paragraphs
    appendix_title="Appendix: source text",
    footer=None,
) -> DocxResult            # content (bytes), path, rows, filled, save(path)
```

`fields` may be:

- a mapping: one record, field name to value (one item of what `DataExtractor.extract()` returns);
- a sequence of `FieldRow(label, value, evidence, verdict)`, of `(label, value)` tuples, or of
  mappings or objects with a `value` and a `label` or `name`, such as the result of
  `gaik.operations.extract_fields`;
- a sequence holding exactly one record.

Anything else raises `ValueError`. Several records in one call raise too: write one file per
record.

## Limits

- One record per file; no nested tables, images or page numbers; no template file.
- The evidence column shows the quote and verdict it is given. The check itself is
  [Source Tracing](../../../implementation_layer/src/gaik/software_components/source_tracing/README.md)'s.

Full reference: [component README](../../../implementation_layer/src/gaik/software_components/fields_to_docx/README.md).
Example: [fields_to_docx_example.py](../../../implementation_layer/examples/software_components/fields_to_docx/fields_to_docx_example.py).
