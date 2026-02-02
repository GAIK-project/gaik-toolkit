# Construction Site Diary Extraction Prompt (Audio Transcript → JSON)

This repository contains a **prompt-only** information extraction workflow for creating official **Daily Construction Site Diary** entries.

You can use the prompts in two ways:
1. **As a Custom GPT** (paste into Custom GPT Instructions), or
2. **Directly in ChatGPT** (paste the prompt into a chat, then paste the transcript)

The prompts convert a spoken **audio transcript** from a construction site supervisor into a **strict JSON object** containing all required fields for an official construction diary entry.

**Available in two languages:**
- English version: [English-prompt.txt](English-prompt.txt)
- Finnish version: [Finnish-prompt.txt](Finnish-prompt.txt)

---

## What this prompt does

### Input
A transcript of an audio recording made by a construction site supervisor describing:
- Daily work activities and progress
- Weather conditions
- Personnel resources
- Work phases (started, ongoing, completed, interrupted)
- Unusual events or deviations
- Inspections and observations
- Attachments (photos, documents)

### Output
A **single JSON object** with a fixed schema and field order, containing:
- Site/project identification and author
- Date, week number, and weather conditions
- Personnel resource breakdown
- Work activities and phases
- Events, deviations, and issues
- Inspections and requested extensions
- Supervisor notes and signatures
- Attachments information

**No extra text is allowed** in the output. The response must be **valid JSON only**.

---

## Why the output is strictly structured

This prompt **forces a structured JSON output** to reduce errors and hallucinations, and to make the result easy to:
- paste into an official diary form
- store in a database
- validate automatically
- send to downstream workflows (construction management systems, compliance reporting)
- archive for legal/regulatory purposes

---

## Core guardrails (anti-hallucination)

The prompt enforces these rules:

- **Use only what is explicitly stated** in the transcript.
- If a field is missing, output **""** (empty string).
  - Exception: "Day's Events (Unusual)" returns **"No events"** when no unusual/unplanned event is mentioned.
- Keep values extremely short (few keywords). No long sentences.
- Keep numbers as digits (do not rewrite numbers into words).
- If conflicting details exist, pick the most explicit/latest mention; otherwise output "".
- For **work phase fields**, output **only** an allowed work phase exactly as written; otherwise output "".
- Output must be **valid JSON only**, no explanations.

---

## Normalization rules

- **Date**:
  - If date with year: `dd.mm.yyyy`
  - If date without year: `dd.mm` (zero-pad: `20.5 → 20.05`)

- **Weather**:
  - If numeric metrics exist: keep compact (e.g., `"3 °C, 2 m/s, 78 %, Kp: -1.4 C"`)
  - If weather is described verbally: keep short keywords (e.g., `"cloudy, drizzle"`)

- **Resources - Personnel**:
  - **ALWAYS** output exactly in the format:
    `"Supervisors: X ppl, Workers: Y ppl, Subcontractors: Z ppl, Total: N ppl"`
  - If a subgroup count is not mentioned, use `0` for that subgroup.
  - Compute Total as X+Y+Z using the available numbers (or 0). Do not guess beyond stated counts.

- **Week Number**:
  - Return digits only (e.g., `"2"`) if explicitly stated; otherwise `""`.

- **Attachments**:
  - Extract counts and types if explicitly mentioned (e.g., `"4 photos, 1 email"`)
  - If type is mentioned without a count, return only the type (e.g., `"photos"`)
  - Otherwise `""`

---

## Fields extracted

The prompt extracts the following fields:

### Metadata fields
- Site / Project (Address or Subject)
- Author
- Date
- Week Number
- Attachments

### Conditions and resources
- Weather
- Resources - Personnel (structured format)

### Work tracking
- Today's Work (brief description)
- Day's Events (Unusual)
- Day's Deviations / Issues

### Work phase tracking (fixed-option fields)
**Work Phases Started / Ongoing / Completed / Interrupted** must use ONLY these allowed values:
- `Asbestos removal`
- `Interior demolition`
- `Structural demolition`
- `Sorting`
- `Site fencing`
- `Dust control`
- `Hauling soil/masses`
- `Hauling scrap`
- `Foundation demolition`
- `Pulverization`
- `Diamond cutting`
- `Protection works`
- `Metal and pipe demolition`
- `Oxy-fuel cutting`

**Mapping guardrail:**
- Add a work phase ONLY if the transcript clearly states that it started / was ongoing / ended / was interrupted.
- If the transcript describes work that does not clearly match an allowed label, return `""` for those work phase fields.
- Each field may contain a comma-separated list of allowed labels, a single label, or `""`.

### Supervisor observations
- Supervisor's Notes
- Supervisor's Remarks
- Inspections Performed
- Requested Extensions

### Signatures
- Supervisor's Signature
- Responsible Manager's Signature

---

## Output schema (strict JSON)

The prompt returns exactly this JSON object, with keys in this exact order:

```json
{
  "Site / Project (Address or Subject)": "",
  "Author": "",
  "Weather": "",
  "Date": "",
  "Resources - Personnel": "",
  "Week Number": "",
  "Today's Work": "",
  "Day's Events (Unusual)": "",
  "Attachments": "",
  "Supervisor's Notes": "",
  "Day's Deviations / Issues": "",
  "Work Phases Started": "",
  "Work Phases Ongoing": "",
  "Work Phases Completed": "",
  "Work Phases Interrupted": "",
  "Requested Extensions": "",
  "Inspections Performed": "",
  "Supervisor's Remarks": "",
  "Supervisor's Signature": "",
  "Responsible Manager's Signature": ""
}
```

---

## How to use in ChatGPT (paste-in workflow)

1. Copy the prompt text from [English-prompt.txt](English-prompt.txt) or [Finnish-prompt.txt](Finnish-prompt.txt)
2. Paste it into a new ChatGPT conversation
3. Paste the transcript after the prompt, for example:
   ```
   TRANSCRIPT:
   [Paste transcript here]
   ```
4. The model will return a single JSON object

---

## How to use as a Custom GPT

1. Create a new Custom GPT
2. Paste the prompt (English or Finnish version) into the Instructions field
3. Save the Custom GPT
4. For each run:
   - Paste the transcript into the chat
   - Ask the GPT to extract the diary fields

**Tip:** Keep the transcript in one message for best extraction consistency.

---

## Recommended repository structure

```
.
├── README.md
├── English-prompt.txt
├── Finnish-prompt.txt
└── Transcripts/
    ├── English.txt
    └── Finnish.txt
```

---

## Known limitations (prototype scope)

This is a prompt-only prototype. Common limitations include:

- If a transcript is vague (no explicit date/time, no explicit work phases), outputs will be empty strings by design.
- If the supervisor describes work that doesn't match the predefined work phase list, those fields will be blank.
- No external validation is performed (e.g., verifying site names, week numbers against dates).
- Work phase categorization depends on explicit verbal cues; implied activities may not be captured.

For production use, you would typically add:

- controlled input capture (standardized voice recording with prompts)
- post-validation rules (e.g., date/week consistency checks)
- human review UI for flagged or empty fields
- integration with construction management systems
- multi-language support beyond English/Finnish

---

## Disclaimer

This prompt is intended for demo and prototyping. Always review extracted data before submitting official construction diary entries. Official construction documentation may have legal and regulatory implications.
