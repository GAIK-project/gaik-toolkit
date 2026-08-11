# Extraction Requirements: MaintenanceTicket

## Task

You are extracting structured maintenance ticket fields from a Finnish-language
voice recording transcript. The technician has reported a facility fault verbally.
Your job is to populate a `MaintenanceTicket` object from the transcript.

**Language note:** The transcript is in Finnish. Field values in the output must
be in Finnish unless the field is a controlled enum (e.g. `urgency`) — those
must always be output in English as specified below.

---

## Output Format

Return a single JSON object with exactly the fields listed below.
- Set a field to `null` if the information was not stated or cannot be reliably
  extracted from the transcript.
- Do **not** invent, infer, or guess values. If a technician said something
  ambiguous, prefer `null` and flag the field in `uncertain_fields`.
- For required fields (`location`, `fault_description`, `urgency`): if the value
  is null, the field name **must** appear in `uncertain_fields`.

---

## Fields

### `reporter_name` — string | null — Optional

The full name of the technician who recorded the message.

- Extract if the technician introduces themselves (e.g. "Täällä Matti Korhonen",
  "Minä olen Tiina Virtanen", "Tämä on Pekka").
- If no name is given, set to `null`.
- Do not extract job titles, only names.

---

### `asset_identifier` — string | null — Optional

The identifier of the specific asset or piece of equipment that is faulty.

- This may be an asset tag, equipment number, machine ID, or a descriptive name
  used internally (e.g. "pumppuyksikkö P-12", "ilmanvaihtokone IV-03",
  "hissi 2", "vesiventtiili V-204").
- Extract verbatim as stated by the technician.
- If no specific asset is mentioned, set to `null`.

---

### `location` — string | null — **Required**

The location of the fault within the facility.

- May include building, wing, floor, room number, corridor, or area name.
- Finnish cues: "rakennuksessa", "kerroksessa", "huoneessa", "käytävällä",
  "osastolla", "konehuoneessa", "ulkona", "pihalla", "varastossa".
- Examples: "B-rakennus, 2. kerros, huone 214", "konehuone 3",
  "pääaula, pohjakerros", "parkkihalli, pohja P1".
- Extract verbatim or reconstruct from surrounding context.
- If no location is mentioned at all, set to `null` and add `"location"` to
  `uncertain_fields`.

---

### `fault_description` — string | null — **Required**

A description of what is broken, malfunctioning, or requires attention.

- Capture the full fault description as closely as possible to the technician's
  own words, in Finnish.
- Finnish cues for fault types: "viallinen" (faulty), "rikki" (broken),
  "vuotaa" (leaking), "ei toimi" (not working), "sammui" (shut off/went out),
  "ylikuumenee" (overheating), "melua" (noise), "haju" (smell/odour),
  "ei käynnisty" (won't start), "jumissa" (stuck/jammed).
- Include any additional context the technician gives (degree of severity,
  which specific part is affected, observable symptoms).
- If no fault is described at all, set to `null` and add `"fault_description"`
  to `uncertain_fields`.

---

### `urgency` — "low" | "medium" | "high" | null — **Required**

The urgency level of the fault.

- **Must be exactly one of:** `"low"`, `"medium"`, `"high"`. No other value is
  acceptable. Always output in English.
- Map Finnish urgency expressions as follows:

  | Finnish expression | English value |
  |--------------------|---------------|
  | kiireellinen, kiireesti, heti, välittömästi, kriittinen, vakava | `"high"` |
  | normaali, tavallinen, ei kiireellinen, kohtuullinen | `"medium"` |
  | matala kiireellisyys, vähäinen, ei kiireinen, sopii odottaa | `"low"` |

- If the technician gives no explicit urgency, apply contextual reasoning:
  - Safety hazard, flooding, fire risk, total equipment failure → `"high"`
  - Performance degradation, minor leak, intermittent fault → `"medium"`
  - Cosmetic issue, very minor inconvenience → `"low"`
- If urgency cannot be determined even with contextual reasoning, set to `null`
  and add `"urgency"` to `uncertain_fields`.
- **Never use any string other than `"low"`, `"medium"`, or `"high"`.**

---

### `observation_date` — date (YYYY-MM-DD) | null — Optional

The date the fault was observed, in `YYYY-MM-DD` format.

- Finnish cues: "tänään" (today), "eilen" (yesterday), "maanantaina" (on Monday),
  specific dates like "15. heinäkuuta" or "15.7." or "15/7".
- If relative expressions are used (e.g. "eilen"), resolve to an absolute date
  only if the recording date is reliably known.
- If the date cannot be determined, set to `null`.

---

### `observation_time` — string (HH:MM) | null — Optional

The time the fault was observed, in `HH:MM` (24-hour) format.

- Finnish cues: "klo", "kello", "aamulla" (in the morning), "iltapäivällä"
  (in the afternoon), specific times like "14:30", "kaksi kolmekymmentä".
- Convert 12-hour times to 24-hour format.
- If time cannot be determined, set to `null`.

---

### `actions_taken` — list[string] | null — Optional

A list of immediate actions the technician already took before or while reporting.

- Each element is a short Finnish sentence describing one action.
- Finnish cues: "suljin", "sammutin", "ilmoitin", "eristin", "laitoin kyltit",
  "otin kuvan", "avasin", "suljettu", "käynnistin uudelleen".
- If no actions were taken, set to `null` (not an empty list).
- Example: `["Sammutin laitteen", "Ilmoitin esimiehelle"]`

---

### `uncertain_fields` — list[string] | null — Optional (but required when any
required field is null)

A list of field names whose values could not be reliably extracted.

- Add a field name here if:
  - The value was ambiguous or contradictory in the transcript.
  - The field is required (`location`, `fault_description`, `urgency`) and its
    value is `null`.
  - The technician used very vague language that could not be mapped to a
    specific value.
- Use the exact field names from the schema (snake_case).
- If all fields were extracted reliably, set to `null`.
- Example: `["urgency", "observation_date"]`

---

## Handling Rules

1. **Never invent values.** If information is absent, use `null`.
2. **Required fields null → flag them.** Any of `location`, `fault_description`,
   or `urgency` that cannot be filled must appear in `uncertain_fields`.
3. **`urgency` enum is strict.** Only `"low"`, `"medium"`, `"high"` — no Finnish
   words, no other English words.
4. **Verbatim Finnish for free-text fields.** Do not translate or paraphrase
   `location`, `fault_description`, `actions_taken` into English.
5. **Dates and times must match their format.** `observation_date` → `YYYY-MM-DD`.
   `observation_time` → `HH:MM`. Reject partial or ambiguous values with `null`.
6. **No hallucination.** Do not combine or infer across multiple recordings.
   Extract only what is stated in this transcript.
