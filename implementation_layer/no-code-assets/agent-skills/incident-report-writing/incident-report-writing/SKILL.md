---
name: incident-report-writing
description: Extracts structured data from incident/safety observation audio recordings for manufacturing company reporting. Use when the user needs to process supervisor or employee audio recordings into standardized incident report data.
---

# Incident Report Writing

Transcribes audio recordings from supervisors or employees describing incidents, near misses, safety observations, or related initiatives, and extracts structured information required for official incident reporting forms.

This skill is designed to run in **Claude Desktop** with:
- An MCP **gaik-transcriber** server (for transcribing audio/video recordings)

## When to Use

Use this skill when:
- User needs to process an incident or safety observation audio recording
- User mentions "incident report", "safety observation", "near miss", or "safety initiative"
- User wants to extract structured information from safety-related audio notes
- User asks to process or transcribe an incident recording
- User provides an audio file describing a workplace incident or safety observation

## Input

**Required:**
- Audio/video recording file path (e.g., `.mp3`, `.m4a`, `.wav`, `.mp4`, etc.)
- The recording should contain a description of an incident, near miss, safety observation, or safety initiative

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

From the transcription, extract the following 17 fields exactly as specified.

**CRITICAL EXTRACTION RULES:**

1. **Use ONLY information explicitly present in the transcript**
2. **If a field is not mentioned, return an empty string ("")**
3. **Keep extracted values BRIEF** - use only tight keywords, not full sentences
4. **Do NOT hallucinate or invent information**
5. **For fields with predefined lists, ONLY select from those lists**
6. **Follow the specified format for each field exactly**

### Fields to Extract:

**1. Type of form**
- Description: Type of report being filed
- **Fixed options (choose ONLY one):**
  - `Safety observation`
  - `Safety-related initiative`
- If not explicitly mentioned or doesn't match: return `""`

**2. Observation type**
- Description: Category of the observation
- **Fixed options (choose ONLY one):**
  - `Safety`
  - `Environmental protection`
  - `Energy efficiency`
- If not explicitly mentioned or doesn't match: return `""`

**3. Positive safety observation**
- Description: Whether this is a positive observation
- **Fixed options:**
  - `Yes` (ONLY if explicitly stated as positive)
- If not explicitly stated as positive: return `""`

**4. Reporter name**
- Description: Name of the person making the report
- Format: Full name as mentioned
- If not mentioned: return `""`

**5. Reporter organization**
- Description: Organization the reporter belongs to
- **Fixed options (choose ONLY one):**
  - `Luvata Pori Oy`
  - `Luvata Oy`
  - `Other`
- If not explicitly mentioned or doesn't match: return `""`

**6. Summer employee**
- Description: Whether the reporter is a summer employee
- **Fixed options:**
  - `Yes`
  - `No`
- If not explicitly stated: return `""`

**7. Event date and time**
- Description: When the incident/observation occurred
- **Format rules:**
  - If both date and time given: `dd.mm.yyyy HH:MM`
  - If only date given: `dd.mm.yyyy`
  - If year not mentioned: `dd.mm`
  - Zero-pad day/month: `5.4` → `05.04`
- If not mentioned: return `""`

**8. Building or site**
- Description: Building or site where event occurred
- Format: Keep as short as possible
- If not mentioned: return `""`

**9. Detailed location**
- Description: Specific area within building/site
- Format: Keep as short as possible
- If not mentioned: return `""`

**10. Location clarification**
- Description: Additional location details
- Format: Brief clarification only
- If not mentioned: return `""`

**11. Event description**
- Description: What happened
- Format: Brief keywords describing the event
- If not mentioned: return `""`

**12. Near miss**
- Description: Whether this was a near miss event
- **Fixed options:**
  - `Yes`
  - `No`
- If not explicitly stated: return `""`

**13. Possible consequences**
- Description: What could have happened
- Format: Brief keywords only
- If not mentioned: return `""`

**14. Direct cause of the event**
- Description: Root cause category
- **Fixed options (choose ONLY one):**
  - `5S`
  - `Technical failure`
  - `Protective devices on machines`
  - `Maintenance`
  - `Tools and devices`
  - `Work methods and instructions`
  - `Work guidance / induction / training`
  - `Following instructions and common standards`
  - `Information flow / lack of information flow`
  - `Working conditions`
  - `Weather conditions`
  - `Traffic`
  - `First-aid supplies (used / shortages)`
  - `PPE`
  - `Hurry / insufficient resources`
  - `Human / organizational factor`
