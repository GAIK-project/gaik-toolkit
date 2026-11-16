# Output format

Two files, written into the wizard's output directory. Write the JSON first; the brief is a
rendering of it and must not say anything the JSON does not.

The checker reports **errors** (the screening is malformed, contradicts itself or its sources,
or cites something that does not exist) and **warnings** (advice). Neither stops the wizard.

## 1. `ai_act_screening.json`

```json
{
  "screening_version": "1.0",
  "reference_last_verified": "2026-11-16",
  "screened_at": "2026-11-16T13:40:00+02:00",
  "pack": {
    "blueprint_id": "incident_reporting_v1",
    "blueprint_status": "validated",
    "blueprint_sha256": "<output of check_screening.py --hash>",
    "files_read": ["use_case.blueprint.json", "workflow.bpmn", "docs/genai_product_canvas.md"],
    "files_absent": ["poc/schemas/output_schema.py"],
    "conversation_available": false
  },
  "questions": [
    {
      "id": "Q1",
      "question": "Will your organisation use this solution itself, or offer it to other organisations under its own name?",
      "answer": "We build it for our own factory and use it ourselves."
    },
    {
      "id": "Q2",
      "question": "Does its output feed a decision about an individual?",
      "answer": "The reports are used to fix hazards, never to assess the person reporting."
    }
  ],
  "summary": {
    "risk_class": "minimal",
    "role": "both",
    "confidence": "medium",
    "confidence_reason": "It relies on your answer that the reports are not used to assess the reporter.",
    "interpretation": "Minimal or no risk: the system documents incidents for a safety manager and is not used to evaluate the person reporting. The only duty is AI literacy for staff. The result would change if the reports were used to assess employees.",
    "one_line": "Documents safety incidents for a reviewer; no Annex III purpose on the recorded facts.",
    "intended_deployment": "Used in-house at one factory by employees to report incidents; a safety manager approves every report.",
    "flags": {
      "art_6_3_exempt": false,
      "transparency_duties": false
    }
  },
  "findings": [
    {
      "id": "F5",
      "question": "Does its intended purpose fall in an Annex III area?",
      "status": "no",
      "answer": "No. The system documents incidents; it does not evaluate or decide about workers.",
      "evidence": [
        {
          "source": "blueprint",
          "locator": "/use_case/description",
          "quote": "Convert spoken incident observations into structured incident reports for review and submission."
        },
        {
          "source": "screening_answer",
          "locator": "Q2",
          "quote": "The reports are used to fix hazards, never to assess the person reporting."
        }
      ],
      "citations": [
        {"ref": "Art. 6(2)", "note": "High-risk follows the intended purpose."},
        {"ref": "Annex III(4)(b)", "note": "Closest area: monitoring and evaluating workers."}
      ],
      "reasoning": "The stated purpose is recording events, and the user confirmed the output is not used to evaluate employees, so the Annex III(4)(b) purpose is not met.",
      "confidence": "medium"
    }
  ],
  "actions": [
    {
      "type": "required",
      "action": "Give staff who use the tool enough AI literacy for the task.",
      "route": "organisation",
      "applies_to": "both",
      "applies_from": "2025-02-02",
      "citations": [{"ref": "Art. 4"}],
      "based_on": ["F1", "F2"],
      "pack_support": "None recorded."
    },
    {
      "type": "recommended",
      "action": "Leave the reporter's name out of the extracted fields unless the safety process needs it.",
      "reason": "Keeps the report about the event and lowers the chance it is later used to assess the reporter.",
      "route": "wizard",
      "citations": [{"ref": "Annex III(4)(b)"}],
      "based_on": ["F5"]
    }
  ],
  "triggers": [
    {
      "change": "Using the severity or reporter fields to assess or discipline employees.",
      "would_become": "high_risk",
      "citations": [{"ref": "Annex III(4)(b)"}]
    }
  ],
  "open_questions": [
    "Retention policy is 'not_specified' in the blueprint."
  ],
  "adjacent": [
    {
      "flag": "Reports name injured persons: health data, a DPIA is likely needed.",
      "citations": [{"instrument": "GDPR", "ref": "Art. 9"}, {"instrument": "GDPR", "ref": "Art. 35"}],
      "evidence": [{"source": "blueprint", "locator": "/target_output_spec/fields", "quote": "injured_persons"}]
    }
  ],
  "disclaimer": "Preliminary screening based on the facts recorded in the solution pack and the user's answers. Not legal advice."
}
```

### Field rules

- `questions`: every question asked in Step 2, with the user's answer copied exactly
  (`"unknown"` when they could not answer). Ids `Q1`, `Q2`, … Use an empty list when no
  question was needed.
- `summary.risk_class`: one of the four risk levels of the Act, decided by the rules in
  SKILL.md Step 3: `unacceptable` (Unacceptable risk), `high` (High-risk), `limited` (Limited
  risk: transparency obligations), `minimal` (Minimal or no risk; also used when the Act does not
  cover the system). `not_decided` is not a level: it says that a fact that decides the level is
  unknown, and `summary.alternatives` then lists the possible levels.
- `summary.interpretation`: three to five plain sentences on what the overall result means for
  this use case. The brief shows it first, under "Summary".
- `summary.confidence_reason`: one plain sentence on why the confidence is what it is.
- `glossary`: the standard plain-language explanations of every term, added by
  `render_brief.py` from `references/glossary.json`. Do not write it by hand.
- `summary.flags`: `art_6_3_exempt` is true exactly when F5 and F6 are `yes`;
  `transparency_duties` is true exactly when F7 is `yes`. Both are always present.
