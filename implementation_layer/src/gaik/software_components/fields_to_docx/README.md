# Fields to Word

Write extracted fields to a Word file. The document is plain and neutral: a title, an
optional line of facts (date, channel, author), a two-column table of labels and values, an
optional third column with the evidence for each value, and an optional appendix with the
source text or transcript.

It is built with python-docx only. There is no model call, no template file and no Pandoc,
and no provider configuration.

## Contents

- [Installation](#installation)
- [Quick start](#quick-start)
- [With the extractor and source tracing](#with-the-extractor-and-source-tracing)
- [With gaik.operations](#with-gaikoperations)
- [What `fields` may be](#what-fields-may-be)
- [How values are written](#how-values-are-written)
- [Options](#options)
- [Limits](#limits)
- [Example](#example)

## Installation

```bash
pip install "gaik[fields-to-docx]"
```

This adds python-docx. Importing the component without it raises an `ImportError` that
names the extra.

## Quick start

Label and value pairs, in the order you give them:

```python
from gaik.software_components.fields_to_docx import FieldsToDocx

result = FieldsToDocx().write(
    [
        ("Site", "Hall 3"),
        ("Work done", "Replaced the inlet valve of pump P-204"),
        ("Follow-up needed", False),
        ("Next visit", None),
    ],
    "service_report.docx",
    title="Service report",
    metadata={"Date": "2026-11-12", "Technician": "Example Person"},
    appendix="Service visit at Hall 3.\n\nThe technician replaced the inlet valve.",
)

print(result.path, result.rows, result.filled)  # service_report.docx 4 3
```

`write` returns a `DocxResult`:

| Attribute | Meaning |
|---|---|
| `content` | The .docx file as bytes |
| `path` | Where it was written, or `None` when no `output_path` was given |
| `rows` | Number of field rows in the table |
| `filled` | How many of them have a value |
| `save(path)` | Writes `content` to another `.docx` path and returns it |

Leave `output_path` out to get the bytes only, for an HTTP response or object storage:

```python
content = FieldsToDocx().write(pairs, title="Service report").content
```

## With the extractor and source tracing

One item of what `DataExtractor.extract()` returns is a record: field name to value. Pass
the record, display labels for its field names, and the `TraceReport` of
[source tracing](../source_tracing/README.md). The first citation of each field becomes the
row's evidence: the quote, and the verdict in brackets.

```python
from gaik.software_components.fields_to_docx import FieldsToDocx
from gaik.software_components.source_tracing import SourceTracing

tracing = SourceTracing()
task = tracing.augment(ServiceNote, "Fill the service report", source="text")
results = extractor.extract(
    extraction_model=task.model,
    requirements=requirements,
    user_requirements=task.prompt,
    documents=[note],
)
records, report = tracing.check_text(results, [note])

FieldsToDocx().write(
    records[0],                      # one record per file
    "service_report.docx",
    title="Service report",
    labels={"site": "Site", "work_done": "Work done"},
    trace=report,                    # or report.to_dict()
    appendix=note,
)
```

Pass the records `check_text` returns, not the raw results: the raw ones still hold the
`field_sources` citations as a field.

A field name without a label is made readable: `work_done` becomes `Work done`. The evidence
column appears when at least one row has a quote. `evidence=True` always shows it and
`evidence=False` hides it.

A report that covers several records gives each field's first citation, so check one
record at a time when you write one file per record.

## With gaik.operations

`gaik.operations.extract_fields` returns rows that already carry a label, a value, the quote
and the verdict. They go in as they are:

```python
from gaik.operations import FieldDefinition, extract_fields
from gaik.software_components.fields_to_docx import FieldsToDocx

fields = [
    FieldDefinition(name="site", label="Site"),
    FieldDefinition(name="visit_date", type="date", label="Date of visit"),
]
values = extract_fields(note, fields)

FieldsToDocx().write(values, "service_report.docx", title="Service report", appendix=note)
```

Install both with `pip install "gaik[operations,fields-to-docx]"`.

## What `fields` may be

`to_rows(fields, labels=..., trace=...)` is the function that decides, and `write` calls it.
It returns a list of `FieldRow(label, value, evidence, verdict)`.

| You pass | It is read as |
|---|---|
| A mapping | One record: a row per key, in the mapping's order |
| A sequence of `FieldRow` | The rows as they are |
| A sequence of `(label, value)` tuples | A row per tuple |
| A sequence of mappings with `value` and `label` or `name` | A row per mapping; `evidence` and `verdict` are read when present |
| A sequence of objects with a `value` attribute and a `label` or `name` attribute | A row per object, for example `gaik.operations.ExtractedField` |
| A sequence holding exactly one mapping that is not such a row | That record, so `write(extractor.extract(...))` works for one document, also when a field is called `value` |

`label` wins over `name`. A row with only a `name` takes its label from `labels`, or the
name made readable. The shapes can be mixed in one sequence.

Anything else raises a `ValueError` that names the reason: an empty input, a bare string,
several records in one call (`write() takes one record; call it once per record`), a row
without a label, or `trace` together with rows (a row carries its own evidence). The shape
is never guessed, and the message never repeats your data.

## How values are written

| Value | In the table |
|---|---|
| `None`, `""`, an empty list or dict, NaN, infinity | `empty_text`, and the row is not counted as filled |
| `True` / `False` | `true_text` / `false_text` |
| `int`, `float`, `Decimal` | The number; `3.0` is written `3` |
| `date`, `datetime` | ISO format, `2026-11-12` |
| A list of scalars | One item per line |
| A list of dicts | One line per item: `key: value; key: value` |
| A dict | One `key: value` line per key |
| Anything else | `str(value)` |

Text is written as text: markup characters such as `<`, `&` and `{{` have no effect.
Control characters and other characters a Word file cannot hold are removed, and line ends
become line breaks inside the cell.

## Options

The constructor sets how every file of this writer looks:

| Argument | Default | Meaning |
|---|---|---|
| `headers` | `("Field", "Value", "Evidence")` | Header texts of the three columns |
| `empty_text` | `"—"` | What a field without a value shows |
| `true_text` | `"Yes"` | What `True` shows |
| `false_text` | `"No"` | What `False` shows |
| `font_name` | `"Calibri"` | Font of the body and the headings |
| `font_size` | `11.0` | Size of the body text in points |
| `label_width_cm` | `5.5` | Width of the label column, at most half of the text width |

`write` takes what belongs to one file:

| Argument | Default | Meaning |
|---|---|---|
| `fields` | required | A record or rows, see above |
| `output_path` | `None` | A `.docx` path; parent folders are created and an existing file is overwritten |
| `title` | `"Report"` | The heading and the title property of the file |
| `metadata` | `None` | Facts for the line under the title: a mapping or `(label, value)` tuples |
| `labels` | `None` | Display labels by field name |
| `trace` | `None` | For a record: a `TraceReport` or its `to_dict()` |
| `evidence` | `None` | `True` shows the evidence column, `False` hides it, `None` shows it when a row has a quote |
| `appendix` | `None` | A string (split into paragraphs on blank lines) or a sequence of paragraphs |
| `appendix_title` | `"Appendix: source text"` | Heading of the appendix |
| `footer` | `None` | Text of the page footer; no footer when left out |

A Finnish report, for example:

```python
writer = FieldsToDocx(
    headers=("Kenttä", "Arvo", "Lähde"), true_text="Kyllä", false_text="Ei", empty_text="-"
)
writer.write(record, "raportti.docx", title="Huoltoraportti", appendix_title="Liite: litterointi")
```

The file's author property is empty and its dates are the time of writing. The component
logs the number of rows and bytes, never a label, a value or the source text.

## Limits

- One record per file. Call `write` once per record.
- No nested tables: a list or a dict inside a value is written as lines of text in its cell.
- No template file: the layout is the one described here, on an A4 page. Open the result
  in Word to restyle it.
- No images, charts or page numbers.
- Evidence comes from the first citation of a top-level field. Citations of values inside a
  list (`items[0].quantity`) are not shown.
- The quote is shown as the model gave it. The verdict tells whether it was found in the
  source; this component does not check anything itself.

## Example

[`fields_to_docx_example.py`](../../../../examples/software_components/fields_to_docx/fields_to_docx_example.py)
runs without credentials. It writes two files to the system's temporary folder: one from
label and value pairs with a facts line and an appendix, and one from a record whose
evidence is checked by `SourceTracing().check_text`.

## License

MIT - see [LICENSE](../../../../../LICENSE)
