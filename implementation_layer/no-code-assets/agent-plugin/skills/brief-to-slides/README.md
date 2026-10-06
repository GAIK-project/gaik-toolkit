# brief-to-slides

An [Agent Skill](https://agentskills.io/specification) that builds a visual, **editable
PowerPoint deck** from a short brief: a topic, an audience and a length. Every slide gets
speaker-ready notes in the PowerPoint Notes pane, the timings add up exactly to the length you
asked for, claims are cited, and the layout is checked by rendering the deck before it is
delivered.

It needs no template and no outline. Whatever you leave out is filled from a default brief
(`references/default-brief.md`), and the reply lists every default it assumed.

## Use it when

- you ask for a presentation, slide deck, lecture, workshop, training session or talk;
- you have a brief, an outline, or source documents (PDF, Word, PowerPoint, Excel, CSV,
  Markdown, JSON, HTML, images, links) that should become slides;
- you need speaker notes and per-slide timing, not only slide text;
- you want targeted changes to a deck the skill already made ("make slide 7 simpler") without
  the rest of the deck moving.

Example requests:

```text
Make a 45-minute teaching deck on data privacy basics for first-year nursing students.
```

```text
Turn the attached project report into a 10-minute briefing for the steering group.
Use only my material.
```

## What you get

- A `.pptx` with 5–30 slides (about 3 minutes per teaching slide, 2 per talk slide), one idea
  per slide, 4–5 self-contained key phrases and a meaningful visual on nearly every teaching
  slide. Text is never shrunk below 12 pt to make it fit.
- Detailed speaker notes on every slide. An activity comes with instructions, timing, a sample
  answer and a debrief.
- Citations on the slide and a references slide, from a source ledger that maps each claim to
  its source.
- Optionally the same deck as a Claude Slides deck, when the client offers that output type.
- A short reply: slide count and timing, the defaults assumed, the source mode, gaps or added
  sources, what was verified (with the date), and anything that could not be reproduced exactly
  (font substitutes, simplified drawings).

## What it asks you

Before building, the skill asks up to ten short questions, skipping any the request already
answers:

1. **Your own material.** Always asked first. If you have files or links, it asks which source
   mode you want.
2. **The title slide and content.** An opening question, activities, presenter name and
   affiliation, and the heading style.
3. **Footer, logo and design.** Running footer, slide numbers, a logo and its position, and a
   template of your own (`.pptx` or `.potx`).

If a question is declined, or nobody can answer, it uses the defaults: no opening question, no
activities, no presenter details, title only, slide numbers only, no logo, the default design.
No activities, presenter details or logos are ever added unless you provided or approved them.

## Source modes

| Mode | Uses | Web search |
|---|---|---|
| `strict` | only your material and the links you gave | never; gaps are left out or marked |
| `extended` | your material first, then online research for gaps and current facts | yes, official sources first; conflicts with your material are flagged, not overridden |

With no material the mode is `extended`. See `references/research-and-citations.md`.

## How it works

1. Turns the request and answers into a brief and computes the slide count and per-slide
   minutes.
2. Prepares the environment (`scripts/setup_env.sh`) and the template, either the bundled one
   or a copy of yours inspected with `scripts/inspect_template.py`.
3. Reads every source and keeps a ledger, then plans one idea per slide using the 20 patterns
   in `references/slide-patterns.md`.
4. Writes a spec (`scripts/example_spec.py` is the starting point) and builds it with
   `scripts/build.py`.
5. Checks it: `scripts/check_deck.py` verifies notes, timing and leftover template text, then
   `scripts/render_preview.sh` renders the slides to images that are inspected for clipping,
   overlap and cramped areas. It rebuilds until the deck is clean.
6. Delivers the `.pptx`, and asks whether you want changes. A change is made to the affected
   slides only, checked with `scripts/diff_decks.py`, and delivered as `_v2`. If you edited the
   file yourself, your file is changed directly.

## Requirements

- Python 3 and `pip`, Node `npm`, LibreOffice (`soffice`) and poppler (`pdftoppm`) on the
  `PATH`.
- `bash scripts/setup_env.sh` installs the rest: `python-pptx`, Pillow, CairoSVG, lxml and
  Playwright, the default fonts (Montserrat, IBM Plex Sans and Mono, Source Serif 4) and the
  Lucide icons. It writes to `~/.fonts` and `~/.cache/brief-to-slides`.
- Web access, for `extended` mode and for installing the fonts and icons.

The skill is client-neutral. Where a client has an `AskUserQuestion` tool the intake questions
use it; elsewhere they are asked in plain text. The optional Slides deck output is specific to
Claude products.

## Files

```text
brief-to-slides/
├── SKILL.md              # workflow, inputs and non-negotiable rules
├── README.md             # this file
├── references/           # loaded only when a step needs them
│   ├── default-brief.md          # the brief applied when you give only three inputs
│   ├── intake-questions.md       # the questions, their options and answer mapping
│   ├── research-and-citations.md # strict and extended modes, the source ledger
│   ├── slide-patterns.md         # 20 slide patterns and when to use each
│   ├── design-system.md          # default theme: colours, type scale, chrome
│   ├── speaker-notes.md          # how notes are written
│   ├── build-notes.md            # layout fixes found while checking decks
│   ├── revisions.md              # targeted changes after delivery
│   └── slides-artifact.md        # the optional Claude Slides deck
├── assets/
│   ├── template.pptx             # a complete 22-slide example deck with notes
│   └── blank-template.pptx       # the same design with no slides: the default start
└── scripts/              # setup, build, check, render and diff tools
```

## Rules the skill keeps

- Notes in the Notes pane of every slide; timings sum exactly to the length; no leftover
  template slides, text, notes or hidden slides.
- No invented sources, statistics, quotes or screenshots. Invented teaching examples are
  disclosed in the speaker notes and in the reply, never labelled on the slides.
- In `strict` mode every factual claim traces to your material.
- No logos or brand marks unless you supply them.

## Installing

The skill ships in the `gaik-toolkit` agent plugin, so installing the plugin installs it; see
[the plugin README](../../README.md). To use it on its own, copy this directory into your
agent's skills directory.
