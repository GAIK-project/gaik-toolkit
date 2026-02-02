# Incident / Safety Observation Extraction Prompt (Audio Transcript → JSON)

This repository contains a **prompt-only** information extraction workflow for a manufacturing company’s **incident / safety observation reporting form**.

You can use the prompt in two ways:
1. **As a Custom GPT** (paste into Custom GPT Instructions), or  
2. **Directly in ChatGPT** (paste the prompt into a chat, then paste the transcript)

The prompt converts a spoken **audio transcript** into a **strict JSON object** containing only the fields required to fill a combined incident-report form.

---

## What this prompt does

### Input
A transcript of an audio recording made by a supervisor or employee describing:
- an incident
- a near miss
- a safety observation
- a safety-related initiative

### Output
A **single JSON object** with a fixed schema and field order, containing:
- form type and observation category (fixed options)
- reporter information (name, organization)
- event date/time and location details
- short event description and consequences
- near miss yes/no (fixed options)
- direct cause category (fixed options)
- corrective actions performed yes/no + short description
- whether a photo is mentioned (fixed option)

**No extra text is allowed** in the output. The response must be **valid JSON only**.

---

## Why the output is strictly structured

This prompt **forces a structured JSON output** to reduce errors and hallucinations, and to make the result easy to:
- paste into a web form
- store in a database
- validate automatically
- send to downstream workflows (RPA, integrations, analytics)

---

## Core guardrails (anti-hallucination)

The prompt enforces these rules:

- **Use only what is explicitly stated** in the transcript.
- If a field is missing, output **""** (empty string).
- Keep values extremely short (few keywords).
- Keep numbers as digits (do not rewrite numbers into words).
- If conflicting details exist, pick the most explicit/latest mention; otherwise output "".
- For **fixed-option fields**, output **only** an allowed option exactly as written; otherwise output "".
- Output must be **valid JSON only**, no explanations.

---

## Normalization rules

- **Event date/time**:
  - If date and time exist: `dd.mm.yyyy HH:MM`
  - If only date exists: `dd.mm.yyyy`
  - If year missing: `dd.mm` (zero-pad: `5.4 → 05.04`)

- **Yes/No fields**:
  - Output exactly `"Yes"` or `"No"` **only** if explicitly stated.
  - Otherwise output `""`.

- **Locations**:
  - Keep location values as short as possible (building + area + short clarification).

---

## Fields extracted

The prompt extracts the following fields (some with fixed allowed options):

### Fixed-option fields
- **Type of form**: `Safety observation` OR `Safety-related initiative`
- **Observation type**: `Safety` OR `Environmental protection`OR `Energy efficiency`
- **Positive safety observation**: `Yes` OR `No`
- **Reporter organization**: `Luvata Pori Oy` OR `Luvata Oy` OR `Other`
- **Summer employee**: `Yes` OR `No`
- **Near miss**: `Yes` OR `No`
- **Direct cause of the event**:
  - `5S`, `Technical failure`, `Protective devices on machines`, `Maintenance`, `Tools and devices`,
  `Work methods and instructions`, `Work guidance / induction / training`,
  `Following instructions and common standards`, `Information flow / lack of information flow`,
  `Working conditions`, `Weather conditions`, `Traffic`,
  `First-aid supplies (used / shortages)`, `PPE`, `Hurry / insufficient resources`,
  `Human / organizational factor`
- **Corrective actions performed**: `Yes` OR `No`
- **Photo mentioned**: `Yes` (only)

### Free-text fields (kept short)
- Reporter name
- Event date and time
- Building or site
- Detailed location
- Location clarification
- Event description
- Possible consequences
- Corrective actions description

---

## Output schema (strict JSON)

The prompt returns exactly this JSON object, with keys in this exact order:

```json
{
  "type_of_form_en": "",
  "observation_type_fi": "",
  "positive_safety_observation": "",
  "reporter_name": "",
  "reporter_organization": "",
  "summer_employee": "",
  "event_datetime": "",
  "building_or_site": "",
  "detailed_location": "",
  "location_clarification": "",
  "event_description": "",
  "near_miss": "",
  "possible_consequences": "",
  "direct_cause": "",
  "corrective_actions_performed": "",
  "corrective_actions_description": "",
  "photo_mentioned": ""
}
```
## How to use in ChatGPT (paste-in workflow)
Copy the prompt text from prompt.txt (or wherever you store it).

Paste it into a new ChatGPT conversation.

Paste the transcript after the prompt, for example:
```
TRANSCRIPT:
[Paste transcript here]
```
The model will return a single JSON object.

##  How to use as a Custom GPT
Create a new Custom GPT.

Paste the prompt into the Instructions field.

Save the Custom GPT.

For each run:

Paste the transcript into the chat.

Ask the GPT to extract the fields.

Tip: Keep the transcript in one message for best extraction consistency.

## Recommended repository structure

```
.
├── README.md
├── prompt.txt
└── data/
    ├── transcript_1.txt
    ├── transcript_2.txt
```

---

## Known limitations (prototype scope)

This is a prompt-only prototype. Common limitations include:

- If a transcript is vague (no explicit date/time, no explicit options), outputs will be empty strings by design.
- If the speaker describes a category indirectly (not matching an option word-for-word), the field will be blank.
- No external validation is performed (e.g., verifying building names or organization labels).

For production use, you would typically add:

- controlled input capture (form-based voice logging)
- post-validation rules
- human review UI for flagged fields

---

## Disclaimer

This prompt is intended for demo and prototyping. Always review extracted data before submitting official incident reports.