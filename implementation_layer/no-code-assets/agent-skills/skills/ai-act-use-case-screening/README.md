# ai-act-use-case-screening

An [Agent Skill](https://agentskills.io/specification) that gives a preliminary EU AI Act
screening of any AI use case, from the user's own description, documents and answers. It
works for a use case that is **planned** (an idea or something being built) and for one
**already in use** (a pilot or a system in regular use).

It is a **preliminary screening**, not legal advice. It tells the user which risk class their
use case falls in on the facts they gave, what they must do and by when, what they could
change, and what is still open.

For a pack made by the GAIK Solution Configuration Wizard, use
[`ai-act-screening`](../ai-act-screening) instead: it reads the wizard's blueprint and
artefacts directly.

## Use it when

- someone wants to know whether and how the EU AI Act applies to an AI system or idea;
- a team needs the risk class of a use case, with the reasons written down;
- an organisation wants an AI Act gap check of a system it already uses.

Example requests:

```text
We are thinking about using AI to screen job applications. Does the AI Act apply?
```

```text
Screen our customer-service chatbot against the AI Act. The vendor's product sheet is attached.
```

## How it works

1. **Start.** The user describes the use case in their own words and can attach documents
   (specification, product sheet, vendor documentation, DPIA). The skill asks whether it is an
   idea, being built, in a pilot or in regular use.
2. **Questions in batches.** At most five questions per turn, in plain language, skipping
   anything already answered. Batches cover purpose and affected people; data and
   interaction; role and supply; product and market context; for systems in use, the date
   they went live and the measures in place. Follow-up batches appear only when an answer
   points to a high-risk use, a possible prohibited practice or transparency duties. Most
   screenings take three to five turns.
3. **Screening.** Eight findings (scope, role, prohibited practice, product safety component,
   Annex III area, Art. 6(3) exception, transparency, general-purpose AI model) place the use
   case in one of the AI Act's four risk tiers: **unacceptable risk** (prohibited),
   **high-risk**, **limited risk** (transparency obligations), or **minimal or no risk**. When a
   deciding fact is unknown, no tier is assigned yet and the possible tiers are listed; when
   the Act does not apply at all, the report says so.
4. **Report.** Written to a screening folder and summarised in chat.

## Output

A folder `ai-act-screening-<short-name>/`:

| File | Content |
|---|---|
| `intake.json` | The user's description, the documents' ids and names, and every question asked with the answer, copied exactly |
| `documents/` | Plain-text copies of the documents the user gave |
| `screening.json` | The screening as data |
| `report.md` | The report for people, one to three pages, readable without any knowledge of the AI Act or of the data files |

The report contains:

- **Result**: risk tier, role, confidence, and the use that was screened.
- **Current gaps** (systems in use): required actions whose date has passed and that are
  missing or only partly in place.
- **What you must do**: required actions with their legal basis and dates; for systems in
  use, each with a status (in place, partly, missing, unknown).
- **Recommendations**: optional changes, kept apart from what is required.
- **Dates that affect you**: in force or upcoming.
- **Findings**: each with the user's words as evidence, the AI Act citation and the reasoning.
- **What would change the classification**, **open questions**, and **related rules** (GDPR,
  workplace rules).

## The check

```bash
python scripts/check_screening.py --dir <screening_folder>
python scripts/check_screening.py --dir <screening_folder> --hash     # intake fingerprint
python scripts/check_screening.py --dir <screening_folder> --status   # current | outdated | none
```

It fails when a finding lacks evidence, a citation or reasoning; a quote does not occur in the
description, answer or document it names, with the same case and punctuation; a citation is
not in the citable list; the class, flags, actions or timeline contradict the findings or the
dates; a required action of a system in use has no status; or the intake changed after the
screening. It also fails a report that still contains field names, internal codes or data file
names.

What it does not check: whether a quote supports the screening's reading, and what the user
actually said. The intake is recorded by the agent during the session, so the report says
that it rests on the answers as recorded. The legal reading needs a person.

## Files

| File | Content |
|---|---|
| `SKILL.md` | The workflow the agent follows |
| `references/question-bank.md` | The question batches, their triggers and which finding each answer feeds |
| `references/ai-act-reference.md` | Dated working summary of the AI Act as amended in 2026, including the rules for systems already in use, and the citable-provisions list |
| `references/output-format.md` | The intake and the screening JSON |
| `references/report-guide.md` | How to write the report: plain wording for every result, the template, and the terms to explain |
| `scripts/check_screening.py` | Checks the screening against the intake |

## Keeping it current

`references/ai-act-reference.md` has a `last_verified` date and marks recently changed points
with **verify**. It shares its legal content with the reference in `ai-act-screening`; update
both together and keep the same `last_verified` date.

## Needs

Python 3.10 or later, standard library only, and file access for the screening folder. Runs in
claude.ai with code execution enabled, Claude Code, and other agents that can run Python. The
skill sends nothing anywhere itself; it uses web access only to read a page the user names or
to check official sources when the reference is out of date.

Install the skill with the [gaik-toolkit plugin](../../README.md#installing).
