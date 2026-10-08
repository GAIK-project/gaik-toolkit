---
name: construction-diary-creation
description: Extracts structured data from Finnish construction site daily diary audio recordings (Työmaapäiväkirja) and creates a formatted Word document with extracted fields. Use when the user needs to process construction site manager's audio diary recordings into standardized documentation.
---

# Construction Diary Creation (Työmaapäiväkirja)

Transcribes audio recordings from construction site managers and extracts structured information required for official daily construction site diaries (Työmaapäiväkirja). Outputs a clean MS Word document with a 2-column table containing all extracted fields.

This skill is designed to run in **Claude Desktop** with:
- An MCP **gaik-transcriber** server (for transcribing audio/video recordings)

## When to Use

Use this skill when:
- User needs to process a construction site diary audio recording
- User mentions "työmaapäiväkirja", "construction diary", or "site diary"
- User wants to extract structured information from site manager's audio notes
- User asks to process or transcribe a construction site recording
- User provides an audio file from a Finnish construction site

## Input

**Required:**
- Audio/video recording file path (e.g., `.mp3`, `.m4a`, `.wav`, `.mp4`, etc.)
- The recording should contain a construction site manager verbally describing the day's events

**Required parameter:**
- `audio_file_path`: Full path to the audio/video recording. If not provided, ask the user to specify it.

## Tooling Rules (Windows vs Linux Path Safety)

### Why this matters
On Windows, Claude Desktop + toolchains sometimes behave like they are in a POSIX shell, producing paths like `/mnt/c/...`.
Meanwhile, your MCP servers may run **native Windows Python**, expecting `C:\...`.
This mismatch can cause "file not found" or failing shell commands.

### Strict rules
1) **Prefer Windows drive-letter paths on Windows**
Pass file paths like `C:\Users\...\recording.m4a` to the gaik-transcriber.

2) **Avoid bash commands on Windows**
If you must run a command on Windows, prefer **PowerShell**.

3) **When calling gaik-transcriber, use Windows drive-letter paths**
Pass file paths like `C:\Users\...\recording.m4a`.
If you only have a POSIX/WSL path (e.g., `/mnt/c/...`), convert it to a Windows path before calling the transcriber.

4) **Never assume the environment is Linux**
Treat the runtime as OS-ambiguous and enforce the above rules to stay stable.

5) **Never do the following:**
- NEVER run pip install, python -c, or any ad-hoc parsing code
- NEVER use /mnt/user-data/uploads/... paths unless explicitly provided by the environment

## Workflow

### Step 1 — Get Audio File Path

If the user has not specified an audio file path, ask for it:
- Request the full path to the audio recording
- Verify the path uses Windows format (e.g., `C:\Users\...`) on Windows systems
- Confirm the file exists before proceeding

### Step 2 — Transcribe Audio (gaik-transcriber MCP tool)

Call the transcription MCP tool:

```
gaik-transcriber:transcribe_audio
  file_path: <full_path_to_audio_file>
  enhanced: false
```

**Parameters:**
- `file_path`: Full Windows path to the recording
- `enhanced`: Always use `false` (standard transcription is sufficient)

**If transcription fails:**
- Check the path format (ensure Windows drive-letter paths on Windows)
- Report the error clearly to the user
- Do NOT proceed with extraction if transcription fails

**Important:** Preserve the entire transcription text for the extraction step.

### Step 3 — Extract Structured Fields

From the transcription, extract the following 20 fields exactly as specified.

**CRITICAL EXTRACTION RULES:**

1. **Use Finnish field names exactly as listed below**
2. **If a field is not mentioned in the transcript, return an empty string ("")**
3. **Keep extracted values BRIEF** - use only tight keywords, not full sentences
4. **Do NOT hallucinate or invent information**
5. **For fields with predefined lists, ONLY select from those lists**
6. **Follow the specified format for each field exactly**

### Fields to Extract (Finnish):

**1. Kohde**
- Description: Address or subject of the diary
- Format: Do not write numbers in words
- Example: `3285-00 Komeetankuja 6, 02210 Espoo`
- If not mentioned: return `""`

**2. Laatija**
- Description: Name of the author recording the diary
- Format: Full name as mentioned
- If not mentioned: return `""`

**3. Sää**
- Description: Weather conditions
- Format: Temperature, wind speed, humidity, ground temperature
- Example: `3 °C, 2 m/s, 78 % suht. kosteus, Kp: -1.4 C`
- If not mentioned: return `""`

**4. Päivämäärä**
- Description: Date of the diary entry
- Format: `dd.mm.yyyy` or `dd.mm` if year not mentioned
- Example: If audio says "20.5", return `20.05`
- If not mentioned: return `""`

**5. Resurssit - Henkilöstö**
- Description: Personnel resources for the day
- Format: `Työnjohtajat: X hlö, Työntekijät: Y hlö, Alihankkijat: Z hlö, Yhteensä: W hlö`
- Note: Use 0 for categories with no information
- Example: `Työnjohtajat: 2 hlö, Työntekijät: 1 hlö, Alihankkijat: 4 hlö, Yhteensä: 7 hlö`
- If not mentioned: return `""`

