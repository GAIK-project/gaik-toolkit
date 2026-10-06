---
name: brief-to-slides
description: >-
  Builds a visual, editable PowerPoint (.pptx) deck with speaker-ready notes, exact
  timing, citations and a layout-checked design from a topic, an audience and a length,
  using only the user's own material (strict mode) or adding web research (extended
  mode). Use when the user asks for a presentation, slide deck, lecture, training session
  or talk, wants a brief, outline or source documents turned into slides, or needs speaker
  notes and per-slide timing for a deck. Also use to make targeted changes to a deck this
  skill produced.
compatibility: >-
  Needs Python 3, npm, LibreOffice and poppler to build the deck and render previews;
  scripts/setup_env.sh installs the rest. Intake questions use AskUserQuestion where the
  client has it and are asked in plain text otherwise.
---

# Brief to Slides

Builds a highly visual, editable .pptx (optionally also a Claude Slides deck) with
speaker-ready notes on every slide, exact timing, citations and a verified layout. It works
from a three-field request and fills everything else from a default brief distilled from a
complete teaching deck (`assets/template.pptx`).

## 1. Inputs

**Required** (ask one short question only if one is missing):
1. **Topic or title**
2. **Audience** (who, prior knowledge)
3. **Length**: minutes or number of slides

**Optional** (apply the default and state it in one line of the reply):

| Input | Default |
|---|---|
| Purpose / type (teaching, briefing, pitch) | Inferred; teaching for students or staff training |
| Goals | 3–5 outcomes you derive from topic + audience |
| Outline, per-slide timing, visual direction | Drafted from the default arc (references/default-brief.md §3) |
| Template (.pptx/.potx) | `assets/blank-template.pptx` + default theme (references/design-system.md) |
| Logo and its position, running footer, heading style | **Ask** (§1b). Defaults: no logo, slide numbers only, title only |
| Own data, files and source links | **Always ask** (§1b, Q1); uploads in any common format, links separated by commas or new lines |
| Source mode: `strict` or `extended` | Asked right after material arrives (Q2); no material → `extended` |
| Running example | Teaching: one invented case (disclosed in notes, never labelled on slides); talks: none |
| Opening question (title slide) | **Ask** (§1b). None if declined |
| Presenter name and affiliation (title slide) | **Ask** (§1b). Omitted if declined |
| Activities | **Ask** (§1b). None unless the user describes or approves them |
| Notes depth | Detailed, speaker-ready |
| Output | .pptx; also a Slides deck if asked or the session started from Slides |
| Language, phrases per slide, exclusions | Request language; 4–5 key phrases; none |

### 1a. Source mode (decide before planning)
- **Strict**: use only the user's data and sources (including links they gave). No web search.
  Claims not supported by them are left out or marked as gaps.
- **Extended**: the user's material comes first; online research fills gaps, adds evidence and
  checks that facts are current.

Decide it this way:
1. **Always ask first** whether the user has their own data, files or source links (Q1), unless
   the request already includes them. If yes, ask them to attach files (PDF, Word, PowerPoint,
   Excel, CSV, text/Markdown, JSON, HTML, images) and paste links separated by commas or one per
   line; collect them with `scripts/collect_sources.py`.
2. Material provided → the **next question** is the mode (Q2): "Only my material (strict)" /
   "My material + online sources (extended)". The user named a mode already → use it.
3. No material → **extended**; say so in one line.
4. Nobody can answer (unattended run): strict if material was attached, otherwise extended;
   say so at the top of the reply.

A template file, logo or outline alone is not source material. Rules per mode:
references/research-and-citations.md.

### 1b. Intake questions (before research or building)
Ask at most **10 questions** with AskUserQuestion, in this order, skipping anything the request
or attachments already answer. Exact wording, options, previews and answer mapping:
`references/intake-questions.md`.
1. **Own material** (Q1, always first) → if yes, upload step (files + links), then
   **search mode** (Q2: strict / extended).
2. **Content and title slide**: opening question, activities, presenter name/affiliation,
   heading style (title only vs section label + title).
3. **Footer, logo, design**: running footer and slide numbers, logo yes/no, design/template and
   output format; then logo position (top right, top left, bottom right, bottom left) if needed.

If the user declines, skips or nobody can answer: no opening question, no activities, no
presenter details, title only, slide numbers only, no logo, default design. State these choices
in the reply.

A detailed user brief always overrides these defaults. Read `references/default-brief.md`
first: it is the full brief applied when the user gives only the three required inputs.

## 2. Workflow (keep a task list)

1. **Brief.** Ask the intake questions (§1b). Turn the request and answers into a brief:
   required inputs + answers + chosen defaults. Compute the
   slide count (≈3 min per teaching slide, 2 per talk slide, 5–30 slides) and per-slide minutes
   that sum exactly to the length. References slides are extra and untimed.
