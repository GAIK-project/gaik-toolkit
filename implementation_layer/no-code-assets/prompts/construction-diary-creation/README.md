# Construction Site Diary Extraction Prompt (Audio Transcript → JSON)

This folder contains a **prompt-only** information extraction workflow for the official **Työmaapäiväkirja** (daily construction site diary) used in construction projects.

You can use the prompt in two ways:
1. **As a Custom GPT** (paste into Custom GPT Instructions), or
2. **Directly in ChatGPT** (paste the prompt into a chat, then paste the transcript)

The prompt converts a spoken **audio transcript** from a site supervisor into a **strict JSON object** containing all 20 fields required for the standard daily diary form.

---

## What this prompt does

### Input
A transcript of an audio recording made by a construction site supervisor describing:
- Daily site activities and work tasks
- Personnel and subcontractors present on site
- Work phases started, ongoing, completed, or interrupted
- Weather conditions
- Any unusual events, deviations, or inspections
- Attachments such as photos or documents

### Output
A **single JSON object** with a fixed 20-field schema matching the Työmaapäiväkirja form, including:
- Site address and date
- Personnel breakdown (supervisors, workers, subcontractors, total)
- Day's tasks and events
- Work phases categorised from a fixed allowed list
- Supervisor observations, remarks, and signatures

**No extra text is allowed** in the output. The response must be **valid JSON only**, followed by a 2-column table for readability.

---

## Why the output is strictly structured

This prompt **forces a structured JSON output** to reduce errors and hallucinations, and to make the result easy to:
- display in a review UI for supervisor approval
- render into a formatted PDF diary document
- store in a project management database
- send to downstream workflows (compliance reporting, analytics, ERP)

---

## Core guardrails (anti-hallucination)

The prompt enforces these rules:

- **Use only what is explicitly stated** in the transcript.
- If a field is missing, output **""** (empty string).
- Keep every extracted value extremely short — tight keywords, no full sentences.
- Keep numbers as digits — do not rewrite in words.
- For **work phase fields**, output **only** a value from the allowed list; otherwise **""**.
- Output must be **valid JSON only**, no explanations.

---

## Work phase options (fixed list)

The four work phase fields (started / ongoing / completed / interrupted) each accept **only** values from this list:

```
Asbestipurku, sisäpurku, rungon purku, lajittelu, työmaan aitaus,
pölynhallinta, massojen ajo, romun ajo, perusten purku, pulverointi,
timanttityöt, suojaustyöt, metalli- ja putkipurku työt, polttoleikkaus
```

If the transcript describes a phase not matching any option, the field is left blank.

---

## Output schema (strict JSON — 20 fields)

```json
{
  "kohde": "",
  "laatija": "",
  "saa": "",
  "paivamaara": "",
  "resurssit_henkilosto": "",
  "tyoviikko": "",
  "paivan_tyot": "",
  "paivan_tapahtumat": "",
  "liitteet": "",
  "valvojan_huomiot": "",
  "paivan_poikkeamat": "",
  "aloitetut_tyovaiheet": "",
  "kaynnissa_olevat_tyovaiheet": "",
  "paattyneet_tyovaiheet": "",
  "keskeytyneet_tyovaiheet": "",
  "pyydetyt_lisaajat": "",
  "tehdyt_katselmukset": "",
  "valvojan_huomautukset": "",
  "valvojan_allekirjoitus": "",
  "vastaavan_allekirjoitus": ""
}
```

---

## How to use

### Option 1 — Paste directly into ChatGPT

1. Open `prompt.txt` and copy its full content.
2. Open a conversation in any capable AI assistant — **ChatGPT**, **Claude.ai**, or **Gemini** all work.
3. Paste the prompt into the message box.
4. In the **same message**, add the transcript below the prompt:
```
TRANSCRIPT:
[Paste your transcript text here]
```
5. Send. The model returns a valid JSON object followed by a 2-column summary table.

To try with the included sample, paste the content of `data/transcript_1.txt` as the transcript.

### Option 2 — Custom GPT (reusable setup)

For a permanent setup that does not require re-pasting the prompt each time:

1. Go to **ChatGPT → Explore GPTs → Create**.
2. Open `prompt.txt` and paste its full content into the **Instructions** field.
3. Give the GPT a name (e.g. "Site Diary Extractor") and save it.
4. Each time: open the Custom GPT, paste the transcript text, and send. No prompt copy-paste needed.