**6. Työviikko**
- Description: Work week number
- Format: Number only (e.g., `2`, `15`)
- If not mentioned: return `""`

**7. Päivän työt**
- Description: List all tasks of today
- Include: Completed, partially completed, incomplete, ongoing, and newly started work
- Format: Brief bullet points or comma-separated list
- If not mentioned: return `""`

**8. Päivän tapahtumat**
- Description: Unusual events that were not anticipated
- Format: ONLY tight keywords
- If no unusual events: return `Ei tapahtumia`
- If not mentioned: return `Ei tapahtumia`

**9. Liitteet**
- Description: Number and type of attachments
- Format: Count and type (e.g., `4 kuvaa, 1 sähköpostin liite, 1 muistiinpano`)
- Example: `4 photos, 1 email attachment, 1 note`
- If not mentioned: return `""`

**10. Valvojan huomiot**
- Description: Supervisor's general notes about the day
- Format: ONLY tight keywords
- Only if explicitly mentioned
- If not mentioned: return `""`

**11. Päivän poikkeamat**
- Description: Issues or deviations in work
- Format: ONLY tight keywords
- Examples: delay, damage, unplanned finding
- Only if mentioned
- If not mentioned: return `""`

**12. Aloitetut työvaiheet**
- Description: Work phases started today
- **MUST CHOOSE ONLY FROM THIS LIST:**
  - Asbestipurku
  - sisäpurku
  - rungon purku
  - lajittelu
  - työmaan aitaus
  - pölynhallinta
  - massojen ajo
  - romun ajo
  - perusten purku
  - pulverointi
  - timanttityöt
  - suojaustyöt
  - metalli- ja putkipurku työt
  - polttoleikkaus
- If no match or not mentioned: return `""`

**13. Käynnissä olevat työvaiheet**
- Description: Work phases currently ongoing
- **MUST CHOOSE ONLY FROM THIS LIST:**
  - Asbestipurku
  - sisäpurku
  - rungon purku
  - lajittelu
  - työmaan aitaus
  - pölynhallinta
  - massojen ajo
  - romun ajo
  - perusten purku
  - pulverointi
  - timanttityöt
  - suojaustyöt
  - metalli- ja putkipurku työt
  - polttoleikkaus
- If no match or not mentioned: return `""`

**14. Päättyneet työvaiheet**
- Description: Work phases completed today
- **MUST CHOOSE ONLY FROM THIS LIST:**
  - Asbestipurku
  - sisäpurku
  - rungon purku
  - lajittelu
  - työmaan aitaus
  - pölynhallinta
  - massojen ajo
  - romun ajo
  - perusten purku
  - pulverointi
  - timanttityöt
  - suojaustyöt
  - metalli- ja putkipurku työt
  - polttoleikkaus
- If no match or not mentioned: return `""`

**15. Keskeytyneet työvaiheet**
- Description: Work phases interrupted
- **MUST CHOOSE ONLY FROM THIS LIST:**
  - Asbestipurku
  - sisäpurku
  - rungon purku
  - lajittelu
  - työmaan aitaus
  - pölynhallinta
  - massojen ajo
  - romun ajo
  - perusten purku
  - pulverointi
  - timanttityöt
  - suojaustyöt
  - metalli- ja putkipurku työt
  - polttoleikkaus
- If no match or not mentioned: return `""`

**16. Pyydetyt lisäajat**
- Description: Requested additional time/extensions
- Format: ONLY tight keywords
- Only if mentioned
- If not mentioned: return `""`

**17. Tehdyt katselmukset**
- Description: Inspections performed
- Format: ONLY tight keywords
- Only if mentioned
- If not mentioned: return `""`

**18. Valvojan huomautukset**
- Description: Supervisor's remarks/warnings
- Format: ONLY tight keywords
- Only if mentioned
- If not mentioned: return `""`

**19. Valvojan allekirjoitus**
- Description: Supervisor's signature
- Only if explicitly stated
- If not mentioned: return `""`

**20. Vastaavan allekirjoitus**
- Description: Responsible person's signature
- Only if explicitly stated
- If not mentioned: return `""`

### Step 4 — Generate Word Document

Before creating the document, view the docx skill:
```
view /mnt/skills/public/docx/SKILL.md
```

Then create a new Word document using the docx skill's "Creating a new Word document" workflow.

**Document Structure:**

1. **Title:** `TYÖMAAPÄIVÄKIRJA` (centered, bold, large font)

2. **2-Column Table:**
   - Column 1: Field name (Finnish)
   - Column 2: Extracted value
   - Include all 20 fields in order, even if value is empty string

