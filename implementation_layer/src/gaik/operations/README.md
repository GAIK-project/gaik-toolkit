# Operations

One function per common task around gaik's components: read a file, transcribe a recording,
generate field definitions, fill fields from a text with evidence, classify a text. Each
function takes plain arguments and returns a pydantic model, and all of them share one
settings object.

The functions add what an application otherwise writes around every component call:

- a timeout that fits real documents (120 s per model request instead of the 30 s default
  of structured calls),
- gaik's `print` output kept out of stdout, per thread and asyncio task,
- working files in a temporary folder that is always removed,
- a schema built from field definitions without a model call and without loading a file,
- a quote for every extracted value, checked against the text by
  [Source Tracing](../software_components/source_tracing/README.md),
- `run_async` for callers that must not block an event loop.

This is not a replacement for the components. Each function calls them the way their own
README shows and changes none of them. When you need rows, nested data, OCR, another parser
or your own prompt, use the component directly.

## Contents

- [Installation](#installation)
- [The operations](#the-operations)
- [Settings](#settings)
- [Field definitions and build_schema](#field-definitions-and-build_schema)
- [Async use](#async-use)
- [Quiet stdout](#quiet-stdout)
- [Errors](#errors)
- [Limits](#limits)

## Installation

```bash
pip install "gaik[operations]"
```

The extra installs what the five operations need (`parser-cpu`, `transcriber`, `extract`,
`source-tracing`). `classify_text(jev=...)` also needs `gaik[jev-classifier]`.

Importing `gaik.operations` loads the standard library and pydantic only. A component is
imported when the operation that needs it is first called.

Credentials are gaik's usual variables for the provider `LLM_PROVIDER` names (for Azure
OpenAI: `AZURE_API_KEY`, `AZURE_ENDPOINT`, `AZURE_DEPLOYMENT`). `parse_document` and
`build_schema` need none.

## The operations

| Function | What it does | Model calls |
| --- | --- | --- |
| `parse_document(path)` | Text of a PDF, DOCX, `.txt` or `.md` file | 0 |
| `transcribe_audio(path)` | Text of a recording | 1 per part |
| `generate_fields(requirement)` | Field definitions for a plain-language requirement | 2, more for nested data |
| `extract_fields(text, fields)` | The fields filled from the text, each value with its quote | 1 |
| `classify_text(text, labels)` | One label, with a probability per label | 1 |

### parse_document

```python
from gaik.operations import parse_document

document = parse_document("service_note.pdf")
print(document.kind)        # "pdf", "docx" or "text"
print(len(document.pages))  # one entry per PDF page; a DOCX or a text file is one page
print(document.text)        # the non-empty pages joined with a blank line
```

The kind is decided from the file's content, not its name. A PDF is read with
`PyMuPDFParser`, a DOCX with `DocxParser` (Markdown, with headings and tables in document
order). A text file is decoded as UTF-16 when it has a byte order mark, otherwise as UTF-8,
otherwise as Windows-1252. A file with no text raises `ValueError`: a scanned PDF needs a
vision parser.

A file that starts with the PDF header is a PDF under any name. A `.txt` or `.md` file that
only mentions `%PDF-` in its first lines is read as text.

A DOCX is a ZIP archive, and the parser loads its parts into memory. A file whose parts
unpack to more than 200 MB in all, or whose markup (the parts that pack to under a fifth of
their size) unpacks to more than 50 MB, raises `ValueError` before anything is read. The
parser's time grows with the number of paragraphs, so a very long document can still take
minutes.

The first call for a PDF or a DOCX imports gaik's parsers package. Where Docling is installed
(`gaik[parser]`, `gaik[all]`) that import loads it and can take a minute; with
`gaik[operations]` alone it takes a moment.

### transcribe_audio

```python
from gaik.operations import transcribe_audio

transcript = transcribe_audio("visit.m4a", language="Finnish", context="Names: Kallio, P-12.")
print(transcript.text, transcript.duration_s, transcript.model, transcript.failed_segments)
```

Accepts `.wav`, `.mp3`, `.m4a`, `.mp4`, `.webm`, `.ogg` and `.flac`. The cloud models take
no language setting, so `language` is told to the model in the prompt; `context` is added
to the same prompt. A recording over 25 MB or 20 minutes is split into parts, and only that
needs `ffmpeg` on the PATH. `duration_s` is `None` when the length of the recording could
not be read. `failed_segments` counts the parts that failed; their text is missing from the
result.

### generate_fields

```python
from gaik.operations import generate_fields

fields = generate_fields(
    "A service note describes one visit to a site. "
    "Extract the visit date, the site name and the technician's name."
)
for field in fields:
    print(field.name, field.type, field.required, field.description)
```

The result is a list of `FieldDefinition` you can show, edit and pass to `extract_fields`.
A repeated collection under one record (the line items of an order) becomes one `list[str]`
field named after the collection. A requirement that describes only rows (every row of a
price list) raises `ValueError`: use `SchemaGenerator` and `DataExtractor` for rows.

### extract_fields

```python
from gaik.operations import FieldDefinition, extract_fields

fields = [
    FieldDefinition(name="Käyntipäivä", type="date", label="Visit date"),
    FieldDefinition(name="site", description="The place where the work was done"),
    FieldDefinition(name="status", options=["ok", "fault"]),
]
for item in extract_fields(text, fields, instructions="Read the service note."):
    print(item.name, item.label, item.value, item.evidence, item.verdict)
```

One `ExtractedField` comes back per definition, in order. A field the text does not state
has `value=None`. With `evidence=True` (the default) the model gives one quote per value
and Source Tracing checks it against the text without a model:

| `verdict` | Meaning |
| --- | --- |
| `verified` | The quote is in the text and holds the value. |
| `reworded` | The quote is in the text; the value is the model's own wording of it. |
| `unchecked` | The quote is in the text but the value cannot be compared with it, or the value came without a quote. |
| `check` | The quote is not in the text, or it is there but does not support the value: it holds another number or date, or is too short to tell. Look at this one. |
| `None` | The field has no value. |

`evidence` is the quote exactly as it stands in the text, or `None` when it is not there.
A `check` verdict can therefore come with `evidence` filled.
`evidence=False` skips the quotes and the check.

### classify_text

```python
from gaik.operations import classify_text

result = classify_text(
    "Water is dripping onto the main electrical cabinet.",
    {"urgent": "Needs action today", "normal": "Can wait for the next visit"},
)
print(result.label, result.confidence, result.probabilities, result.backend)
```

`labels` is a mapping of label to meaning, or a list of labels (2 to 255). By default one
structured chat call is made on the configured provider; the probabilities are the model's
own estimates, normalised to sum to 1. They are not calibrated.

Pass a `JevClassifier` to use Jev instead:

```python
from gaik.software_components.jev_classifier import JevClassifier

jev = JevClassifier(api_key=key, base_url=url)
result = classify_text(text, labels, jev=jev)   # result.backend == "jev"
```

Jev's probabilities are calibrated. `confidence` is not the same figure on both backends:
with the chat model it is the probability of the chosen label (`probabilities[label]`),
with Jev it is Jev's own confidence, which is high when nearly all probability landed on
one label. Do not use one threshold for both; `probabilities[label]` is the probability of
the chosen label on either backend.

The Jev classifier reads the first 10 000 characters of the text and cuts the rest without
saying so. With Jev the text is sent to TypeSafe and processed in the United States: send
no personal data and nothing you may not move out of the EU.

## Settings

Every operation takes `settings=OperationSettings(...)`. Without it the defaults apply.

| Setting | Default | Meaning |
| --- | --- | --- |
| `config` | `None` | A gaik config dict (`get_llm_config(...)`). It holds the key and stays out of `repr`. |
| `provider` | `None` | Used when `config` is `None`: `get_llm_config(provider)`. `None` reads `LLM_PROVIDER`. |
| `timeout` | `120.0` | Seconds per model request. A timeout already in `config` wins. `None` leaves the config as it is. |
| `quiet` | `True` | Keep what gaik prints out of stdout. |
| `work_dir` | `None` | Parent of temporary working folders. `None` is the system's temporary folder. |
| `temperature` | `0.0` | Passed to `SchemaGenerator` and `DataExtractor` as is; `None` leaves it out. |
| `reasoning_effort` | `None` | Passed on as is; `None` leaves it out. |

`temperature=0.0` and `reasoning_effort=None` are the components' own defaults, so the
default settings change nothing in a request except the timeout.

```python
from gaik.operations import OperationSettings, extract_fields

settings = OperationSettings(provider="azure", timeout=300, reasoning_effort="low", temperature=None)
values = extract_fields(text, fields, settings=settings)
```

## Field definitions and build_schema

| `FieldDefinition` | Default | Meaning |
| --- | --- | --- |
| `name` | required | Any text, unique in a list. `Sää ja lämpötila` is fine. |
| `type` | `"str"` | `str`, `int`, `float`, `bool`, `date`, `decimal` or `list[str]`. |
| `description` | `""` | What the value means. The label is used when it is empty. |
| `label` | `None` | Display label. `None` derives it from the name (`work_done` gives `Work done`). |
| `required` | `False` | A field that is not required may be null. |
| `options` | `None` | Allowed values, for `str` fields. |
| `format` | `None` | Output format of a `date` field. |

Dates come back as `YYYY-MM-DD` unless `format` is one of the formats the extractor knows:
`%d/%m/%Y`, `%d-%m-%Y`, `%d.%m.%Y`, `%m/%d/%Y`, `%m-%d-%Y`, `%Y-%m-%d`, `%Y/%m/%d`,
`%Y.%m.%d`. A `decimal` value comes back as a string, so no digit is lost in JSON.

gaik's `FieldSpec` accepts ASCII snake_case names only. The operations therefore send each
field under a safe name (`Sää ja lämpötila` becomes `saa_ja_lampotila`) and map the result
back, so `ExtractedField.name` is always the name you gave.

`build_schema` gives you the same schema for use with the components directly:

```python
from gaik.operations import FieldDefinition, build_schema
from gaik.software_components.extractor import DataExtractor

schema = build_schema([FieldDefinition(name="site"), FieldDefinition(name="Sää")])
schema.model          # the pydantic class the model's answer is parsed into
schema.requirements   # gaik's ExtractionRequirements
schema.names          # {"site": "site", "saa": "Sää"}

rows = DataExtractor(config=config).extract(
    extraction_model=schema.model,
    requirements=schema.requirements,
    user_requirements="Fill the fields from the text.",
    documents=[text],
)
```

It makes no model call and reads no file.

## Async use

The operations are plain blocking functions. From async code, run them in a worker thread:

```python
from gaik.operations import extract_fields, run_async

values = await run_async(extract_fields, text, fields, settings=settings, deadline=240)
```

`deadline` is in seconds. When it passes, `run_async` raises `TimeoutError`. A thread cannot
be stopped: it ends when its own request timeout does (`OperationSettings.timeout`), and a
program started with `asyncio.run` waits for it before it exits. `run_async` works for any
blocking call, not only the operations.

## Quiet stdout

gaik's components print progress lines. With `quiet=True` an operation captures what its
own thread prints while it runs; other threads print as before. This matters for a program
that speaks a protocol on stdout, such as an MCP server on stdio.

The capture belongs to the thread or the asyncio task that opened it, so a `quiet_stdout()`
block in a coroutine may span an `await`: other tasks on the same event loop print as before.
A task, or an `asyncio.to_thread` call, started inside the block is captured with it.

To do this, `sys.stdout` is replaced by a small stand-in the first time an operation runs.
It stays in place for the life of the process and passes everything else through to the
real stream. Output written straight to the file descriptor (by a C library) is not
captured.

You can use the same capture around your own component calls:

```python
from gaik.operations import quiet_stdout

with quiet_stdout() as printed:
    rows = extractor.extract(...)
printed.getvalue()   # what the block printed
```

## Errors

There is no error type of its own.

| Error | When |
| --- | --- |
| `ValueError` | Input the operation refuses: an empty text, no fields, an unsupported file, bad labels, a file without text. |
| `FileNotFoundError` | The file does not exist. |
| `ImportError` | A package is missing; the message names the extra to install. |
| `TimeoutError` | `run_async` passed its deadline. |
| `RuntimeError` | A component returned nothing usable. |
| anything else | An error of a component or a provider SDK, unchanged. |

The operations' own messages hold no text from the input, and they log counts only.

## Limits

- One flat record per text. For rows or nested data use `SchemaGenerator` and
  `DataExtractor`.
- No OCR: a scanned PDF has no text to read. Use `VisionParser` or `DoclingParser`.
- A DOCX that unpacks to more than 200 MB, or to more than 50 MB of markup, is refused.
- Audio works with OpenAI and Azure OpenAI only, as the `Transcriber` does.
- Evidence covers the first quote of each field; the full report is in `SourceTracing`.
- The probabilities of the chat-model classifier are not calibrated.
