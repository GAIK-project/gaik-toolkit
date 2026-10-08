# Speaker notes

Notes go in the PowerPoint Notes pane of every slide (and in the `<aside>` of a Slides deck,
max 4000 characters, so keep each under ~3900). Write for a presenter who did not build the
deck: plain language, full explanations, nothing that only repeats the slide.

## Format
Start with the allotted time so `check_deck.py` can sum it, then labelled blocks:

```
[3 min] SAY: <central point in plain language, 2–4 sentences>
VISUAL: <walk through the figure in reading order; explain every diagram element, term and interface drawing>
TERMS: <definitions, with an example each> (when new terms appear)
EXAMPLE: <what to say about the running example on this slide>
ASK: "<one question for the audience>" <typical answers / what to listen for>
TRANSITION: "<one sentence leading into the next slide>"
```
Where a slide uses the invented example case or a simplified interface drawing, add one line:
`NOTE FOR PRESENTER: <company/data> is an invented example; the panel is a simplified drawing, not a product screenshot.`
These disclosures live in the notes only, never as words on the slide.
Title slide notes cover the opening question only if the user gave one. Untimed slides (references) start with "References slide, not part of the timed session" and
say when facts were checked and what to re-check before reuse.

## Activities (only when the user asked for them; required parts)
```
[5 min: 2 min in pairs, 3 min sharing and debrief]
EXACT INSTRUCTIONS (read aloud): "<what to do, with whom, output, time>" Start a visible timer.
WHAT STUDENTS SHOULD NOTICE: <the deliberate difficulty in the task>
STRONG SAMPLE ANSWER: <a complete model answer>
DEBRIEF: <how many groups to hear; 3–4 points to make; common mistakes>
TRANSITION: ...
```

## Rules
- 1,500–3,000 characters for a typical teaching slide; at least 600 (checked).
- Explain product features (what they do, who has access) rather than relying on readers
  seeing interface text.
- Mention plan/region/age limits and dates when they affect the audience.
- Keep facts consistent with the slide and the references.
