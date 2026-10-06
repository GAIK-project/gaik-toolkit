# Review and targeted changes

## Ask after every delivery
When the deck (and any Slides deck) has been delivered, end the reply by asking whether the user
wants changes. Use AskUserQuestion when available (this is not one of the 10 intake questions):

| Header | Question | Options |
|---|---|---|
| Changes | Would you like any changes to the presentation? | No, it's ready · Yes, I'll describe them |

Describing changes in free text (via "Other" or a normal message) is always fine. Without
AskUserQuestion, ask the same in one sentence. Repeat after each revision until the user is done.

## Make targeted changes, not a rebuild
1. **Pin down the request.** List each change as `slide N (id): what changes`. If a request is
   ambiguous ("make it better", "shorter"), ask one short question before editing; otherwise
   start.
2. **Find the right source of truth.**
   - The user did not edit the file: edit only the affected slide entries in the spec (or THEME for
     deck-wide items such as footer, logo, heading style), then rebuild.
   - The user edited the .pptx themselves (they send it back, or say so): do NOT rebuild from the
     spec, which would erase their edits. Change only the named shapes/notes in their file with
     python-pptx, keeping everything else byte-identical where possible.
3. **Change only what was asked.** Keep slide ids, order, wording, timing and notes of every
   other slide. Do not "improve" untouched slides.
4. **Keep the deck consistent with the change**:
   - Text changed → update that slide's speaker notes so they still match.
   - Slide added/removed/re-timed → re-balance minutes so the timed total still equals the
     requested length (say which slides absorbed the difference); renumbering is automatic.
   - New facts → follow the current source mode (strict: only the user's material; extended:
     verify and cite); update source line, ledger and references slides.
   - Deck-wide change (logo, footer, heading style, colours, template) → THEME/template only.
5. **Verify.** Rebuild, run `check_deck.py` (must print OK), render, and look at every changed
   slide (and its neighbours if layout or numbering moved). Run
   `python scripts/diff_decks.py old.pptx new.pptx` to confirm that only the intended slides
   changed; if others changed, fix that before delivering.
6. **Deliver.** Send the new file (same name with `_v2`, `_v3` …). Reply with a short list:
   `slide N: what changed`, anything not done and why. Then ask again whether further changes
   are wanted.
