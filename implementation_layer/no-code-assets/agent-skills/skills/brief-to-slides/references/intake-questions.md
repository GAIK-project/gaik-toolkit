# Intake questions

Ask **at most 10 questions** in total, with AskUserQuestion (each call: 1–4 questions, 2–4
options per question, header ≤ 12 characters; the user can always type their own answer via
"Other"). Ask everything before research or building. Ask in the order below.

**Skip** any question the request or attachments already answer: files or links already given
→ skip Q1 and the upload step and go straight to Q2; a logo file attached → skip Q8, ask only
Q9; the user's template already carries a logo or footer → skip Q8/Q9 or Q7; the user said
"no activities" → skip Q4. If a required input (topic, audience, length) is missing, ask for it
first in a separate one-question call; it does not count toward the 10.

## Step 1: the user's own material (always first)
| # | Header | Question | Options |
|---|---|---|---|
| Q1 | Your material | Do you have your own data, files or sources (links) for this presentation? | No, research it for me · Yes, files · Yes, links · Yes, files and links |

**If yes → upload step (plain message, not a question; it does not count toward the 10).** Send:

> Please attach your files and paste your links in your next message.
> **Files:** PDF, Word (.docx), PowerPoint (.pptx), Excel (.xlsx/.xls), CSV/TSV, text or Markdown
> (.txt/.md), JSON, HTML, and images (.png/.jpg) such as charts or photos.
> **Links:** separate them with commas or put each on a new line.

Wait for the reply. Then run
`python scripts/collect_sources.py --links "<pasted text>" --files <attached file paths> --out sources.json`
to split and check the links (commas, new lines or spaces; duplicates removed; only http/https)
and to list the files by type. Read every file and open every link before planning (how to read
each format: references/research-and-citations.md). Tell the user in one line if a link could not
be opened or a file could not be read, and continue with the rest.
If the user said yes but sends nothing, treat it as "No" (extended mode) and say so.

## Step 2: source mode (immediately after the material arrives)
| # | Header | Question | Options |
|---|---|---|---|
| Q2 | Search mode | Should the deck use only your material, or your material plus online sources? *(only if files or links were provided)* | Only my material (strict) · My material + online sources (extended) |

No material → extended mode, no question.

## Step 3: content and title slide (one call)
| # | Header | Question | Options (first = recommended) |
|---|---|---|---|
| Q3 | Opening Q | Do you want an opening question for the audience on the title slide? | No opening question · Suggest one for me · *(Other: type your own)* |
| Q4 | Activities | Should the session include audience activities? | No activities · I'll describe them · Suggest some for me to approve |
| Q5 | Presenter | Should the title slide show the presenter's name and affiliation? | Leave them off · Add them *(type via Other: "Name, Affiliation")* |
| Q6 | Headings | How should slide headings look? Use previews. | Title only · Section label + title |

Previews for Q6 (show them in the option `preview`):
```
Title only                        Section label + title
┌──────────────────────────┐      ┌──────────────────────────┐
│ Choosing the Right Tool  │      │ CHOOSING TOOLS           │
│                          │      │ Choosing the Right Tool  │
│ [slide content]          │      │ [slide content]          │
└──────────────────────────┘      └──────────────────────────┘
```

## Step 4: footer, logo, design (one call)
| # | Header | Question | Options |
|---|---|---|---|
| Q7 | Footer | What should the footer of content slides show? | Slide numbers only · Presentation title + slide numbers · Nothing · *(Other: custom text, e.g. course name and date)* |
| Q8 | Logo | Should a logo appear on the slides? *(skip if a logo file is attached)* | No logo · Yes, I'll attach it |
| Q10 | Design | Which design and format? *(skip if a template is attached or the format is stated)* | Default design (.pptx) · My own template (I'll attach .pptx/.potx) · Default design + Claude Slides deck |

## Step 5: only if needed
| # | Header | Question | Options |
|---|---|---|---|
| Q9 | Logo place | Where should the logo go? *(only if a logo is attached or Q8 = yes; ask the user to attach it in the same message if it is not attached yet)* | Top right · Top left · Bottom right · Bottom left |

If a promised logo or template does not arrive, continue without it and say so in the reply.

## Mapping answers to the build
| Answer | Where it goes |
|---|---|
| Q1 + upload | `sources.json` (files, links); source ledger (references/research-and-citations.md) |
| Q2 | source mode (SKILL.md §1a) |
| Q3 | `cover(question=...)`; "Suggest one" → write one, show it in the reply |
| Q4 | activity slides only for described/approved activities (patterns 6, 15) |
| Q5 | `cover(presenter=..., affiliation=...)` |
| Q6 | `THEME['show_kicker']` = True for "Section label + title"; slides keep a short `kicker` value |
| Q7 | `THEME['page_numbers']`, `THEME['footer_text']` (presentation title, custom text or None) |
| Q8/Q9 | `THEME['logo'] = dict(path=..., position='top-right'|'top-left'|'bottom-right'|'bottom-left')`; also on the title slide (`logo_on_cover`) |
| Q10 | template file / default `assets/blank-template.pptx`; Slides deck per references/slides-artifact.md |

## When nobody answers (unattended run) or the user skips
Material: use only what was attached to the request (strict if any, otherwise extended). No
opening question, no activities, no presenter details, title only (no section label), slide
numbers only, no logo, default design (.pptx). State these choices in the reply.

## Not asked (inferred; mention in the reply only if relevant)
Running example (teaching: one invented case, disclosed in notes; talks: none unless the
material suggests one), language (from the request), goals, tone/purpose, notes depth (always
detailed), slide count (from the length), colours (from the template or default design).
