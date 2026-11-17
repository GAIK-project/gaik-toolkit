# Writing the report

**report.md** is for people who have never read the AI Act: a manager, a product owner, a
lawyer outside the team. It must be understandable on its own, without `screening.json`,
this skill, or the conversation.

## Rules

1. **No internal names.** Never write a field name, value code, finding or question id, or
   file name from the data: no `risk_class`, `art_6_3_exempt`, `transparency_duties`,
   `in_place`, `not_applicable`, `F5`, `Q3`, `D1`, `intake.json`, and no backticks. Use the
   wording in the tables below. `check_screening.py` fails a report that contains them.
2. **Explain every legal reference where it appears.** After an article or annex, say in a
   few words what it requires or covers, taken from `ai-act-reference.md`: "Article 26(11),
   which requires users of high-risk systems to tell the people affected". Write "Article",
   not "Art.".
3. **Explain every term on first use**, and list the terms the report uses in "Terms used in
   this report" at the end. Only the terms that appear.
4. **Say what each result means for the reader**, not only what it is: "High-risk. This means
   …", "Missing. This duty applies from 2 December 2027 and is not yet in place."
5. **Name sources in words**: "your description", "your answer to the question '…'", the
   document's original name.
6. **Plain language, short sentences, the user's language.** Quotes stay in their original
   language.
7. The report says nothing that `screening.json` does not.

## Wording for data values

**Risk tiers** — always show all four, and mark the one that applies:

| Value | Label | What it means for the reader |
|---|---|---|
| `unacceptable` | Unacceptable risk (prohibited) | The AI Act bans this practice. It may not be put on the market or used in the EU as described. |
| `high` | High-risk | Allowed, but with strict requirements: risk management, documentation, human oversight, logging, accuracy, and information for the people affected. |
| `limited` | Limited risk (transparency obligations) | Allowed. People must be told when they deal with an AI system or with AI-generated content. |
| `minimal` | Minimal or no risk | Allowed with no requirements specific to this system, beyond giving staff who use AI enough knowledge to use it well (AI literacy). |

**No tier yet**:

| Value | Label | Explanation to give |
|---|---|---|
| `undetermined` | Not yet determined | Name the possible tiers and, for each, the fact that would lead to it. Say which question the user should answer to settle it. |
| `not_in_scope` | Outside the AI Act | Say why (for example: not an AI system, not used in the EU, purely personal use) and that the AI Act places no duties on it. |

**Role**:

| Value | Label | Explanation |
|---|---|---|
| `provider` | Provider | You develop the AI system, or have it developed, and offer it or put it into use under your own name. Providers carry most of the duties. |
| `deployer` | Deployer (user) | You use an AI system made by someone else in your work. Deployers have fewer duties, mainly about how the system is used. |
| `both` | Provider and deployer | You build the system and use it yourselves, so both sets of duties apply. |
| `unknown` | Not yet known | Say which answer would settle it. |

**Confidence**:

| Value | Label | Explanation |
|---|---|---|
| `high` | High | Every fact the result rests on comes from your own words or documents. |
| `medium` | Medium | One fact rests on an assumption you have not confirmed. Name it. |
| `low` | Low | A key fact is unknown. Name it. |

**Status of a required action** (systems already in use):

| Value | Label | Explanation |
|---|---|---|
| `in_place` | In place | You said, or a document shows, that this is done. This is your report, not a verified audit. |
| `partly` | Partly in place | Say what is missing. |
| `missing` | Missing | Not in place. If its date has passed, it is a current gap. |
| `unknown` | Not known | You could not say. Treat it as something to check. |

**Who acts** (route):

| Value | Label |
|---|---|
| `system` | A change to the AI system or to how it is used |
| `organisation` | Something your organisation does around the system (training, notices, registration, policy) |

**Dates**: "In force since 2 February 2025" or "Applies from 2 December 2027 (in 13 months)".

**Finding statuses**: `yes` → "Yes", `no` → "No", `unknown` → "Not known yet", and
`not_applicable` → "Does not apply, because …" with the reason.

**The flags** are never shown as flags. Write them as sentences in "Duties that apply
whatever the tier":

- Exception from high-risk (F5 and F6 both yes): "Your use case is in an area the AI Act lists
  as high-risk, but an exception applies because <reason>. It is therefore not high-risk. A
  provider relying on this exception must still document why and register the system in the
  EU database (Article 6(4) and Article 49(2))."
- Transparency (F7 yes): "Because <people talk to the system / it generates content that
  people see>, people must be told <what>, (Article 50(<n>)). This applies whatever the tier."