- `summary.role`: `provider` | `deployer` | `both` | `unknown`.
- `confidence` (summary and findings): `high` | `medium` | `low`.
- `findings`: all of F1 to F8, in order, with the questions from SKILL.md Step 3.
  `status`: `yes` | `no` | `unknown` | `not_applicable`. `not_applicable` is allowed only for
  F6 when F5 is not `yes`, and for F2–F8 when F1 is `no`. A finding that applies
  (`yes`, `no`, `unknown`) needs at least one evidence item, at least one AI Act citation and a
  reasoning; a `not_applicable` finding needs only its answer and reasoning.
- `evidence[].source` and how to point at it:

  | `source` | `locator` | `quote` |
  |---|---|---|
  | `blueprint` | JSON Pointer (RFC 6901) into `use_case.blueprint.json`, e.g. `/governance/data_handling/contains_personal_data`, `/workflow/steps/5/type` | The whole value at that location: a string as it is, a number or boolean in JSON form (`true`, `0.0`). For a list of values, one whole element. Never point at an object; point at its field. |
  | `document` | Path relative to the pack, e.g. `docs/genai_product_canvas.md`, `workflow.bpmn`, `poc/schemas/output_schema.py`. Not the screening's own output files. | A passage copied from the file. Its words must occur in order; a copy that differs only in case or punctuation is accepted with a warning. |
  | `conversation` | Who said it and roughly where, e.g. `user, requirements round 2` | The user's words, copied the same way. Quote the user, not the wizard. |
  | `screening_answer` | The id of a recorded question, e.g. `Q1` | Words from that recorded answer, copied the same way. |
  | `absent` | The blueprint pointers you checked, comma-separated, e.g. `/business_spec/affected_persons` | Empty string. Use when the finding rests on something the pack does not record. |

  Quote whole sentences, including any negation, so the quote cannot mean more than its
  source. Keep them under about 40 words. For a long blueprint text value, cite the same
  text from a document instead.
- `citations[].ref`: a line from the citable-provisions list at the end of
  `ai-act-reference.md`, written exactly as listed (`Art. 6(3)`, `Annex III(4)(b)`).
  `instrument` is `AI Act` (the default) or `GDPR`. GDPR citations go only in `adjacent`.
- `pack.blueprint_sha256`: the fingerprint printed by `check_screening.py --hash` when the
  screening was written. It covers what the blueprint says and leaves out `metadata.last_updated_at`,
  `change_log` and `business_spec.ai_act_context`, which change without changing the solution. The
  checker and the wizard compare it with the current blueprint to tell whether the screening is
  outdated (a warning, never a stop). Leave it empty only when Python could not be run; the status
  is then `unverified` and the wizard says it cannot tell.
- `summary.intended_deployment`: one or two sentences on the production use that was
  screened (who uses it, on whom, for what). Not the PoC.
- `actions`: one list, every item with `type`, `action`, `route` and `based_on` (finding ids).
  - `type: "required"` — an AI Act duty for this role and class. Also `applies_to`
    (`provider` | `deployer` | `both`), `applies_from` (ISO date from the reference's date
    table), at least one AI Act citation, and optionally `pack_support`.
  - `type: "recommended"` — an optional change. Also `reason`. No `applies_to` or
    `applies_from`; citations are optional and show what the change relates to, not a duty.
  - `route`: `wizard` when doing it changes the solution, `organisation` when it is done
    outside the solution.
- `triggers[].would_become`: one of the four levels.
- When the result is `not_decided`, add `summary.alternatives`: at least two
  `{"if": "<answer to the open fact>", "risk_class": "<level>"}`, each one of the four levels.
  Summary confidence should not then be `high`.
- Required actions should include an Art. 6(4) or Art. 49(2) duty when `art_6_3_exempt` is
  true, and the applicable Art. 50 duty when `transparency_duties` is true, unless the level is
  `unacceptable`. A `high` result should list the duties for the user's role
  (deployer: Art. 26, 27, 86; provider: Art. 9-17, 43, 47-49, 72, 73; both: each side). An
  unacceptable-risk practice has no required actions; its recommended actions say what would have to
  change. The checker warns when these are missing; it does not fail.

## 2. `docs/ai_act_screening.md`

Do not write it by hand: `python scripts/render_brief.py --pack <output_dir>` renders it from the JSON
(and adds the glossary to the JSON). It says nothing the JSON does not, in plain language, for a
reader who does not know the Act. Sections, in order:

1. **Summary**: `summary.interpretation`, then the risk level, the number of required duties and
   suggestions, and the number of open questions.
2. **Result**: the risk level, role and confidence, each with its meaning, and the four levels of
   the Act with this result marked (or the possible levels, for "Not decided yet").
3. **What was screened**, and **Duties that apply whatever the risk level** (the Art. 6(3)
   exception and the Art. 50 transparency obligations, each explained).
4. **How the result was reached**: the eight questions in plain words, each with its answer, why,
   evidence and provision.
5. **What you must do** (duties in the Act; the wizard does not enforce them), **Suggestions
   (optional)**, **What would raise the risk level**, **Open questions**, **Related rules outside
   the AI Act**.
6. **Provisions cited** in plain words, and **Terms used**.

The standard explanations live in `references/glossary.json` and `references/provisions.json`.
Every provision the checker accepts has a plain-words line there; add one when you add a citable
provision.

### When the brief is outdated

When the blueprint changes after a screening, the wizard runs `render_brief.py --pack <output_dir>
--outdated`, which adds this line directly under the title, mentions it once to the user with an
offer to rerun, and leaves the rest as it was:

```markdown
> **Outdated.** The blueprint changed after this screening (<date>). Rerun the screening
> before relying on it.
```
