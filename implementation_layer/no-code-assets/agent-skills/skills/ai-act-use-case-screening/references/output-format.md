# Output format

Three files in the screening folder. Write `intake.json` during the questions,
`screening.json` after them, and **report.md** last, from `screening.json`, following
`report-guide.md`.

## 1. `intake.json` — what the user said

```json
{
  "intake_version": "1.0",
  "use_case_name": "Applicant screening assistant",
  "mode": "existing",
  "lifecycle_stage": "production",
  "description": "We use an AI tool to read CVs for our open positions. It gives each applicant a match score and a short summary, and the recruiter looks at the top ten.",
  "documents": [
    {"id": "D1", "file": "documents/D1.txt", "original_name": "vendor-product-sheet.pdf"}
  ],
  "questions": [
    {"id": "Q1", "batch": "B", "question": "Does a person decide with the output as one input, or does the output become the decision unless someone objects?", "answer": "The recruiter only reads the top ten, so the others are never looked at."},
    {"id": "Q2", "batch": "D", "question": "Are you building it yourselves, buying a ready-made product, or offering it to others under your own name?", "answer": "We subscribe to it from a vendor."},
    {"id": "Q3", "batch": "F", "question": "When was it first put into use?", "answer": "March 2025."},
    {"id": "Q4", "batch": "F", "question": "Which of these are already in place: a person who reviews outputs, kept logs, accuracy testing, documentation, notices to users or staff, staff training?", "answer": "The recruiter reviews the shortlist. We have not told applicants or trained anyone."}
  ]
}
```

- `mode`: `planned` | `existing`. `lifecycle_stage`: `idea` | `development` (planned) or
  `pilot` | `production` (existing).
- `description`: the user's own words, copied exactly. Never a summary.
- `documents[].file`: path inside the screening folder of the plain-text copy.
- `questions`: every question asked, in order, with the answer copied exactly; `unknown`
  when skipped. `batch` is the question-bank letter. Corrections are new entries.

## 2. `screening.json` — the screening as data

```json
{
  "screening_version": "1.0",
  "reference_last_verified": "2026-11-16",
  "screened_on": "2026-11-16",
  "intake_sha256": "<output of check_screening.py --hash>",
  "summary": {
    "outcome": "classified",
    "risk_class": "high",
    "role": "deployer",
    "confidence": "medium",
    "mode": "existing",
    "lifecycle_stage": "production",
    "screened_use": "A subscribed CV-scoring tool used by the company's recruiters to rank applicants for open positions.",
    "one_line": "Ranks job applicants, which is an Annex III(4)(a) use; no exception applies.",
    "flags": {"art_6_3_exempt": false, "transparency_duties": false}
  },
  "findings": [
    {
      "id": "F5",
      "question": "Does its purpose fall in an Annex III area?",
      "status": "yes",
      "answer": "Yes. It analyses and ranks job applications.",
      "evidence": [
        {"source": "description", "locator": "description", "quote": "It gives each applicant a match score and a short summary, and the recruiter looks at the top ten."}
      ],
      "citations": [{"ref": "Annex III(4)(a)"}, {"ref": "Art. 6(2)"}],
      "reasoning": "Scoring applicants to decide whom the recruiter reads is analysing and filtering applications in recruitment.",
      "confidence": "high"
    }
  ],
  "actions": [
    {
      "type": "required",
      "action": "Inform applicants that a high-risk AI system is used in assessing their application.",
      "route": "organisation",
      "applies_to": "deployer",
      "applies_from": "2027-12-02",
      "citations": [{"ref": "Art. 26(11)"}],
      "based_on": ["F2", "F5"],
      "status": "missing",
      "status_evidence": [
        {"source": "answer", "locator": "Q4", "quote": "We have not told applicants or trained anyone."}
      ]
    },
    {
      "type": "recommended",
      "action": "Have the recruiter review a sample below the top ten each round.",
      "reason": "Keeps a person's judgement over who is excluded, which the deployer's oversight duty asks for.",
      "route": "system",
      "citations": [{"ref": "Art. 26(2)"}],
      "based_on": ["F5"]
    }
  ],
  "timeline": [
    {"date": "2025-02-02", "what": "AI literacy for staff using AI systems", "status": "in_force", "citations": [{"ref": "Art. 4"}]},
    {"date": "2027-12-02", "what": "High-risk duties for Annex III systems", "status": "upcoming", "citations": [{"ref": "Art. 6(2)"}]}
  ],
  "triggers": [],
  "open_questions": ["Whether the vendor documents the tool as high-risk and provides instructions for use."],
  "adjacent": [
    {"flag": "Automated ranking of applicants: check GDPR rules on decisions based solely on automated processing.", "citations": [{"instrument": "GDPR", "ref": "Art. 22"}]}
  ],
  "disclaimer": "Preliminary screening based on the user's description, documents and answers as recorded in this session. Not legal advice."
}
```