## The eight questions, in plain words

Use these headings in "How we reached this result", never the ids F1–F8:

| Id | Plain question |
|---|---|
| F1 | Does the AI Act apply to this system? |
| F2 | What is your role: do you provide the system or use it? |
| F3 | Does it do anything the AI Act bans? |
| F4 | Is it part of, or itself, a product covered by EU product-safety law, such as a medical device or machine? |
| F5 | Is it used in one of the areas the AI Act lists as high-risk? |
| F6 | Does an exception take it out of the high-risk tier? |
| F7 | Must people be told they are dealing with AI, or with AI-generated content? |
| F8 | Which general-purpose AI model does it use, and do you change that model? |

## Template

Headings in this order, translated into the user's language. Leave out a section that would
be empty, except "In short", "The result" and "How we reached this result".

```markdown
# EU AI Act screening: <use case name>

> **About this report.** A preliminary screening of <use case name> against the EU AI Act
> (Regulation (EU) 2024/1689, as amended in 2026). It is based only on the description,
> documents and answers you gave on <date>, as recorded during the screening, and on a
> summary of the law checked on <reference date>. It is not legal advice and does not
> confirm compliance.

## In short

<Three to five sentences: the tier and what it means for this use case; the most important
thing to do and by when; the biggest open question, if any.>

## The result

**What was assessed:** <the use: who uses it, on whom, for what>. <Planned: "This screening
covers the intended use once the system is running. Building and testing it is not covered
by the AI Act." Existing: "This screening covers how the system is used today.">

**Risk tier:** <label>. <What it means, from the table.>

| AI Act risk tier | What it means | This use case |
|---|---|---|
| Unacceptable risk (prohibited) | … | |
| High-risk | … | ✔ |
| Limited risk (transparency obligations) | … | |
| Minimal or no risk | … | |

**Your role:** <label>. <Explanation.>

**How certain this is:** <label>. <Explanation, naming the fact it hinges on.>

## Duties that apply whatever the tier

<Only when the exception or transparency sentence applies.>

## Current gaps

<Systems in use only: duties already in force that are missing or partly in place.>

| What is missing | Why it is required | Required since |
|---|---|---|

## What you must do

| What to do | Why it is required | From | Who acts | Status |
|---|---|---|---|---|
| Tell applicants that an AI system helps assess their application. | Article 26(11): users of a high-risk system must inform the people it makes or helps make decisions about. | Applies from 2 December 2027 (in 13 months) | Your organisation | Missing |

<The Status column only for systems already in use.>

## Recommendations (optional)

- **<What to do>.** <Why it helps.> These are suggestions, not legal requirements.

## Dates that affect you

| Date | What applies | Status |
|---|---|---|

## How we reached this result

### <Plain question>

**Answer:** <Yes / No / Not known yet / Does not apply, because …>. <Reasoning, in plain
words.>

**Based on:** <source in words>: "<quote>"

**Legal basis:** <Article or annex, and what it says in a few words.>

<Repeat for all eight questions.>

## What would change the result

- If <change>, the use case would become <tier>, because <reason>.

## Open questions

- <What is not known, and why it matters.>

## Related rules to check

- <Other law the facts point to, for example the GDPR, with one line on why.>

## Terms used in this report

- **<Term>**: <one-sentence explanation>.
```

## Terms to explain when they appear

- **AI system**: software that works with some autonomy and infers from its input how to
  produce outputs such as predictions, content, recommendations or decisions.
- **Provider / deployer**: see the role table.
- **High-risk areas (Annex III)**: the uses the AI Act lists as high-risk, such as
  recruitment and managing workers, education, credit, insurance, access to public services
  and law enforcement.
- **Exception from high-risk (Article 6(3))**: a system in a high-risk area that only does a
  narrow task, improves work a person has already done, flags patterns for a person to
  review, or prepares material for a person's assessment, and does not profile people.
- **Profiling**: automatically evaluating personal aspects of a person, such as performance,
  reliability, behaviour, interests or health.
- **General-purpose AI model**: a model that can do many different tasks, such as the large
  language models behind GPT, Claude or Gemini.
- **Transparency obligations (Article 50)**: duties to tell people they are dealing with AI,
  or that content was generated or manipulated by AI.
- **AI literacy (Article 4)**: measures to help staff who use AI systems understand them well
  enough to use them properly.
- **Placing on the market / putting into service**: first offering a system to others in the
  EU / first using it for its purpose, including for your own use.
- **Article 26(11)**: Article 26, paragraph 11. The AI Act is divided into articles and
  annexes; numbers in brackets are paragraphs, letters are points.
