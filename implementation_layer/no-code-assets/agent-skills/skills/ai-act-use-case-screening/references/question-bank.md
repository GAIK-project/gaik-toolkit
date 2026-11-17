# Question bank

Questions the skill asks, grouped in batches. Ask in plain language, without article numbers.
Each batch is one turn: at most five questions, as a numbered list.

**Skip any question the description, the documents or an earlier answer already settles.**
**Ask a branch batch only when its trigger is met.** A user who answers "don't know" has
answered: record `unknown` and move on.

Each question has a fact id. The fact ids are for you: they tell you which finding the
answer feeds. Do not show them to the user. Record every question you actually ask, with the
user's answer copied exactly, in `intake.json` as `Q1`, `Q2`, … in the order asked.

## Batch A — Start (always, first turn)

Ask only what the user has not already given.

| Fact | Question | Feeds |
|---|---|---|
| `description` | Describe the AI use case in your own words: what it does or will do, who uses it, what information it works on, and what happens with its output. You can also attach documents you already have (a specification, product sheet, vendor documentation, a DPIA). | All |
| `stage` | Is this an idea, something you are building, a pilot with real users, or a system already in regular use? | Mode, F1 |

`idea` and `development` → mode **planned**. `pilot` and `production` → mode **existing**.
A pilot with real users is real-world use, not development, and is screened as existing.

## Batch B — Purpose and people (always)

| Fact | Question | Feeds |
|---|---|---|
| `purpose` | What is the main purpose, and what is the output used for? | F5, F6 |
| `users` | Who uses it: your staff, your customers, the public, or someone else? | F7, F2 |
| `affected` | Whose information does it process, or who is affected by its output (employees, job applicants, students, customers, patients, citizens)? | F5 |
| `decisions` | Does the output feed a decision about a specific person? For example hiring, performance, pay, promotion, admission or grading, credit, insurance, benefits, access to a public service, or emergency response. | F5 |
| `weight` | If so, does a person decide with the output as one input, or does the output become the decision unless someone objects? | F6 |

## Batch C — Data and interaction (always)

| Fact | Question | Feeds |
|---|---|---|
| `data` | Does it handle health data, biometric data (face, fingerprints, voice used to recognise someone), data about children, or data on ethnicity, religion, politics, trade-union membership or sexual life? | F3, F5, adjacent |
| `biometric_analysis` | Does it analyse faces, voices (tone, pitch), body movement or behaviour, for example to recognise people, sort them into groups, or infer how they feel? | F3, F5 |
| `interaction` | Do people talk to it directly (chat, voice)? If so, are they told they are dealing with an AI? | F7 |
| `generated_content` | Does it generate text, images, audio or video that other people see? Is it published, and does a person edit or approve it first? | F7 |

## Batch D — Role and supply (always)

| Fact | Question | Feeds |
|---|---|---|
| `role` | Are you building it yourselves, buying or subscribing to a ready-made product, or offering it to other organisations under your own name? | F2 |
| `model` | Which AI model or vendor does it rely on (for example a GPT, Claude, Gemini or open model)? Do you fine-tune or retrain the model? | F8 |
| `rebrand` | If you bought it: have you put your own name on it, changed what it is used for, or modified it substantially? | F2 |

## Batch E — Context (always)

| Fact | Question | Feeds |
|---|---|---|
| `product` | Is it part of a physical or regulated product, or itself one: a medical device, machine, vehicle, toy, lift, radio equipment, or similar? | F4 |
| `market` | Is it used in the EU, offered to customers in the EU, or is its output used in the EU? | F1 |
| `organisation` | Is your organisation a public authority, a private organisation providing a public service, or a company? Is it a small or medium-sized enterprise? | Actions (Art. 27), penalties |

## Batch F — Systems already in use (mode existing only)

| Fact | Question | Feeds |
|---|---|---|
| `in_service_date` | When was it first put into use, or first offered to others? | Timeline, transition |
| `changes` | Has it changed significantly since then: a new purpose, new users, a different model, new data? | Transition |
| `measures` | Which of these are already in place: a person who reviews or approves outputs, kept logs, accuracy testing, written documentation, notices to users or staff, staff training on using AI? | Action status |

## Branch batches (only when the trigger is met)

### G — Possible high-risk use (trigger: `decisions`, `affected` or `purpose` points to an Annex III area)

| Fact | Question | Feeds |
|---|---|---|
| `annex_activity` | What exactly does it do in that decision: recommend, rank or score people, filter applications, evaluate performance, check eligibility, or only prepare or format information for a person? | F5 (subpoint) |
| `exception` | Which describes it best: a narrow procedural task; improving work a person has already completed; spotting patterns or deviations that a person then reviews; or preparing material for a person's assessment? Or none of these? | F6 |
| `profiling` | Does it evaluate or predict personal aspects of individuals, such as performance, reliability, behaviour, interests, health or location? | F6 (profiling override) |

### H — Possible prohibited practice (trigger: `biometric_analysis`, `purpose` or `affected` suggests one of the practices in the reference)

| Fact | Question | Feeds |
|---|---|---|
| `emotion_context` | Is the emotion analysis used on employees or students? Is it for a medical or safety reason? | F3 (Art. 5(1)(f)) |
| `manipulation` | Is it designed to influence people's decisions or behaviour in ways they would not notice, or to target people because of age, disability or financial situation? | F3 |
| `scoring` | Does it score people on their social behaviour or personal traits, and is that score used in an unrelated context? | F3 |
| `intimate_content` | Can it generate sexual or intimate images of real, identifiable people, or of children? What safeguards stop that? | F3 |

### I — Transparency details (trigger: `interaction` or `generated_content` is yes)

| Fact | Question | Feeds |
|---|---|---|
| `marking` | Are generated images, audio, video or text marked as AI-generated in a machine-readable way (for example watermarks or metadata)? | F7, actions |
| `deepfake` | Can it produce realistic images, audio or video of real people, places or events? | F7 |

## Stopping

Stop asking when every finding F1–F8 can be answered `yes`, `no` or `unknown` with evidence.
Do not ask more questions to raise confidence once the class can no longer change.
