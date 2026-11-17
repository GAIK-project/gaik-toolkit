# ai-act-screening

A skill of the [GAIK Solution Configuration Wizard](../README.md), in the format of an
[Agent Skill](https://agentskills.io/specification), that screens a solution pack against the
EU AI Act and adds a brief, evidence-backed analysis to the pack. The wizard offers it after
Phase 12; it lives in the wizard folder because it only works on a wizard pack.

It is a **preliminary screening**, not legal advice. It tells a team which risk class their
use case falls in on the recorded facts, what they must do, what they could change, and what
is still open. It screens the **intended deployment** of the solution, not the proof of
concept, which is development work outside the Act.

## When it runs

The wizard offers it once, as an optional step after Phase 12, when the blueprint, PoC and
documentation are final:

1. **Offer.** "Would you like a preliminary EU AI Act screening of this solution?"
2. **Screen.** The skill explains the classification, the unresolved facts, the actions the
   Act requires, and optional recommendations, kept apart.
3. **Revise.** Changes to the solution go back through the wizard: requirements and blueprint
   first, then the affected workflow, documentation and PoC files are regenerated. Actions
   such as training or notices are done outside the solution and change nothing in the pack.
4. **Rerun.** Once the blueprint changes, the screening is marked outdated and the wizard
   offers to run it again.

**It proposes and never blocks.** Every proposal can be accepted, skipped or ignored, and the
wizard carries on either way. "Required" in the brief describes a duty in the Act, not a gate in
the wizard; the wizard does not enforce it.

A high-risk result does not by itself mean the requirements must change. It usually means
the intended use carries more duties.

You can also run it yourself on any pack, for example after the use case changes:

Example request:

```text
Use the ai-act-screening skill on the solution pack in <output_dir>.
```

## Input

| Input | Required | Used for |
|---|---|---|
| `use_case.blueprint.json` | Yes | Purpose, sector, users, human review, data handling, models, workflow |
| `workflow.bpmn` / `workflow.mmd` | No | Roles, approval gateways, external parties |
| `docs/genai_product_canvas.md`, `docs/technical_specification.md` | No | Purpose and limits in prose |
| `poc/schemas/output_schema.py`, `poc/prompts/extraction_requirements.md` | No | Which data about people is extracted |
| The wizard conversation | No | The user's own words; read when the skill runs in the wizard's session or a transcript is given |
| Up to six answers from the user | When missing | Facts the pack does not record: provider or deployer role, affected people, decision weight, sensitive data, audience, scope |

## Output

Two files written into the pack. The blueprint is not changed.

| File | Content |
|---|---|
| `ai_act_screening.json` | The screening as data: the questions asked and answers given, the screened deployment, summary with flags, eight findings, required and recommended actions, triggers, open questions, related rules, and the fingerprint of the blueprint it describes |
| `docs/ai_act_screening.md` | The same in plain language: a summary first, then the result, the eight questions with their evidence and reasoning, what you must do, and every term and provision explained. It is written by `scripts/render_brief.py` from the JSON |

Every finding carries three things:

- **evidence**: the file and location in the pack (a JSON Pointer into the blueprint and the
  value there, or a quote from a document, the conversation or a recorded screening answer);
- **citation**: the AI Act provision, from the reference's citable-provisions list;
- **reasoning**: how the evidence meets or does not meet the provision.

The eight findings, in order: in scope (F1), role (F2), prohibited practice (F3), product
safety component (F4), Annex III area (F5), Art. 6(3) exception (F6), transparency duties
(F7), general-purpose AI model (F8). The result is one of the four risk levels of the AI Act,
derived from them by fixed rules: **Unacceptable risk**, **High-risk**, **Limited risk
(transparency obligations)** or **Minimal or no risk** (which also covers a system the Act does
not cover). If a fact that decides the level is unknown, the screening says "Not decided yet",
which is not a level, and lists the possible levels and which answer leads to each. Two flags
show duties that apply whatever the level: an Annex III system exempt under Art. 6(3) keeps its
assessment and registration duties, and Art. 50 transparency duties can apply to any level,
including High-risk.

## Files

| File | Content |
|---|---|
| `SKILL.md` | The workflow the agent follows |
| `references/ai-act-reference.md` | Dated working summary of the AI Act as amended in 2026: scope, roles, prohibited practices, Annex III, Art. 6(3), Art. 50, duties by role, dates |
| `references/output-format.md` | The JSON structure and the brief's layout |
| `scripts/check_screening.py` | Checks the screening against the pack |
| `scripts/render_brief.py` | Writes the plain-language brief from the JSON and adds the glossary to it |
| `references/glossary.json` | The fixed plain-language explanations of the terms (levels, confidence, role, flags, the eight questions) |
| `references/provisions.json` | A plain-words line for every provision the checker accepts |

## The check

```bash
python scripts/check_screening.py --pack <wizard_output_dir> [--transcript <file>]
python scripts/check_screening.py --pack <wizard_output_dir> --hash     # fingerprint to record
python scripts/check_screening.py --pack <wizard_output_dir> --status   # current | outdated | unverified | none
```

Run it from this folder. It reports **errors**, which make it exit 1, and **warnings**, which
do not. An error means the screening is malformed, contradicts itself or its sources, or cites
something that does not exist: a finding without evidence, a citation or reasoning; a blueprint
quote that is not the value at its pointer; a quote whose words are not in its source; something
marked absent that is in the blueprint; a citation outside the citable list; or a class or flags
that do not follow from the findings. A warning is advice: a duty that may be missing, a date
not in the reference's table, a quote that differs in case or punctuation, or a screening that
is outdated because the blueprint changed (the fingerprint ignores the timestamp, change log
and saved screening answers). The wizard never reads either as a gate. Conversation quotes are
checked only when a transcript file is given; otherwise they are reported as unverified.
Python 3.10 or later, standard library only.

The check confirms that the quoted values and passages occur in their sources and that the
classification follows from the findings. It does not confirm that a quote supports the
screening's reading, or that the legal reading is right; that needs a person.

## Keeping it current

`references/ai-act-reference.md` has a `last_verified` date and marks recently changed
points with **verify**. Review it when the Commission publishes guidance (high-risk
classification guidance is due in 2027) or the Act is amended, and update the date.

## Needs

An agent that can read the pack's files. Nothing is sent anywhere by the skill itself; it
uses web access only to check official sources when the reference is out of date.
