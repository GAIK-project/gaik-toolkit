# Source Tracing

Evidence for extracted values. You ask the extractor to return one short verbatim quote per
value. Source tracing then finds each quote in the source with plain code (no model call),
compares the value with the quote, and tells you whether a person can trust the value on
that evidence. For PDFs it also gives the position of the quote on the page, taken from the
PDF's own text layer.

It works around the extractor you call and changes none of them: `DataExtractor`,
`VisionExtractor`, `DocumentsToStructuredData` and `AudioToStructuredData` are used as they
are.

## Contents

- [Installation](#installation)
- [Quick start](#quick-start)
- [Using it with each component](#using-it-with-each-component)
- [What you get back](#what-you-get-back)
- [Reading the verdicts](#reading-the-verdicts)
- [Viewing the results](#viewing-the-results)
- [How the check decides](#how-the-check-decides)
- [Settings](#settings)
- [Limits](#limits)
- [Related components](#related-components)

## Installation

```bash
pip install gaik[source-tracing]
```

This adds PyMuPDF, which only the PDF check (`check_pdf`) uses. Checking text and transcripts
(`check_text`) works without it.

## Quick start

Source tracing is three steps around the extractor call you already have:

```python
from gaik.software_components.source_tracing import SourceTracing

tracing = SourceTracing()

# 1. Ask for evidence. This returns a copy of your schema with a citation field added, and
#    your task text with the instruction appended. Your own schema is not changed.
#    source="text" when the extractor reads text, source="files" when it reads the files
#    themselves (VisionExtractor).
task = tracing.augment(Invoice, "Extract the invoice number and the total", source="text")

# 2. Call the extractor as usual, with the augmented model and prompt.
results = extractor.extract(
    extraction_model=task.model,
    requirements=requirements,
    user_requirements=task.prompt,
    documents=[text],
)

# 3. Check each value against its quote.
clean, report = tracing.check_text(results, [text])

print(clean)             # your results, without the evidence
print(report.summary())  # {"verified": 2, "check": 0, "reworded": 0, "unchecked": 0, "total": 2, "coverage": 1.0}
```

The same three steps for a PDF read by `VisionExtractor`:

```python
task = tracing.augment(Invoice, "Extract the invoice number and the total", source="files")
result = vision_extractor.extract(
    file_paths=["invoice.pdf"],
    user_requirements=task.prompt,
    extraction_model=task.model,
    requirements=requirements,
)
clean, report = tracing.check_pdf(result.data, ["invoice.pdf"])
```

Runnable versions for all four components, on the sample purchase orders `PO.pdf` and
`PO2.pdf`, are in the [examples](../../../../examples/software_components/source_tracing/).

To see the evidence on the page, run `source_tracing_viewer_example.py`. It runs the
`VisionExtractor` with source tracing, then writes one self-contained HTML page
(`output/trace_view.html`, no server needed) with the quotes outlined on the PDF pages, a verdict
and an explanation for every value, and the function that draws the boxes, which you can copy into
your own interface. Three extra fields in its task are chosen so that the page shows all four
verdicts.

## Using it with each component

| Component | Ask for evidence | Check against |
|---|---|---|
| `DataExtractor.extract()` | `extraction_model=task.model`, `user_requirements=task.prompt` | `check_text(results, texts)` with the `documents` you passed |
| `VisionExtractor.extract()` | the same two arguments, plus `requirements` (so it keeps your schema), and `source="files"` | `check_pdf(result.data, file_paths)` with the same files |
| `DocumentsToStructuredData.run()` | `schema=task.model`, `requirements=...`, `user_requirements=task.prompt` | `check_text(result.extracted_fields, result.parsed_documents)` |
| `AudioToStructuredData.run()` | the same three keyword arguments | `check_text(result.extracted_fields, transcript_used(result))` |

Pass your own `schema=` and `requirements=` to the two modules. A module that generates its
own schema would receive the evidence request as part of the text it generates the schema
from.

`transcript_used(result)` returns the transcript the pipeline extracted from: the enhanced
transcript when there is one, otherwise the raw one. Quotes must be checked against exactly
that text.

With `VisionExtractor(include_verification=True)` the values keep their confidence envelopes
(`{"value": ..., "confidence_score": ...}`). Source tracing compares the bare value and leaves
the envelopes in `clean`.

## What you get back

`augment(...)` returns an `Augmented` with `model` (the schema with the citation field) and
`prompt` (the task with the instruction).

`check_text(...)` and `check_pdf(...)` return a pair, `(clean, report)`:

- **`clean`**: your extraction results with the citation field removed. It has the same shape
  you passed in (a dict stays a dict, a list stays a list). The input is not modified.
- **`report`**: a `TraceReport`.

### `TraceReport`

| Member | Meaning |
|---|---|
| `report.items` | a `TracedValue` for every citation the model gave, in the order given |
| `report.summary()` | counts per verdict, `total`, and `coverage` |
| `report.coverage` | the share of the extracted values that came with a citation (`None` when nothing was extracted) |
| `report.documents` | file names of the checked PDFs (empty for texts) |
| `report.to_dict()` | the whole report as plain JSON: `summary`, `documents`, `sources` |

### `TracedValue` (one per citation)

| Field | Meaning |
|---|---|
| `field` | path of the value, e.g. `total` or `lines[0].quantity` |
| `value` | the extracted value at that path |
| `quote` | the snippet the model gave as evidence |
| `document`, `page` | where the quote was found (1-based); the cited ones when it was not found |
| `cited_page` | the page the model named |
| `status` | `found` (on the cited page or in the cited text), `moved` (found on another page, in another file or text), `not_found`, `no_text_layer` (a scan or an image file) |
| `value_status` | `match`, `mismatch` or `unchecked`: whether the value is in the quote |
| `verdict` | `verified`, `check`, `reworded` or `unchecked`; see below |
| `rects` | PDF only: boxes of the quote's words, one per word |
| `value_rects` | PDF only: boxes of the value inside the quote (empty when the value is not located in it) |
| `span` | text only: `(start, end)` character offsets of the quote in the text |
| `occurrences` | how many times the quote occurs in the text, or on the page it was found on (0 when not found) |
| `record` | index of the row the value belongs to when the results hold lists of records; `None` for a value every row shares |

A box is `{"x", "y", "w", "h"}`, as fractions of the page from 0 to 1, measured from the top
left corner.

Real output for one value on `PO2.pdf`:

```json
{
  "summary": {"verified": 1, "check": 0, "reworded": 0, "unchecked": 0, "total": 1, "coverage": 1.0},
  "documents": ["PO2.pdf"],
  "sources": [
    {
      "field": "purchase_no", "value": "7200445321", "quote": "PURCHASE NO: 7200445321",
      "document": 1, "page": 1, "cited_page": 1,
      "status": "found", "value_status": "match", "verdict": "verified",
      "rects": [
        {"x": 0.498, "y": 0.114, "w": 0.073, "h": 0.014},
        {"x": 0.575, "y": 0.114, "w": 0.024, "h": 0.014},
        {"x": 0.649, "y": 0.114, "w": 0.073, "h": 0.014}
      ],
      "value_rects": [{"x": 0.649, "y": 0.114, "w": 0.073, "h": 0.014}],
      "span": null, "occurrences": 1, "record": 0
    }
  ]
}
```

For text, `rects` is empty and `span` holds the offsets, for example `"span": [19, 38]`.

## Reading the verdicts

| Verdict | Meaning | What a reviewer should do |
|---|---|---|
| `verified` | the quote is in the source and holds the value | nothing, or a glance |
| `check` | the quote is not in the source, or holds another number or date than the value | look at it: the value may be wrong, or a legitimate conversion |
| `reworded` | the quote is in the source, but a text value is not in it | usually the model's own wording (a translation or a summary); read it |
| `unchecked` | cannot be compared: a list, a number written in words, a scan | check by hand |

A `verified` value matches its quote. It does not prove the quote is the right place to read
that value. Use `LLMJudge` or a person for that.

Examples from the sample purchase order:

| Value | Quote | Verdict | Why |
|---|---|---|---|
| `7200445321` | `PURCHASE NO: 7200445321` | verified | the value is in the quote |
| `2026-02-15` | `DATE: 02/15/2026` | verified | the same date in another order |
| `7200-4453-21` | `PURCHASE NO: 7200445321` | verified | the same characters with other separators |
| `2721.55` (kg) | `... 6,000 LB LB` | check | the only number in the quote is 6000 |
| `alumiiniseoksinen pyörötanko` | `010 6061-T6 Aluminium Alloy Round Bar` | reworded | a Finnish value in an English line |

## Viewing the results

**In the terminal.** Loop over the items:

```python
for item in report.items:
    print(f"{item.verdict:<9} {item.field:<22} {item.value!s:<20} doc {item.document} p.{item.page}  {item.quote}")
print(report.summary())
```

**Route by verdict.** For a human-review step, show only what needs a person:

```python
needs_review = [item for item in report.items if item.verdict != "verified"]
uncited = report.coverage is not None and report.coverage < 1  # some values came with no quote
```

**On a PDF page, in your own interface.** Each item with `rects` says which page of which
document and where. Show that page at any size and place a box for every rect in percentages
of the page, so it scales with the image:

```js
// container: position: relative, same aspect ratio as the page image
for (const r of item.rects) {
  const box = document.createElement("div");
  Object.assign(box.style, {
    position: "absolute", border: "2px solid #16a34a",   // colour by item.verdict
    left: `${r.x * 100}%`, top: `${r.y * 100}%`, width: `${r.w * 100}%`, height: `${r.h * 100}%`,
  });
  container.appendChild(box);
}
// the value inside the quote, filled: draw item.value_rects the same way with a background
```

The same in Python with PyMuPDF, drawing onto a copy of the page and saving an image:

```python
import pymupdf

doc = pymupdf.open("invoice.pdf")
for item in report.items:
    if item.rects and item.document == 1:
        page = doc[item.page - 1]
        w, h = page.rect.width, page.rect.height
        for r in item.rects:
            page.draw_rect(pymupdf.Rect(r["x"] * w, r["y"] * h, (r["x"] + r["w"]) * w, (r["y"] + r["h"]) * h), color=(0.1, 0.6, 0.2))
doc[0].get_pixmap(dpi=110).save("page1.png")
```

The fractions are relative to the page as PyMuPDF sees it. If you render with another library,
check one document first: rotated or cropped pages are not covered by the tests.

**In text or a transcript.** `span` gives character offsets into the exact text you passed to
`check_text`, so highlight `text[start:end]`:

```python
start, end = item.span
highlighted = text[:start] + "[[" + text[start:end] + "]]" + text[end:]
```

**With rows of records.** `record` ties a value to its row in the unwrapped results, so a
table view can show each row's evidence next to its cells.

**To send to a front end.** `report.to_dict()` is JSON-ready.

## How the check decides

No model is involved in the check. For each citation:

1. **Quote in the source?** Quote and source are reduced to lowercase words with punctuation
   and spacing removed, and the quote's words must appear as an unbroken run. The cited page is
   tried first, then the other pages of that file, then the other files.
2. **Value in the quote?** Numbers are compared as numbers in both European and American
   formats (`3.000 kg` holds `3000`, `1.234,50` holds `1234.5`); dates by their year, month and
   day in any order (`11.04.2025` holds `2025-04-11`), including month names; text by its
   words, or as the same characters with other separators (`7200-4453-21` for `7200445321`).
3. **Verdict** from the two answers, as in the table above.
4. **Position** (PDF): the matched words' boxes from the PDF's own text layer, and the box of
   the value inside the quote when it can be located.

Evidence is only as good as what the model returns: it must follow the instruction and copy
the quote exactly.

## Settings

`SourceTracing(policy=TracePolicy(...))` sets the judgment calls:

| Setting | Default | Effect |
|---|---|---|
| `number_tolerance` | `1e-6` | largest difference at which two numbers are equal |
| `match_reformatted_identifiers` | `True` | count `7200-4453-21` as matching `7200445321` |
| `reworded_is_problem` | `False` | report `reworded` as `check`, for tasks that must copy values verbatim |
| `min_quote_words` | `1` | a quote with fewer words is reported as `check` |
| `ambiguous_quote_is_check` | `False` | report a quote that occurs more than once as `check` |

## Limits

- The model must follow the instruction. A model that skips citations lowers `coverage`; one
  that paraphrases a quote shows as `not_found` (verdict `check`).
- A quote that occurs more than once (a unit, a header) is boxed at its first occurrence, and
  `occurrences` says how many there are. It can not tell which one the model read.
- The check needs text. A scan has no text layer, so its values are `unchecked`; an image
  file is `no_text_layer`.
- Positions are in the transcript text or on the PDF page. A quote is not mapped to a time in
  an audio or video recording.
- A value in another format, such as a converted unit, is flagged `check`: the code can not tell
  a correct conversion from a wrong number.
- A number with one dot or comma and three digits after it, such as `4.200`, can be read as
  4.2 or 4200. The check accepts either, so a value of 4.2 matches a quote of `4.200` even when the
  document means 4200 and the value is a conversion (kilograms to tonnes, for example).
- Citations add output tokens to the extraction call.

## Related components

- `LLMJudge` is the other review aid: a second model reads the source and scores each field.
  Source tracing needs no second model call and shows the person where to look; the judge can
  catch values that are in the text but wrong for the question. They can be used together.
- `VisionExtractor(include_verification=True)` returns a confidence score for each value. That
  is the model's own rating, not evidence, and it can be combined with source tracing.
- `SourceNormalizer` turns mixed input files into text. It is a different job (it prepares the
  source) and gives no evidence.
- The demo app has its own copy of this logic for its Extractor and incident reporting pages.
  It is not changed by this component.

## Examples

Runnable examples are in the
[examples folder](https://github.com/GAIK-project/gaik-toolkit/tree/main/implementation_layer/examples/software_components/source_tracing).
They run a real extractor with source tracing on the sample purchase orders `PO.pdf` and `PO2.pdf`
(or a sample recording) and print what the check found. They need model credentials in `.env`.

| Example | What it does |
|---|---|
| `source_tracing_example.py` | `VisionExtractor` on a PDF, then `check_pdf`: a verdict per value and the page box of each quote |
| `source_tracing_data_extractor_example.py` | `DataExtractor` on the PDF's text, then `check_text`: a verdict per value and where each quote sits in the text |
| `source_tracing_documents_example.py` | `DocumentsToStructuredData` with a supplied schema, checked against the parsed text |
| `source_tracing_audio_example.py` | `AudioToStructuredData` on a sample recording, checked against the transcript it read (`transcript_used`) |
| `source_tracing_viewer_example.py` | `VisionExtractor` with source tracing, then one self-contained HTML page (`output/trace_view.html`) that shows every quote outlined on the PDF page, a verdict and an explanation per value, and the function that draws the boxes. Three extra fields make all four verdicts appear. `trace_viewer.py` builds the page |

`po_schema.py` holds the schema the examples extract.

## License

MIT - see [LICENSE](../../../../../LICENSE)
