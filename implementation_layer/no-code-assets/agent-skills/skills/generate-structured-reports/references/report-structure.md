# The report structure

The structure is the report's sections: for each a title and a prompt saying what it must
contain. It is agreed with the user in chat **after** normalization, as part of the whole spec.
Prompts and required items stay generic: they say what a section of this kind of report should
cover, never what the sources contain or whether they cover it; curation, writing and review
find that out. Curation, the first stage that pays for every section, starts only once the user
has accepted the whole spec.

## The structure file

The agent keeps the drafted structure as a list in `structure.json` and passes it to
`run_report.py propose-spec --structure`, which turns it into the spec's sections; an already
agreed spec's sections are changed with `run_report.py set-sections`:

```json
[
  {
    "title": "Building services",
    "prompt": "Heating, ventilation, water and sewer, as observed on site and in the documents.",
    "required_items": ["ventilation system and its age", "latest sewer camera inspection"]
  },
  {
    "title": "Summary",
    "prompt": "The main findings and the most urgent repairs, in one paragraph.",
    "summary_of": ["Building services"]
  }
]
```

| Field | Meaning | In the spec |
|---|---|---|
| `title` | The section heading, in the report's own words and language. Unique | `title` |
| `prompt` | What the section must contain and how. Required | `instructions` |
| `required_items` | Optional. Facts the section must cover; each one no source covers is marked `(missing: …)` in the report | `required_items` |
| `summary_of` | Optional. Titles of the sections this one is written from. Such a section gets no facts of its own | `depends_on` (as ids) |

`set-sections` turns titles into ids (rules below), checks the structure, and replaces only the
spec's `sections`, leaving its sources, settings and relative paths as they were. When a rule
fails it changes nothing and says which section breaks which rule:

- the report has at least one section;
- at least one section is written from the sources, not only summaries;
- titles differ, and every section has a prompt;
- a summary names sections that exist, not itself, and summaries do not depend on each other
  in a circle.

Changing the structure after curation is allowed; `set-sections` then warns that curation and
synthesis must run again, and the run record marks them as not current.

## Agreeing it in chat

Never present the sections on their own. Write the draft to `structure.json`, run
`propose-spec --structure`, and show the sections as group (3) of the whole spec (SKILL.md,
step 5), next to the report-wide fields, the sources (`primary` and `secondary`, even when
empty), the sample, the models and the settings. Show all four fields of every section, for
example:

> | # | title | instructions | required_items | depends_on |
> |---|---|---|---|---|
> | 1 | Building services | Heating, ventilation, water and sewer: their type, age and condition. | ventilation system and its age; latest sewer camera inspection | none |
> | 2 | Summary | The main findings and the most urgent repairs, in one paragraph. | none | 1 |
>
> `depends_on` makes a section derived: it gets no facts of its own and is written only after
> the sections it names, from their text. Shall I keep these sections, or would you like to
> change any field? You can rename sections, rewrite what they should contain, change the
> required items or what a section depends on, add or remove sections, or give me a structure
> of your own.

Never put source findings into these fields or into what you say about them: no "the notes
cover it", "covered by both sources", "the sources say little here", and no names, figures or
examples from the sources.

Then act as a helpful assistant until the user accepts:

- Apply each change the user asks for: a new title, a rewritten prompt, a new section in a
  given place, a deleted section, a new order, a section turned into a summary of others or
  back. When a deleted section was summarized by another, remove it from that summary too.
- A user who defines their own structure, at the start or at any point, replaces the draft.
  Take their sections as given and ask only about what they left open: what a section should
  contain, whether "Summary" is written from the others, which points are must-cover items.
- After each change, show the updated sections with all four fields. Keep the user's own
  wording for titles and prompts; suggest better wording, do not impose it.
