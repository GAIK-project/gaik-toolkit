# Extraction Requirements — MeetingRecord

## Purpose

Produce a single structured `MeetingRecord` JSON object from three inputs describing one
project meeting:

1. **Meeting transcript** — a timestamped transcript of the spoken meeting audio
   (segments carry `start_timestamp`/`end_timestamp` in `HH:MM:SS`).
2. **Agenda document text** — the pre-meeting agenda, parsed with page markers
   (`=== PAGE N ===`). The agenda records *proposals and open questions prepared before
   the meeting*. It is **not** an approved decision record.
3. **Participant list** — a JSON list of `{name, role}` (optionally with a meeting
   responsibility) for everyone expected at the meeting.

The output will be reviewed and approved by a human (the project manager) before
distribution — the record must be trustworthy enough to review efficiently, which means
every claim must be traceable to its source.

## Core evidence rule

**The spoken meeting is authoritative. The agenda is context only.**

- Only record something as a `decision` if it was **explicitly and spokenly confirmed**
  in the meeting transcript. An agenda item that merely proposes something (e.g. a
  proposed date, a proposed budget ceiling) must **not** be copied into `decisions`
  unless the transcript confirms it happened that way.
- When the agenda and the spoken meeting **disagree** (e.g. the agenda proposes one
  launch date but the meeting explicitly decides a different one), do **not** silently
  prefer one or merge them. Instead:
  - Follow the **spoken decision** for the actual `decisions` / `topics` content.
  - Add an entry to `conflicts` describing the disagreement, citing **both** sources
    (the agenda page and the audio timestamp range).
- Never invent, infer, or "fill in" a fact that is not explicitly stated anywhere in the
  provided material — not an owner, not a due date, not a budget approval, not a
  technical decision. If the meeting explicitly says something is *not* decided or *not*
  agreed, it must appear in `unresolved_issues`, not in `decisions` or `action_items`.

## Field-by-field guidance

- **meeting_id / title / meeting_date / start_time / end_time**: read directly from the
  meeting metadata available in the transcript/agenda (opening/closing remarks usually
  state the date and closing time explicitly).
- **participants**: use the supplied participant list (`name`, `role`) as the
  authoritative source of names/roles. Do not add participants who are not on the list;
  do not drop participants who are confirmed present in the transcript.
- **topics**: one entry per agenda/discussion topic actually covered in the meeting, with
  a concise `discussion_summary` of what was actually said (not the agenda's proposed
  framing).
- **decisions**: one entry per explicit, spoken decision. `statement` is a clear,
  self-contained description of what was decided. Every decision needs at least one
  `citations` entry pointing at the audio segment where it was stated.
- **action_items**: concrete follow-up tasks. Set `owner` and `due_date` **only** when a
  name and a date/deadline were explicitly stated together with the action. If either is
  missing or ambiguous, set it to `null` and explain why in `uncertainty_reason` (e.g.
  `"No owner or exact due date was agreed."`). Do not guess a "most likely" owner from
  role or context.
- **unresolved_issues**: anything the meeting explicitly leaves open, pending, or
  deferred to another forum (e.g. "pending finance confirmation", "remains with the
  architecture board"). Must have at least one citation.
- **conflicts**: agenda-vs-meeting disagreements only (see Core evidence rule above).
  Cite both the agenda page and the audio segment.
- **review_status**: always set to the fixed literal `"pending_review"` in this PoC's
  output — the actual approve/reject decision happens outside the pipeline.

## Citation format (strict)

Every `decisions`, `action_items`, `unresolved_issues`, and `conflicts` entry must carry
at least one citation string in its `citations` list. Citations are **single
pipe-delimited strings**, not objects:

- Audio evidence: `"<file_name>|<start_timestamp>|<end_timestamp>"`, timestamps in
  `HH:MM:SS` (e.g. `"project_nimbus_meeting.wav|00:01:56|00:02:08"`).
- Agenda evidence: `"<file_name>|<page_number>"` (e.g. `"project_nimbus_agenda.pdf|2"`).

Use the exact source file names as given in the input bundle. An item may carry several
citations (e.g. a `conflicts` entry typically cites both the agenda and the audio).

## What must NOT be asserted

Do not state or imply any of the following unless the transcript explicitly says it
happened:

- A specific budget figure or ceiling was **approved** (a figure being *mentioned* as
  proposed/pending is not an approval).
- A specific technical approach (e.g. an SSO/authentication approach) was **selected**,
  when the transcript says it remains with another body/board.
- A named owner or exact due date for an action that the transcript explicitly leaves
  open.
- The agenda's proposed date/scope as the actual outcome, when the meeting explicitly
  changed it.

When in doubt, prefer `null` + `uncertainty_reason`, or an `unresolved_issues`/
`conflicts` entry, over asserting a fact.