**Table Format:**
```
| Kenttä                      | Arvo                           |
|-----------------------------|--------------------------------|
| Kohde                       | [extracted value or ""]        |
| Laatija                     | [extracted value or ""]        |
| Sää                         | [extracted value or ""]        |
| Päivämäärä                  | [extracted value or ""]        |
| Resurssit - Henkilöstö      | [extracted value or ""]        |
| Työviikko                   | [extracted value or ""]        |
| Päivän työt                 | [extracted value or ""]        |
| Päivän tapahtumat           | [extracted value or "Ei tapahtumia"] |
| Liitteet                    | [extracted value or ""]        |
| Valvojan huomiot            | [extracted value or ""]        |
| Päivän poikkeamat           | [extracted value or ""]        |
| Aloitetut työvaiheet        | [extracted value or ""]        |
| Käynnissä olevat työvaiheet | [extracted value or ""]        |
| Päättyneet työvaiheet       | [extracted value or ""]        |
| Keskeytyneet työvaiheet     | [extracted value or ""]        |
| Pyydetyt lisäajat           | [extracted value or ""]        |
| Tehdyt katselmukset         | [extracted value or ""]        |
| Valvojan huomautukset       | [extracted value or ""]        |
| Valvojan allekirjoitus      | [extracted value or ""]        |
| Vastaavan allekirjoitus     | [extracted value or ""]        |
```

**Document Formatting:**
- Use clean, professional formatting
- Table should have borders
- First column (field names) should be slightly bold
- Keep the document simple and readable

### Step 5 — Save and Present

1. Save the document with a descriptive filename, e.g., `Tyomaapaivakirja_[Date].docx`
2. Use `present_files` to share the document with the user

## Guardrails

### Critical Rules to Prevent Hallucination:

**MUST DO:**
- Extract ONLY information explicitly mentioned in the transcript
- Use exact Finnish field names as specified
- Keep extracted values BRIEF (tight keywords only)
- Return empty string ("") if field not mentioned in transcript
- For work phases (fields 12-15), ONLY select from the predefined lists
- For date fields, follow the exact format specified
- Preserve numbers as numbers, not words (e.g., "3285" not "kolmetuhatta...")

**MUST NOT DO:**
- NEVER invent or hallucinate information not in the transcript
- NEVER add assumptions or interpretations
- NEVER use values outside predefined lists for work phase fields
- NEVER create full sentences when "tight keywords" are requested
- NEVER leave out fields from the table (include all 20 fields)
- NEVER change Finnish field names
- NEVER guess dates, numbers, or names

### Field-Specific Validation:

**Date (Päivämäärä):**
- Must be in format `dd.mm.yyyy` or `dd.mm`
- If transcript says "twentieth of May", extract as `20.05`

**Resources (Resurssit - Henkilöstö):**
- Must follow exact format with categories and counts
- Use 0 for categories with no information
- Must include "Yhteensä" (total) if any category has data

**Work Phases (Fields 12-15):**
- STRICT: Only use values from the predefined list
- If transcript mentions a work type not in the list, return `""`
- Multiple values can be comma-separated if multiple phases apply

**Päivän tapahtumat:**
- Special case: If nothing unusual mentioned, return `Ei tapahtumia`
- Otherwise use tight keywords only

### Error Handling:

**If transcription fails:**
- Report error clearly to user
- Do NOT attempt extraction without transcript
- Provide troubleshooting steps (check file path, file format, etc.)

**If transcript is unclear or ambiguous:**
- Extract what is clear
- Return `""` for unclear fields
- Do NOT guess or make assumptions

**If transcript is in wrong language:**
- Attempt extraction anyway
- Note to user that transcript may not match expected Finnish format

## Examples

### Example 1: Standard Daily Diary

**User prompt:**
"Process this construction diary recording: C:\Sites\diary-2024-05-20.mp3"

**Expected behavior:**
1. Transcribe audio using gaik-transcriber
2. Extract all 20 fields from transcript
3. Create Word document with 2-column table
4. Save as `Tyomaapaivakirja_20.05.2024.docx`
5. Present file to user

### Example 2: Minimal Information

**User prompt:**
"Extract diary data from C:\Audio\site-note.m4a"

**Expected behavior:**
1. Transcribe audio
2. Extract available fields
3. Return `""` for fields not mentioned
4. Return `Ei tapahtumia` for Päivän tapahtumat if nothing unusual
5. Create document with all 20 fields (including empty ones)
6. Present file to user

### Example 3: Missing File Path

**User prompt:**
"Create a construction diary from my recording"

**Expected behavior:**
1. Ask user for the audio file path
2. Explain format needed (e.g., `C:\path\to\file.mp3`)
3. Wait for user to provide path
4. Proceed with transcription and extraction once path is provided

## Notes

- The skill focuses on **accurate extraction** over fancy formatting
- **Never hallucinate** - empty fields are acceptable and expected
- The transcript may contain casual speech, filler words, and unclear audio - extract what is clear
- Work phase lists are **closed sets** - do not add values not in the lists
- All Finnish terminology must be preserved exactly as specified
- The output document should be simple and professional, suitable for official construction documentation