- Advise once, briefly, where the report would get weaker: a prompt too vague to act on ("other
  matters"), two sections asking for the same facts, a must-cover item phrased as a topic rather
  than a fact, or a summary whose `depends_on` leaves out a section it should draw on. Do not
  predict which sections the sources will fill or leave thin; curation reports that.
- Explain a rule when a change breaks it, and offer a way out. Deleting the last section:
  "The report needs at least one section; shall I keep this one, or what should replace it?"
  Making every section a summary: "Each summary needs a section written from the sources;
  which one should hold the facts?"
- Sections have one level. When the user asks for sub-sections, fold them into the section's
  prompt ("Cover heating, then ventilation, then water and sewer, each under its own
  sub-heading") and say so.
- Propose `required_items` and `depends_on` for every section yourself, with a one-line,
  generic reason for each non-obvious choice (why the item is essential to this kind of report;
  why a section is or is not written from others); an empty list is a proposal too, and the
  user accepts or changes it like the title and prompt.
- Do not move on until the user accepts the sections; apply each change to
  `spec_proposal.json` and check it with `apply-spec --check` (SKILL.md, step 5). Use
  `set-sections` only to change the sections of a spec that was already agreed.

## Drafting from a template

```bash
python <skill>/scripts/template_to_spec.py template.docx --out outline.json
```

The script reads a Word (.docx), Markdown or text template locally, with no model call. Word
templates are read with python-docx, which keeps their bullet lists; gaik's DOCX parser drops
the list markers, so a checklist would otherwise read as plain text. Write its output to a file with `--out`: piping it on Windows can garble non-ASCII text.
`outline.json` holds the draft `structure` (in the format above) and, for checking it, the
detailed `sections` and `diagnostics`. How the template is read:

| The template has | The draft gets |
|---|---|
| One top heading above all the others | The report title, not a section |
| Headings at the next level | One section each |
| Deeper headings | Kept inside their section, as labelled text in its prompt |
| Text under a heading | The section's prompt |
| A bulleted list after "Include:", "must cover" or similar, or a list of short items without figures | `required_items` |
| Bullets that read as content (full sentences, figures, dates) | `to_confirm`: usually example facts. Ask the user; never treat them as facts |
| `[insert …]`, `<…>`, `{…}`, `____` | Left in the prompt and listed under `placeholders` in `sections`: they are instructions, never facts |
| A title such as Summary, Conclusions, Recommendations, Yhteenveto, Johtopäätökset, Suositukset, Sammanfattning | `summary_of` all the other sections. A label alone does not prove it: ask if unsure |

A section with no text under its heading gets an empty prompt: write one from the heading and
the normalized sources before showing the draft. Check `diagnostics`: a template with no
headings is drafted as if there were no template; duplicate titles and skipped heading levels
need a decision.

Word output follows the report's headings, not the template's page layout, branding, headers,
logos or fields. The report is a new document with the template's structure; its placeholders
are not filled in place.

## Drafting without a template

Read the normalized texts and the request, and propose sections that fit both: what the sources
can actually fill, in an order that suits the reader, with a concrete prompt for each and
must-cover items where the user named facts that matter. Add a summary written from the other
sections if the report needs one. Keep it short: four to eight sections suit most reports.

## Section ids

Ids must match `^[A-Za-z0-9_-]+$`, so `set-sections` makes them from the titles: letters such
as `ä`, `ö`, `å` lose their accents, `ß`, `æ`, `ø` become `ss`, `ae`, `o`, the result is
lowercased and words are joined with `_`. A clash gets `_2`, `_3`; a title that gives no id
(only punctuation or non-Latin letters) gets `section_N`. Titles keep their original wording;
the ids appear only in the workspace's file names.

| Title | Id |
|---|---|
| Yhteenveto ja jatkotoimet | `yhteenveto_ja_jatkotoimet` |
| Työmaan äänitys | `tyomaan_aanitys` |

## Worked example

A Markdown template:

```markdown
# Kuntoarvio

## Talotekniikka
Describe heating, ventilation, water and sewer. Include:
- ventilation system and its age
- latest sewer camera inspection

## Yhteenveto
The main findings in one paragraph.
```

The draft structure from `template_to_spec.py`:

```json
[
  {
    "title": "Talotekniikka",
    "prompt": "Describe heating, ventilation, water and sewer. Include:",
    "required_items": ["ventilation system and its age", "latest sewer camera inspection"],
    "summary_of": []
  },
  {
    "title": "Yhteenveto",
    "prompt": "The main findings in one paragraph.",
    "required_items": [],
    "summary_of": ["Talotekniikka"]
  }
]
```

The agent tidies the first prompt, presents both sections, and the user adds one: "Add a
section called Vesikatto before Talotekniikka, covering the roofing material and its condition,
and include it in the summary." The accepted structure has three sections; `set-sections` writes
them into the spec as `vesikatto`, `talotekniikka` and `yhteenveto`, with `yhteenveto`
depending on the other two. If no source mentions a sewer inspection, the report says
`(missing: latest sewer camera inspection)` in Talotekniikka, where the reader sees the gap.