- If not explicitly mentioned or doesn't match: return `""`

**15. Corrective actions performed**
- Description: Whether corrective actions were taken
- **Fixed options:**
  - `Yes` (ONLY if explicitly stated actions were performed/completed)
  - `No`
- If only suggested/planned but not performed: return `""`
- If not mentioned: return `""`

**16. Corrective actions description**
- Description: What corrective actions were taken
- Format: Brief keywords only
- If not mentioned: return `""`

**17. Photo mentioned**
- Description: Whether a photo was mentioned/attached
- **Fixed options:**
  - `Yes` (ONLY if explicitly mentioned)
- If not mentioned: return `""`

### Step 4 — Generate Word Document

Before creating the document, view the docx skill:
```
view /mnt/skills/public/docx/SKILL.md
```

## Guardrails

### Critical Rules to Prevent Hallucination:

**MUST DO:**
- Extract ONLY information explicitly mentioned in the transcript
- Use exact field names as specified
- Keep extracted values BRIEF (tight keywords only)
- Return empty string ("") if field not mentioned in transcript
- For fixed-option fields, ONLY select from the predefined lists
- Follow the exact format for each field
- Preserve numbers as digits (not words)

**MUST NOT DO:**
- NEVER invent or hallucinate information not in the transcript
- NEVER add assumptions or interpretations
- NEVER use values outside predefined lists for fixed-option fields
- NEVER create full sentences when "keywords" are requested
- NEVER leave out fields from the output (include all 17 fields)
- NEVER change field names
- NEVER guess dates, numbers, names, or organizations

### Field-Specific Validation:

**Date and Time (Field 7):**
- Must follow format rules exactly
- If transcript says "fifth of April", extract as `05.04`
- If only time is mentioned without date, return `""`

**Fixed-Option Fields:**
- Type of form (field 1): ONLY from 2 options
- Observation type (field 2): ONLY from 3 options
- Positive safety observation (field 3): ONLY `Yes` or `""`
- Reporter organization (field 5): ONLY from 3 options
- Summer employee (field 6): ONLY `Yes`, `No`, or `""`
- Near miss (field 12): ONLY `Yes`, `No`, or `""`
- Direct cause (field 14): ONLY from 16 options
- Corrective actions performed (field 15): ONLY `Yes`, `No`, or `""`
- Photo mentioned (field 17): ONLY `Yes` or `""`

**Location Fields (8, 9, 10):**
- Keep as short as possible
- Building/site: just the building name/number
- Detailed location: just the area within building
- Clarification: minimal additional context

**Description Fields (11, 13, 16):**
- Use ONLY tight keywords
- No full sentences
- No elaboration beyond what's stated

### Error Handling:

**If transcription fails:**
- Report error clearly to user
- Do NOT attempt extraction without transcript
- Provide troubleshooting steps (check file path, file format, etc.)

**If transcript is unclear or ambiguous:**
- Extract what is clear
- Return `""` for unclear fields
- Do NOT guess or make assumptions

**If speaker mentions conflicting information:**
- Use the most explicit or latest mention
- If still uncertain, return `""`

**If fixed-option field doesn't match any option:**
- Return `""` (do not force a match)
- Explain to user why field was left empty

## Examples

### Example 1: Standard Safety Observation

**User prompt:**
"Process this incident report: C:\Reports\safety-obs-2024-03-15.mp3"

**Expected behavior:**
1. Transcribe audio using gaik-transcriber
2. Extract all 17 fields from transcript
3. Return `""` for fields not mentioned
4. Present extracted data to user

### Example 2: Minimal Information

**User prompt:**
"Extract incident data from C:\Audio\report.m4a"

**Expected behavior:**
1. Transcribe audio
2. Extract available fields
3. Return `""` for fields not mentioned
4. Ensure fixed-option fields match allowed values or are empty
5. Present extracted data to user

### Example 3: Missing File Path

**User prompt:**
"Create an incident report from my recording"

**Expected behavior:**
1. Ask user for the audio file path
2. Explain format needed (e.g., `C:\path\to\file.mp3`)
3. Wait for user to provide path
4. Proceed with transcription and extraction once path is provided

## Notes

- The skill focuses on **accurate extraction** over interpretation
- **Never hallucinate** - empty fields are acceptable and expected
- The transcript may contain casual speech, filler words, and unclear audio - extract what is clear
- Fixed-option lists are **closed sets** - do not add values not in the lists
- All field names must be preserved exactly as specified
- Brevity is critical - keep all extracted values as short keywords, not narrative descriptions
