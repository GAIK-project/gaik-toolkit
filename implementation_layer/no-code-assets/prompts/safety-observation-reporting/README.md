# Safety Observation Reporting Extraction Prompt (Audio Transcript → JSON)

This folder contains a **prompt-only** information extraction workflow for converting spoken or written safety observations — near misses, incidents, and deviations — into structured safety report records.

You can use the prompt in two ways:
1. **As a Custom GPT** (paste into Custom GPT Instructions), or
2. **Directly in ChatGPT, Claude.ai, or Gemini** (paste the prompt, then paste the transcript)

The prompt converts a spoken audio transcript (or typed text) into a **strict JSON object** containing all 13 required safety observation fields.

---

## What this prompt does

### Input
A transcript of an audio recording or written note describing:
- A safety observation, near miss, or deviation
- The location and date of the event
- Contributing factors
- Immediate actions taken
- Suggestions for prevention

### Output
A **single JSON object** with a fixed 13-field schema, including:
- Incident type (near miss / safety observation / deviation)
- Incident category (equipment, quality, safety, etc.)
- Date, employer, reporter, and employee type
- Project identifier
- Event description, contributing factors, immediate actions
- Action taker and date
- Prevention suggestions

**No extra text is allowed** in the output. The response must be **valid JSON only**, followed by a 2-column table for readability.

---

## Why the output is strictly structured

This prompt **forces a structured JSON output** to reduce errors and hallucinations, and to make the result easy to:
- display in a review UI for supervisor correction
- render into a formatted PDF safety report
- store in a safety management database
- send to downstream workflows (compliance reporting, risk analytics, ERP)

---

## Core guardrails (anti-hallucination)

The prompt enforces these rules:

- **Use only what is explicitly stated** in the transcript.
- If a field is missing, output **""** (empty string).
- For **fixed-option fields** (incident type, category), output only a value from the allowed list.
- Do NOT use the current date/time as the event date.
- Output must be **valid JSON only**, no explanations.

---

## Fixed-option fields

**Incident type** (`vaaratilanne_turvallisuushavainto_tai_poikkeama`):
- `Near miss`
- `safety observation` ← default if unclear
- `deviation`

**Incident category** (`havainto_ja_poikkeamatyypin_tarkennus`):
- `Kalusto` (Equipment)
- `Laatu` (Quality)
- `Alihankinta` (Subcontracting)
- `Ympäristö` (Environment)
- `Asiakas` (Customer)
- `Turvallisuus` (Safety) ← default if unclear

---

## Output schema (strict JSON — 13 fields)

```json
{
  "vaaratilanne_turvallisuushavainto_tai_poikkeama": "",
  "havainto_ja_poikkeamatyypin_tarkennus": "",
  "paivamaara": "",
  "tyonantaja": "",
  "kirjaaja": "",
  "henkilotyyppi": "",
  "projektitunnus": "",
  "tapahtumaselostus": "",
  "tapahtumaan_johtaneet_tekijat": "",
  "tehdyt_valittomaat_toimenpiteet": "",
  "toimenpiteiden_tekija": "",
  "tekopaiva": "",
  "ehdotukset_vastaavien_tilanteiden_valttamiseksi": ""
}
```

---

## How to use

### Option 1 — Paste directly into ChatGPT, Claude.ai, or Gemini

1. Open `prompt.txt` and copy its full content.
2. Open a new conversation in any capable AI assistant.
3. Paste the prompt into the message box.
4. In the **same message**, add the transcript below the prompt:
```
TRANSCRIPT:
[Paste your transcript text here]
```
5. Send. The model returns a valid JSON object followed by a 2-column summary table.

To try with the included sample, paste the content of `data/transcript_1.txt` as the transcript.

### Option 2 — Custom GPT (reusable setup)

1. Go to **ChatGPT → Explore GPTs → Create**.
2. Paste the full content of `prompt.txt` into the **Instructions** field.
3. Give the GPT a name (e.g. "Safety Observation Extractor") and save it.
4. Each time: open the Custom GPT, paste the transcript, and send. No prompt copy-paste needed.

---

## How to customise for a different use case

### 1. Change the fields

Find the **FIELDS TO EXTRACT** section and add, remove, or rename fields. Update the JSON schema at the bottom to match. Follow the same numbered format.

### 2. Change the fixed-option categories

Find the fixed-option fields (incident type and category) and replace the allowed values with the categories used by your organisation. Keep the same `[CHOOSE ONE: ...]` format and specify a sensible default.

### 3. Change the output language

The current prompt uses Finnish field names in the JSON keys (matching the official form). To switch to English keys, rename the JSON keys in both the **FIELDS TO EXTRACT** section and the **OUTPUT (STRICT JSON)** block.

### 4. Adapt to a different domain

This prompt pattern works for any safety or quality observation workflow:
- Replace the task description with your domain (e.g. "environmental deviation reporting")
- Replace the fields with your domain's required fields
- Update the fixed-option lists to match your classification schema

---

## Repository structure

```
safety-observation-reporting/
├── README.md
├── prompt.txt            ← paste this into ChatGPT, Claude.ai, or Gemini
└── data/
    └── transcript_1.txt  ← sample Finnish safety observation transcript
```

---

## Sample transcript (data/transcript_1.txt)

The sample transcript is a spoken safety observation in Finnish. It covers:
- A near miss in a warehouse (oil leak causing slip risk)
- Date, employer, reporter, and project ID
- Contributing factors (hydraulic oil leak, poor lighting)
- Immediate actions taken (area cordoned off, maintenance notified)
- Prevention suggestions (regular equipment checks, better lighting)

Use it to test the prompt end-to-end.

---

## Known limitations (prototype scope)

- If a transcript is vague or omits key fields, outputs will be empty strings by design.
- The incident category defaults to "Turvallisuus" (Safety) when no category is explicitly stated.
- For production use, add a post-extraction human review step before submitting official safety records.

---

## Disclaimer

This prompt is intended for demo and prototyping. Always review extracted data before submitting official safety observation reports.
