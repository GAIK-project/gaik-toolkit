# Extraction Requirements: MaintenanceTicket

## Purpose

Extract structured maintenance ticket fields from a Finnish voice message recorded by a
field technician reporting a facility fault. The technician may speak informally, use
abbreviations, or describe the situation in conversational Finnish. Extract only what is
explicitly stated — do not infer, guess, or hallucinate values.

## Language

- Input: Finnish (fi)
- Field values should be preserved in the language they appear in the audio (typically Finnish)
- Field names are in English as specified below
- Handle Finnish colloquial expressions, technical abbreviations, and regional terms for
  facility components and locations

---

## Fields

### reporter_name (str | None)
The name of the technician reporting the fault.
- Extract only if explicitly stated (e.g. "Täällä Matti Virtanen", "Minun nimeni on Leena")
- Do not infer from voice characteristics or context
- Set to `null` if not mentioned

---

### asset_identifier (str | None)
The identifier or description of the faulty asset or equipment.
- May be a code (e.g. "LVI-003", "P-12"), a descriptive name ("kolmannen kerroksen
  ilmanvaihtokone", "kylmälaite varastossa"), or both
- Extract the most specific reference stated
- Set to `null` if not mentioned

---

### location (str | None)  **[REQUIRED]**
The physical location of the fault within the facility.
- Extract building, floor, room, area, or zone references exactly as stated
  (e.g. "B-rakennus, toinen kerros", "huone 214", "keittiön varastotila", "pysäköintihalli")
- Preserve the technician's wording — do not normalise, abbreviate, or translate
- If location is not stated at all: set to `null` AND add `"location"` to `uncertain_fields`

---

### fault_description (str | None)  **[REQUIRED]**
A concise, faithful description of the fault or problem observed.
- Capture what is broken, malfunctioning, or abnormal as the technician describes it
- Common Finnish fault indicators: vuoto (leak), melu/ääni (noise), ei toimi (not working),
  katkennut (broken), ylikuumenee (overheating), sulake paloi (fuse blown),
  ovi ei sulkeudu (door won't close), vesi ei tule (no water flow)
- Do not paraphrase beyond what is needed for clarity
- If no fault is described: set to `null` AND add `"fault_description"` to `uncertain_fields`

---

### urgency (str | None)  **[REQUIRED]**
The urgency level of the fault.

**Allowed values (English, lowercase only):** `low`, `medium`, `high`

Finnish expression mapping:
- **`high`**: kiireellinen, heti, välittömästi, pikaisesti, vaarallinen, kriittinen,
  turvallisuusriski, tulipalovaara, vesivahingon uhka, täytyy korjata nyt
- **`medium`**: tänään, pian, melko kiireellinen, normaali kiireellisyys,
  ei hätää mutta pitäisi katsoa, seuraavien päivien aikana
- **`low`**: ei kiireellinen, rauhassa, kun sopii, matala prioriteetti, ei haittaa toistaiseksi

Rules:
- If urgency is not stated → `null` + add `"urgency"` to `uncertain_fields`
- If the stated urgency does not clearly map to `low`, `medium`, or `high` →
  `null` + add `"urgency"` to `uncertain_fields`
- Never output any value other than `"low"`, `"medium"`, `"high"`, or `null`
- Never invent or guess an urgency level not expressed or clearly implied in the audio

---

### observation_date (date | None)
The date the fault was observed, if stated.
- Output format: YYYY-MM-DD
- Finnish date expressions to convert:
  - "tänään" → today's date
  - "eilen" → yesterday's date
  - Explicit dates: "27. heinäkuuta" or "27.7." → YYYY-07-27
- Set to `null` if not stated

---

### observation_time (str | None)
The time the fault was observed, if stated.
- Output format: HH:MM (24-hour clock)
- Finnish time expressions to convert:
  - "kello 14" → "14:00"
  - "puoli kolme" (half past two) → "14:30"
  - "vartin yli kymmenen" → "10:15"
- Set to `null` if not stated

---

### actions_taken (list[str] | None)
A list of immediate actions the technician has already taken before making this report.
- Each distinct action is a separate string in the list
  (e.g. `["Suljettu päävesihana", "Ilmoitettu vartialle", "Sijoitettu varoitusmerkki"]`)
- Only include actions explicitly described as already completed
- Set to `null` (or empty list) if no actions were mentioned

---

### uncertain_fields (list[str] | None)
A list of the field names that could not be confidently extracted.
Add a field name here when:
- A required field was not stated in the audio (field set to `null`)
- An extracted value is ambiguous or unclear
- An urgency value was stated but does not match the allowed values

Examples:
- `["urgency", "location"]` — both were missing or unresolvable
- `["observation_date"]` — date was mentioned but too vague to convert
- `null` or `[]` — all fields were clear and extractable

---

## Output Format Policy

- Return a single JSON object conforming to the `MaintenanceTicket` schema
- All nine fields must be present in the output, even if their value is `null`
- Required fields (`location`, `fault_description`, `urgency`) must always appear in the
  JSON object; they may be `null` only when genuinely not stated, and in that case the
  field name must appear in `uncertain_fields`
- Do not add fields beyond the nine specified
- Do not hallucinate values — absence of information → `null`, not a plausible guess
- Field names in English (as above); extracted text values in Finnish (as spoken)
