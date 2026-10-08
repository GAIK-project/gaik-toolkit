# Default brief

Users usually give only a topic, an audience and a length. This file is the full brief the
agent applies by default. Anything the user does specify overrides the matching default.
It generalises a detailed brief that produced `assets/template.pptx` (a 60-minute, 20-slide
teaching session with notes and references; its activities were requested by that user).

## 1. Deliverable

- An **editable .pptx** with speaker notes inside the PowerPoint Notes pane on **every** slide
  (title, activities, conclusion and references included). Never deliver notes only as a
  separate document.
- Slide count when only minutes are given: about **3 minutes per teaching slide** for
  teaching/workshops (60 min → 20 slides), **2 minutes** for briefings or pitches. Clamp to
  5–30 slides. When only a slide count is given: assume 3 min per slide for teaching, 2 for talks.
- The timed slides add up **exactly** to the requested length. References slides follow the
  timed slides and are untimed.
- If the user also wants a Claude Slides deck, or started from the Slides output type, build
  the same spec as a Slides deck too (references/slides-artifact.md).

## 2. Template

- User supplied a .pptx/.potx: start from a **copy**, preserve its masters, layouts, logos,
  footer, typography and colours. Run `scripts/inspect_template.py` and write a THEME for it.
  Remove all its old slides, notes and hidden slides. Disclose any font substitutes.
- No template: use `assets/blank-template.pptx` with the default THEME (references/design-system.md).
  Add no logos unless the user supplies them.
- If a template element cannot be reproduced, recreate it as closely as possible and list it
  in the final reply.

## 3. Shape the content (infer when not given)

| Element | Default |
|---|---|
| Purpose | Inferred from the topic: teach, inform, persuade or decide. Teaching is the default for students/staff audiences. |
| Goals | 3–5 observable outcomes ("By the end, you can…") on slide 2. |
| Prior knowledge | Assume the audience knows the basics of the field but not advanced tools or terms; define new terms through examples. |
| Arc (teaching) | Title (+ opening question only if the user gave one) → link to prior knowledge + goals → big picture → core method(s) with a before/after → (activity, only if the user asked) → application/tools → risks or responsible use → recap → references. |
| Arc (talk/briefing) | Title + key message → context/problem → evidence → options compared → recommendation → risks → next steps → references. |
| Running example | One invented case revisited across slides to show progression (e.g. a small company and its documents). Never require real personal or customer data. Do not label it on slides; disclose it in the speaker notes. |
| Activities | **None by default.** Ask the user (intake, SKILL.md §1b). Build only activities the user describes or explicitly approves; timing comes out of the session length. |
| Title slide | Title, subtitle, optional kicker; opening question and presenter name/affiliation **only if the user gave them** (asked in intake). Nothing else: no illustrations, mock-ups or cards (`cover()` helper). |
| Product/tool content | Prefer methods that stay valid when product names and menus change; use current products only as concrete examples, with availability caveats. |
| Distinctions | When terms are easily confused, explain each with an example, not a definition alone, and do not imply identical meanings across vendors. |
| Language/spelling | Language of the request; consistent spelling throughout. |

For every tool, product or method example, state: **what task it helps with, what
information it needs, what it produces, and what the user must check.**

## 4. Slide design rules

- Highly visual and consistent with the template: a meaningful figure, process diagram,
  annotated example, comparison, matrix, simplified interface drawing or image on nearly every
  teaching content slide (not on the title slide).
  Choose from references/slide-patterns.md. Create original visuals; verify and attribute
  any external figure.
- About **4–5 concise, self-contained key phrases** per slide that still make sense when
  reviewed later. No paragraphs, no unexplained labels. Large diagrams, title and activity
  slides may have fewer.
- One main idea per slide, large readable type (body ≥ 13 pt, key phrases 17–20 pt), strong
  contrast, template spacing. **Never shrink text to fit**: simplify the slide and move detail
  to the notes.
- No generic AI-robot images, decorative icon grids, or screenshots too small to read.
- Interfaces you cannot capture are drawn as clearly simplified diagrams (generic shapes, no
  real product logos), never imitating or presented as screenshots.
- **No label words on slides**: do not write "illustrative", "mock-up", "fictional",
  "synthetic data" or similar on slides (references slides included). Put such disclosures in
  the speaker notes (and in the delivery reply).

## 5. Speaker notes

Substantial, speaker-ready, sufficient to deliver the session without reconstructing the
explanations. Format and required parts: references/speaker-notes.md.

## 6. Sources, research and citations

First ask whether the user has their own data, files or source links (intake Q1) and collect
them (upload step); then ask the source mode (Q2): **strict** = only the user's material;
**extended** = the user's material first, plus online research. No material → extended.
In extended mode, check time-sensitive facts
(features, plans, prices, rules, dates, names) in official sources immediately before building.
In both modes cite on the slide and list full sources on references slides. Never invent
sources, statistics, quotes, feature availability or screenshots.
Details: references/research-and-citations.md.

## 7. Final verification (before delivery)

- Design matches the template (fonts, sizes, layouts, footer, citation style).
- Every slide rendered and inspected; no clipped text, overlaps or off-canvas elements.
- Timed slides sum exactly to the requested length.
- Every slide has detailed notes; no leftover template text, notes or hidden slides.
- Activities appear only if the user asked for them, and then contain instructions, timing,
  a sample answer and debrief points.
- Source mode respected (strict: every claim traceable to the user's material; extended:
  added sources marked and dated). Product names and availability verified with dates; invented examples disclosed in the notes, not labelled on slides; every sourced
  claim and external visual cited.
- Reply briefly lists any template elements not reproduced exactly and any font substitutes.
