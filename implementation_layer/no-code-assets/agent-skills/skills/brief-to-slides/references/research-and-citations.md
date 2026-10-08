# Sources, research and citations

## Source modes

| | Strict | Extended |
|---|---|---|
| Content may come from | Only the user's data and sources: attached files, pasted text/data, links the user gave, documents they named and supplied | The user's material **first**, plus online research |
| Web search | None. Fetch only the exact URLs the user provided (do not follow on to other pages) | Yes: official documentation first, then other reliable sources |
| General knowledge | Allowed for structure, teaching method, plain-language explanation of concepts *in* the sources; not for new facts, figures, dates, examples presented as real, or claims | Allowed; facts that may change are verified online |
| Gaps | Leave the point out, or keep it in the notes as `[Not in provided sources: …]`; list every gap in the reply | Fill from research; mark added sources |
| Conflicts | Report contradictions within the user's material | If online sources disagree with the user's material, keep the user's version on the slide, flag the conflict in the notes and in the reply; never silently override |
| References slides | Only the user's sources | Two groups: "Provided sources" and "Additional sources (checked D Mon YYYY)" |

**Choosing the mode** (SKILL.md §1a): always ask first whether the user has own material (Q1);
if material arrives, ask strict vs extended next (Q2); an explicit user choice wins; no material →
extended; nobody to ask → strict if material was attached, stated at the top of the reply. A template, logo or outline on its own is not source
material.

Invented running examples and example data are allowed in both modes as long as they carry no
real-world claims. Do not label them on slides; disclose them in the speaker notes.

## Source ledger
Keep a ledger while writing (a scratch notes file or a dict in the spec), one line per factual
claim: `slide id · claim · source (file name + page/section, or URL) · mode (provided|added) · date checked`.
Use it to write source lines and references, and to verify in step 8 that every claim on a
slide and in its notes has an entry. In strict mode an entry must point to the user's material.

## Reading provided material
- Material arrives through the upload step (references/intake-questions.md). Run
  `scripts/collect_sources.py` to split the pasted links (commas, new lines) and list the files with
  the right way to read each type: PDF (pdf-reading skill), Word, PowerPoint, Excel/CSV (pandas),
  text/Markdown, JSON, HTML, images (view them; never read values off a chart image as exact).
- Open every link the user gave (in strict mode, only those exact pages). If a page cannot be
  opened, say so and continue; never cite a page you could not read.
- Read everything provided before planning; note each document's title, author/owner, date and
  version so citations are exact. Prefer its terminology.
- Data files: compute figures in code (spreadsheet or Python), never estimate; cite the file and
  sheet/column. Label any derived figure ("calculated from sales_2025.xlsx").
- Quote short passages exactly; paraphrase otherwise and keep the meaning.

## Extended-mode research
- Look up anything that describes the world now (product features and names, plans, prices,
  laws, dates, statistics, office holders) immediately before writing; record the check date.
- Watch for transitions (renamed or retired features); present an older feature only as context
  for a current choice, with dates.
- Stable knowledge (concepts, history, definitions) needs no lookup.

## Never invent
Sources, statistics, quotes, feature availability, screenshots, survey numbers, people. Where a
number would help but none is supported, use an obviously example-style figure inside the
running example (disclosed in the notes), or no number.

## Example data and interface drawings
- Running examples use invented organisations and records. **No label words on slides**
  ("fictional", "synthetic data", "illustrative", "mock-up"); state in the speaker notes that the
  case and data are invented, and mention it in the delivery reply.
- Interfaces you cannot capture are drawn as clearly simplified diagrams (generic shapes, no real
  product logos or pixel imitation) and never called screenshots; the notes say they are
  simplified drawings and explain the feature.
- External figures/photos: verify the source and licence; attribute on the slide.

## On-slide citation (source line)
One line at the bottom of the body area (12 pt grey): `Sources: Publisher, Short title; …
(checked D Mon YYYY)`. Provided documents: `Source: <document title>, p. 12` (or section).
Cite product-specific capabilities, external figures and factual claims. Keep it to one line;
shorten titles with an ellipsis if needed.

## References slides
After the timed slides, untimed. Each entry: `Author/Publisher (year). *Title*. Publisher/site.
short-url` with the short URL hyperlinked to the full URL (`ref()` helper); provided files
without a URL: `Owner (year). *Title* (provided document, version/date).` About 9–12 entries per
slide at 13–14 pt; split into "References (1/2)", "(2/2)". In extended mode group them as
"Provided sources" then "Additional sources". No disclaimer line on the slide. Notes give the
check date, what is likely to change, and that the example case and drawings are invented/original.