This is recommended for regular daily use on a project site.

---

## How to customise for a different use case

The prompt in `prompt.txt` is structured so that each part can be changed independently. Here is what to edit for common customisation scenarios.

### 1. Change the fields to extract

Find the **FIELDS TO EXTRACT** section in `prompt.txt`. Each numbered line defines one field. To adapt to a different domain:

- **Rename** a field by changing its label and the matching key in the JSON schema at the bottom of the prompt.
- **Remove** a field by deleting its numbered line and its corresponding key from the JSON schema.
- **Add** a field by adding a new numbered line (with instructions) and a new key in the JSON schema.

Example — replacing the construction-specific `Päivän poikkeamat` with a general `Issues or incidents` field:

*Before:*
```
11. Päivän poikkeamat [Any issues or deviations in work (ONLY tight keywords)...]
```
*After:*
```
11. Issues or incidents [Any problems, accidents, or deviations (ONLY tight keywords); return "" if none]
```
Then update the JSON schema key from `"paivan_poikkeamat"` to `"issues_or_incidents"`.

### 2. Change the fixed work phase options

The work phase fields use a **controlled vocabulary** list. To adapt to a different type of project:

Find the four work phase fields (lines 12–15) and replace the allowed options list with your own set of activity types. Keep the same format:

```
12. Started activities [CHOOSE FROM this list or return "" if no match: Activity A, Activity B, Activity C, ...]
```

Example for a renovation project:
```
12. Started activities [CHOOSE FROM: Demolition, Electrical work, Plumbing, Plastering, Painting, Flooring, Tiling, Insulation, Roofing]
```

### 3. Change the output language

The current prompt extracts into Finnish field names and values. To extract into English:

- Change all field labels in the **FIELDS TO EXTRACT** section to English.
- Change all JSON keys in the **OUTPUT (STRICT JSON)** block to English equivalents.
- Update the normalization rules if date or personnel formats differ.

Example JSON key change:
```json
"kohde"      → "site_address"
"paivamaara" → "date"
"saa"        → "weather"
```

### 4. Change the output format

By default the prompt returns a JSON object **plus** a 2-column table. To return only JSON (e.g. for programmatic use), delete or comment out this instruction from the **OUTPUT FORMAT** section:

```
2.	Then, present the same JSON content as a 2-column table...
```

To return only the table and skip the JSON, reverse which step is step 1 and which is optional.

### 5. Change the domain entirely

To reuse this prompt pattern for a completely different domain (e.g. daily health and safety inspection, field service report, environmental monitoring log):

1. Replace the opening task description with your domain.
2. Replace all fields in **FIELDS TO EXTRACT** with your fields.
3. Replace the allowed work phase lists with your domain's activity categories (or remove them if not applicable).
4. Update the JSON schema to match.
5. Replace the sample transcript in `data/` with a sample from your domain.

The anti-hallucination rules, normalization guidelines, and output format instructions at the top of the prompt can be kept as-is — they are domain-agnostic.

---

## Repository structure

```
construction-diary-creation/
├── README.md
├── prompt.txt            ← paste this into ChatGPT or Custom GPT
└── data/
    └── transcript_1.txt  ← sample Finnish site supervisor recording
```

---

## Sample transcript (data/transcript_1.txt)

The sample transcript is a spoken recording by a site supervisor (in Finnish). It covers:
- Site address and date
- Personnel count (4 subcontractors + 1 own machine operator)
- Ongoing work phases (rungon purku, sisäpurku)
- A utility disconnection task (water, electricity, district heating)
- A call to a waste collection service

Use it to test the prompt end-to-end in ChatGPT.

---

## Known limitations (prototype scope)

This is a prompt-only prototype. Common limitations include:

- If a transcript is vague (no explicit date, no explicit work phase), outputs will be empty strings by design.
- Work phase fields return blank if the spoken description doesn't match the fixed list.
- Personnel totals must be directly calculable from stated numbers — not estimated from context.

For production use, you would typically add:

- controlled mobile voice capture with prompts guiding the supervisor
- post-extraction human review UI
- PDF rendering of the structured diary output (see the code-based pipeline)

---

## Disclaimer

This prompt is intended for demo and prototyping. Always review extracted data before submitting official construction site diary entries.
