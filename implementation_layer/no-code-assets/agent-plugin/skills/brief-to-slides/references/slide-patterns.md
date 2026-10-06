# Slide patterns

The 20 teaching slides of `assets/template.pptx` are worked examples of reusable patterns.
Pick a pattern per slide from the purpose column, then build it with the DSL helpers named.
Open the example slide (render it with `scripts/render_preview.sh assets/template.pptx OUT`)
when you need exact proportions. `scripts/example_spec.py` shows code for patterns 1, 2, 3, 6, 19 (its activity slide shows the
pattern for when a user asks for one).

| # | Pattern | Use it to… | Structure | Helpers | Example slide |
|---|---|---|---|---|---|
| 1 | Cover | open the session | `cover()`: kicker (optional), serif title, subtitle, opening-question box ONLY if the user gave a question, presenter name + affiliation ONLY if given. No illustrations, cards or icons | `cover` | 1 |
| 2 | Recap + goals | link to earlier session, state outcomes | left tinted panel with 3 icon+text recap items; right numbered goals with accent bars | `ICON`, `BAR`, `text_h` | 2 |
| 3 | Staircase progression | show maturity/automation levels | 5 rising cards (tint gets darker), example line in each, "what you must check" chips below, banner | `R`, `ARW`, `chip`, `banner` | 3 |
| 4 | Annotated artefact | dissect a prompt, form, email, policy | cream card with labelled rows (label col + text), separated source chips; key phrases on the right | `KPS`, `chip` | 4 |
| 5 | Before / after | prove why a method matters | left: vague input → weak output + defect chips; right: specified input → structured table; banner with the lesson | `chip`, `ARW`, `table`, `banner` | 5 |
| 6 | Pair activity (only if requested) | practise | brief + source excerpts card left; 3–4 numbered task cards right; timing chips (work / debrief) | `R`, `E`, `chip` | 6, 16 |
| 7 | Three options + claim check | compare sources, then verify one claim | 3 icon cards on top; bottom: claim → original passage → verdict with arrows; key phrase | `card`, `ARW`, `KP` | 7 |
| 8 | Iteration loop with versions | show draft → inspect → change → review | numbered chip loop on top; version 1 drawing → change request → version 2 drawing | `chip`, `R`, bars | 8 |
| 9 | Decision matrix | choose a method/tool | table: need · method · effort chip · risk chip · example; banner rule of thumb | `table`, `chip`, `banner` | 9 |
| 10 | Feature matrix | compare features of one product | 4 feature columns × rows Helps with / Needs / Produces / You check; status band (what is changing) | `matrix` | 10, 12 |
| 11 | Capability chain | show how parts of one system hand work along | 5 header cards with icon; rows "what it adds / example step / you check"; arrows; availability band | `R`, `ICON`, `ARW` | 11 |
| 12 | Flow + permissions diagram | explain read vs write, approvals | actor → system node; blue read path to a source; orange write path through an approval gate; side key phrases | `LN`, `R`, `chip`, `KPS` | 13 |
| 13 | Spec card + contrast panels | design something reusable | left: spec card (6 labelled rows); right: two stacked panels contrasting temporary vs persistent | `R`, `T` | 14 |
| 14 | Anatomy (folder/code + parts) | show what a package/file contains | dark code panel (file tree, header), right list of parts as alternating chips, warning band | `T(font=M)`, `R` | 15 |
| 15 | Fill-in template (only if requested) | worksheet for an activity | brief panel + timing chips left; 5 labelled rows with prompt and dashed write-in line | `R`, `LN(dash)` | 16 |
| 16 | Definition + workflow + contrast | introduce a practice | quoted definition with bar; 5-step row with loop-back dashed connector; example card; prototype → dependable contrast | `step_row`, `LN`, `R` | 17 |
| 17 | Test runs | before/after evidence | two dark "terminal" panels (PASS/FAIL lines) with a targeted request between; checklist cards below | `T(font=M)`, `card` | 18 |
| 18 | Checklist cards | responsible use, criteria | 5 numbered cards with icon, title, question; navy responsibility banner | `numbered_cards`, `banner` | 19 |
| 19 | Takeaways (+ exit ticket if requested) | close | 3 numbered dark takeaway cards; 4 warm prompt boxes only when the user wants an exit ticket | `R`, `ICON`, `numbered_cards(dark=True)` | 20 |
| 20 | References | sources | Author (year). *Title*. Publisher. short-url (hyperlinked), 13–14 pt, split across slides when > ~10 entries; no disclaimer line on the slide | `ref`, `T` | 21–22 |

## Choosing patterns
- Vary patterns: do not use the same one on consecutive slides unless they form a series
  (e.g. three product matrices).
- Diagrams should show the real mechanism or comparison, not decoration.
- Every pattern keeps 4–5 key phrases; put explanations in notes.
- Reuse the running example inside the pattern (rows, cards, drawings) instead of generic text.
- Activities (patterns 6, 15) and exit tickets appear only when the user asked for them.
- Never write "illustrative", "mock-up", "fictional" or "synthetic" on a slide; disclose in notes.