2. **Environment.** `bash scripts/setup_env.sh` (fonts, icons, libraries, render tools).
3. **Template.**
   - None given: use `assets/blank-template.pptx` with the default THEME.
   - Given: copy it; run `python scripts/inspect_template.py T.pptx --render tmpl_preview`;
     look at the contact sheet; write a `THEME` override (layout name, colours, kicker/title/
     source/page-number boxes, title background, logos the user supplied) and map the palette
     roles in references/design-system.md to its colours/fonts. Install missing fonts.
4. **Sources.** Read all provided material first (every file in `sources.json`, every link;
   report any that fail) and keep a source ledger (claim → source →
   page/section/URL). *Strict:* no web search; list gaps. *Extended:* research online (official
   sources first) for gaps and anything time-sensitive; note check dates; flag conflicts with
   the user's material instead of overriding it (references/research-and-citations.md).
5. **Plan.** One idea per slide; pick a pattern per slide from references/slide-patterns.md
   (vary them); thread the running example; write the 4–5 key phrases per slide. Title slide =
   `cover()` only (title, subtitle, optional series label; question/presenter only if given).
   Put the intake answers for heading style, footer, slide numbers and logo into `THEME`
   (`show_kicker`, `footer_text`, `page_numbers`, `logo`); the renderers place them.
6. **Write the spec.** Copy `scripts/example_spec.py`; fill `SLIDES` (id, kind, kicker, title,
   els, minutes, notes, source), `TITLE`, `SECTIONS`, `THEME`. Use the DSL and helpers in
   `scripts/dsl.py`; size every text box with `text_h()`. Write notes per
   references/speaker-notes.md (activities need instructions, timing, sample answer, debrief).
7. **Build.** `python scripts/build.py spec.py --template T --out deck.pptx --preview preview.html`
8. **Check.** `python scripts/check_deck.py --pptx deck.pptx --minutes N --preview preview.html
   --forbid "<old template text>"` must print OK. Then
   `bash scripts/render_preview.sh deck.pptx out 72` and inspect `out/sheet.png` and each slide.
   Fix clipping, overlaps, cramped or empty areas, one-line labels that wrap; rebuild until
   clean (references/build-notes.md).
9. **Slides deck (optional).** references/slides-artifact.md.
10. **Deliver.** Send the .pptx. Reply in a few lines: slide count and timing, defaults you
    assumed, the source mode, gaps (strict) or added sources and conflicts (extended),
    facts verified (with date), and template elements not reproduced exactly
    (font substitutes, simplified drawings instead of screenshots, masters not carried into a
    Slides deck). Mention that example cases are invented.
11. **Ask for changes.** End the delivery by asking whether the user wants any changes
    (AskUserQuestion: "No, it's ready" / "Yes, I'll describe them"; not one of the 10 intake
    questions). If they describe changes, make **targeted** changes only: edit just the affected
    slides (or THEME for deck-wide items), keep every other slide as it was, keep notes, timing
    total and citations consistent, rebuild, run `check_deck.py`, look at the changed slides, run
    `scripts/diff_decks.py old.pptx new.pptx` to confirm nothing else changed, deliver as `_v2`
    with a `slide N: what changed` list, and ask again. If the user edited the .pptx themselves,
    change their file directly instead of rebuilding (references/revisions.md).

## 3. Non-negotiables
- Notes in the Notes pane of every slide; timings sum exactly; no leftover template slides,
  text, notes or hidden slides.
- A meaningful visual on nearly every teaching slide; 4–5 self-contained phrases; never shrink
  text below 12 pt or to fit: simplify and move detail to notes.
- No invented sources, statistics, quotes, availability or screenshots; sourced claims cited on
  the slide and in references.
- No label words on slides ("illustrative", "mock-up", "fictional", "synthetic data"): invented
  examples and simplified interface drawings are disclosed in the speaker notes and the reply.
- Title slide carries nothing beyond `cover()`: no illustrations, mock-ups, cards or icons.
- No activities, opening question or presenter details unless the user provided or approved them.
- Strict mode: every factual claim on slides and in notes traces to the user's material.
- No logos or brand marks unless the user supplies them. No section label above titles unless the
  user chose it. No generic robot imagery.

## Files
- `references/default-brief.md`: full default brief (deliverable, arc, design, notes, research, verification)
- `references/design-system.md`: default theme: palette roles, type scale, chrome, motifs
- `references/slide-patterns.md`: 20 patterns from the template deck, when to use, helpers
- `references/intake-questions.md`: the ≤10 intake questions, upload step, options, defaults, mapping
- `references/research-and-citations.md`: strict/extended source modes, ledger, citations
- `references/revisions.md`: asking for changes after delivery and making targeted edits
- `references/speaker-notes.md`, `references/build-notes.md`, `references/slides-artifact.md`
- `assets/template.pptx`: complete 22-slide example deck (60-min session) showing every pattern with notes
- `assets/blank-template.pptx`: same design, no slides: the default starting file
- `scripts/`: `setup_env.sh`, `collect_sources.py`, `inspect_template.py`, `dsl.py`, `render_pptx.py`, `render_html.py`, `build.py`, `check_deck.py`, `diff_decks.py`, `render_preview.sh`, `example_spec.py`
