# Extraction Requirements — Meeting Record (MeetingRecord)

## Purpose

Extract a structured, evidence-cited meeting record from three combined sources for a
single meeting: the spoken meeting audio (transcribed), the agenda document (parsed),
and the participant list. The output helps a project team see what was decided, what
actions were assigned, and what remains unresolved — with every claim traceable back to
its source. Input language is English.

## Source precedence (critical)

- The **spoken meeting content** (transcript) is authoritative for what actually
  happened. The **agenda** only describes what was *planned* to be discussed.
- An agenda item must **never** be treated as a decision, action, or resolved issue by
  itself. Only extract a decision/action/resolution when the transcript shows it was
  actually discussed, decided, or assigned in the meeting.
- When the agenda and the transcript disagree (e.g. a different date, a topic listed but
  never discussed, a decision that contradicts the agenda's proposal), do **not** silently
  pick one — record it as an entry in `conflicts`, and let the value that ends up in the
  main record (e.g. `meeting_date`) follow the explicit spoken statement, not the agenda.
- If the transcript and agenda disagree and the transcript itself is ambiguous or silent,
  keep the field unset rather than guessing.

## Field-by-field instructions

- **meeting_id**: A stable identifier for this meeting instance. If no explicit ID is
  stated in either source, derive one from the meeting title and date; do not invent an ID
  format that isn't grounded in the material.
- **title**: The meeting title as stated in the agenda or transcript.
- **meeting_date**: The date the meeting was actually held, per the transcript if stated
  there; if the agenda and transcript give different dates, record the conflict (see
  `conflicts`) and prefer the transcript's explicit statement. Leave unset if neither
  source states it explicitly. Always format as ISO-8601 `YYYY-MM-DD`.
- **start_time** / **end_time**: As explicitly stated (agenda or transcript). Leave unset
  if not stated — do not infer from audio duration. Format as `HH:MM` (24-hour).
- **participants**: One entry per person confirmed to be part of the meeting, `{name,
  role}`. Use the supplied participant list to **normalize** names and roles heard in the
  transcript (the transcript may mishear or shorten a name — match it to the closest
  participant-list entry). Do not add a participant who appears only in the participant
  list but is never referenced as attending, unless the source materials otherwise confirm
  attendance.
- **topics**: One entry per agenda topic that was **actually discussed** in the meeting,
  `{title, discussion_summary}`. `discussion_summary` should be a concise, neutral summary
  of what was said, grounded only in the transcript. Do not create a topic entry for an
  agenda item that was never brought up in the meeting.
- **decisions**: One entry per decision **explicitly made** in the spoken meeting,
  `{decision_id, statement, citations}`. `decision_id` is a short stable slug (e.g.
  `decision_1`). `statement` must be a **complete, self-contained** restatement of the
  decision — include every condition, scope, or exclusion the speaker stated as part of it
  (e.g. both "only synthetic/anonymized data" and "no production data" if both were said),
  not just a partial paraphrase. Every decision must carry at least one citation into the
  audio (see citation format below).
- **action_items**: One entry per action assigned or agreed in the meeting, `{action_id,
  description, owner, due_date, uncertainty_reason, citations}`.
  - `owner` and `due_date` must be set **only** when explicitly stated in the transcript
    (owner normalized against the participant list). If either is not explicitly stated,
    set it to `null` and explain why in `uncertainty_reason` (e.g. `"no owner named in
    transcript"`, `"no due date mentioned"`).
  - Never infer an owner from who raised the topic, and never infer a due date from
    meeting cadence or agenda dates.
  - When a due date is stated (even informally, e.g. "by September 29th" with no year),
    normalize it to ISO-8601 `YYYY-MM-DD`, using the same year as `meeting_date` unless the
    transcript explicitly states a different year. Never invent a day/month that wasn't
    stated — only reformat what was said.
  - Every action item must carry at least one citation.
- **unresolved_issues**: One entry per topic or question raised in the meeting that was
  **not** resolved by the end of the discussion, `{description, citations}`. Every entry
  must carry at least one citation.
- **conflicts**: One entry per contradiction between the agenda and the transcript, or
  within the transcript itself (e.g. two different dates mentioned, an agenda item
  proposing one thing while the meeting decided another), `{description, citations}`.
  Cite both conflicting sources where possible (e.g. one audio citation and one agenda
  citation). Every entry must carry at least one citation.
- **review_status**: Always set to `"pending_review"` in the extracted output. This field
  is later changed by the human reviewer, not by extraction.

## Values that must never be invented

Do not invent, guess, or infer values that are not explicitly stated in a source,
including (but not limited to):
- an action's owner or due date,
- budget approval status,
- SSO / access / systems decisions,
- a meeting date, start time, or end time not explicitly stated.

If a fact is not explicitly supported by the transcript or agenda, leave the
corresponding field unset (`null`) rather than approximating it. This applies even if the
value seems "obvious" from context.

## Citation format (mandatory)

Every `decisions`, `action_items`, `unresolved_issues`, and `conflicts` entry must carry a
`citations` list with **at least one** citation. Each citation is a single pipe-delimited
string:

- **Audio source**: `file_name|start_timestamp|end_timestamp`, with timestamps in
  `HH:MM:SS` format (e.g. `meeting_2026-08-10.wav|00:12:05|00:12:41`).
- **Agenda source**: `file_name|page_number` (e.g. `agenda_2026-08-10.pdf|2`).

An entry may carry multiple citations (e.g. one audio citation plus one agenda citation
for a `conflicts` entry). Never fabricate a citation — only cite a location you can point
to in the actual source content.

## Output format policy

- Return exactly one JSON object matching the `MeetingRecord` schema — no extra
  commentary, no markdown fences.
- Empty lists (`topics`, `decisions`, `action_items`, `unresolved_issues`, `conflicts`) are
  valid when nothing qualifies — do not pad them with invented entries.
- `review_status` is always `"pending_review"` at extraction time.