### Field rules

- `screened_on`: the date of the screening (ISO). Timeline statuses are judged against it.
- `intake_sha256`: printed by `check_screening.py --hash` just before writing. It marks the
  screening outdated when the intake or a document changes.
- `summary.outcome`: `classified` | `undetermined` | `not_in_scope`, by the rules in SKILL.md
  Step 3.
- `summary.risk_class`: one of the four AI Act tiers — `unacceptable` | `high` | `limited` |
  `minimal` — when the outcome is `classified`; `null` otherwise.
- With `undetermined`, add `summary.alternatives`: at least two
  `{"if": "...", "risk_class": "<tier>"}`, and confidence is not `high`.
- `summary.role`: `provider` | `deployer` | `both` | `unknown`. `unknown` when F2 is unknown.
- `summary.mode` and `summary.lifecycle_stage`: the same as in `intake.json`.
- `summary.screened_use`: one or two sentences on the use screened: who uses it, on whom,
  for what.
- `summary.flags`: `art_6_3_exempt` is true exactly when F5 and F6 are `yes`;
  `transparency_duties` exactly when F7 is `yes`.
- `findings`: all of F1–F8, in order, with the questions from SKILL.md Step 3. `status`:
  `yes` | `no` | `unknown` | `not_applicable` (only F6 when F5 is not `yes`, and F2–F8 when
  F1 is `no`). Each needs evidence, at least one AI Act citation, reasoning and `confidence`
  (`high` | `medium` | `low`).
- `evidence` (in findings, `status_evidence` and `adjacent`):

  | `source` | `locator` | `quote` |
  |---|---|---|
  | `description` | `description` | Words from the intake description. |
  | `answer` | A question id, e.g. `Q3` | Words from that recorded answer. |
  | `document` | A document id, e.g. `D1` | A passage from that document's text file. |

  Case and punctuation must match; only whitespace may differ. Quote whole sentences,
  including any negation. Keep quotes under about 40 words.
- `citations[].ref`: a line from the citable list at the end of `ai-act-reference.md`,
  written exactly as listed. `instrument` is `AI Act` (default) or `GDPR`; GDPR only in
  `adjacent`.
- `actions`: each with `type`, `action`, `route` (`system` | `organisation`) and `based_on`
  (finding ids).
  - `required`: also `applies_to` (`provider` | `deployer` | `both`), `applies_from` (ISO date
    from the reference) and at least one AI Act citation. **Existing** mode: also `status`
    (`in_place` | `partly` | `missing` | `unknown`) and `status_evidence` (at least one item,
    unless the status is `unknown`). **Planned** mode: no `status`.
  - `recommended`: also `reason`. No `applies_to`, `applies_from` or `status`. Citations are
    optional and show what the change relates to.
  - Required actions include an Art. 6(4) or Art. 49(2) duty when `art_6_3_exempt` is true,
    and the applicable Art. 50 duty when `transparency_duties` is true, unless the tier is
    `unacceptable` or the outcome is `not_in_scope`. The unacceptable tier has no required
    actions.
- `timeline`: items with `date` (ISO), `what`, `status` and at least one AI Act citation.
  `status` is `in_force` when the date is on or before `screened_on`, else `upcoming`.
- `triggers`: `{"change", "would_become" (a tier), "citations"}`.
- `open_questions`: plain strings.
- `adjacent`: `{"flag", "citations", "evidence" (optional)}`.

## 3. **report.md** — the report for people

Written from `screening.json` for readers who have never read the AI Act. Follow
`report-guide.md`: its rules, its wording for every data value, and its template. The report
contains no field names, codes or file names from the data.
