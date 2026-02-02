---
name: report-writing
description: Converts scattered documents and media (recordings, notes, diagrams, PDFs, spreadsheets) into structured MS Word reports. Automatically infers appropriate sections from content or follows provided template/sample structure. Use when the user needs to create a report, summarize documents, consolidate materials, generate documentation, or create meeting notes.
---

# Report Writing

Converts scattered materials—audio/video recordings, handwritten notes, diagrams, digital notes, and supplementary documents—into a single, well-formatted MS Word report. The skill automatically infers appropriate sections from content signals or follows a provided template/sample structure.

It is designed to run in **Claude Desktop** with:
- An MCP **filesystem** server (for listing/reading files and folders)
- An MCP **gaik-transcriber** server (for transcribing audio/video recordings)

## When to Use

Use this skill when:
- User needs to create a report, summary, or documentation from source materials
- User mentions "create a report", "generate documentation", "summarize documents"
- User wants to consolidate multiple documents/media into a single structured deliverable
- User has recordings, notes, images, or documents to process into a report
- User needs meeting notes, meeting minutes, or meeting documentation
- User provides a template or sample and wants content filled in
- User asks to "write up" notes, "document this", or create a Word document from materials

## Inputs

**Required (at least one):**
- Audio/video recordings – transcribed using `gaik-transcriber:transcribe_audio`
- Handwritten notes (scanned images) – interpreted visually
- Digital notes (text files, markdown, etc.)
- Diagrams/sketches/figures (images)
- Source documents to synthesize

**Optional:**
- Supplementary documents (PowerPoint slides, PDF documents, Excel files)
- Output template (blank .docx with predefined headers, sections, logos)
- Sample output document (.docx or .pdf) defining style, format, tone, and length

**Required parameter:**
- `input_folder`: Path to the main input folder containing the required subfolder structure. If not provided, ask the user to specify it.

**Required folder structure:**
```
<input_folder>/
├── input_documents/     # Required: recordings, photos, notes, presentations, PDFs, etc.
├── templates/           # Optional: blank template with predefined headers, sections, logos
└── sample_documents/    # Optional: sample document defining style, format, tone, length
```

## Tooling Rules (Windows vs Linux Path Safety)

### Why this matters
On Windows, Claude Desktop + toolchains sometimes behave like they are in a POSIX shell, producing paths like `/mnt/c/...`.
Meanwhile, your MCP servers may run **native Windows Python**, expecting `C:\...`.
This mismatch can cause "file not found" or failing shell commands.

### Strict rules
1) **Prefer MCP filesystem tools for file/folder operations**
Use the filesystem server for listing and reading files instead of shell commands.

2) **Avoid bash commands on Windows**
If you must run a command on Windows, prefer **PowerShell**.

3) **When calling gaik-transcriber, prefer Windows drive-letter paths on Windows**
Pass file paths like `C:\Users\...\recording.m4a`.
If you only have a POSIX/WSL path (e.g., `/mnt/c/...`), convert it to a Windows path before calling the transcriber, or rely on the transcriber server's internal normalization (recommended).

4) **Never assume the environment is Linux**
Treat the runtime as OS-ambiguous and enforce the above rules to stay stable.

5) **Never do the following:**
NEVER run pip install, python -c, pdfplumber, or any ad-hoc parsing code for .pdf/.pptx/.xlsx.

NEVER use /mnt/user-data/uploads/... paths; only use paths returned by the MCP filesystem listing or the user-provided Windows folder.

If you are about to do any of the above, STOP and switch to the built-in PDF/PPTX/XLSX skills.

## Workflow

### Step 0 — Collect context
Ask (only if not provided):
- Report title or purpose (optional but recommended)
- Desired output format (Word document is default)
- Any special focus or sections to emphasize
- Target audience (if relevant)

## Step 1 — Validate input folder structure and capabilities

If the user has not specified an input folder path, ask for it and confirm it contains `input_documents/` (required).

### 1) Validate folder structure (MCP filesystem only)
Use the filesystem MCP tool to list:
- `<input_folder>`
- `<input_folder>\input_documents` (required)
- `<input_folder>\templates` (optional)
- `<input_folder>\sample_documents` (optional)

If `input_documents/` is missing or empty, stop and ask the user to add the source materials there.

### 2) Capability check (prevents Windows/Linux path loops for binaries)
Purpose: decide upfront whether this environment can process **binary** files from a Windows folder without requiring the user to upload them.

Inventory binary files found in:
- `<input_folder>\input_documents`
- `<input_folder>\templates`
- `<input_folder>\sample_documents`

Treat the following as **binary** (not safely readable via text tools):
- `.pdf`, `.pptx`, `.xlsx`, `.docx`

Decision:
- If ANY binary files exist and are ONLY in the Windows folder:
  - Assume you cannot process them directly unless you have a binary-capable tool.
  - The official Node filesystem MCP server supports reading text files and reading image/audio media, but does not guarantee generic binary reads for Office/PDF files.
  - Therefore:
    - If a dedicated MCP document-parser tool is available (recommended), use it for these files.
    - Otherwise, you MUST ask the user to upload/attach these binaries in Claude Desktop to process them with built-in PDF/PPTX/XLSX/DOCX skills.

If the user asks for "local-folder only" processing of PDF/PPTX/XLSX/DOCX:
- Explain that this requires either:
  - a binary-capable filesystem MCP server (supports base64/binary reads), or
  - a Windows-native document-parser MCP server.

Continue with the core workflow (transcription + text notes + images) regardless of the binary handling outcome.

### Step 2 — Inventory input files
From `input_documents/`, create a quick inventory:
- Recordings (audio/video)
- Images (handwritten notes, diagrams)
- Text documents (notes, drafts, emails, etc.)
- PDFs / slides (read text if possible; otherwise summarize)

### Step 3 — Transcribe recordings (gaik-transcriber MCP tool)
For each audio/video file, call:

- `gaik-transcriber:transcribe_audio`
  - `file_path`: full path to the recording
  - `enhanced`: false by default (true only if user asks for enhanced quality)

If transcription fails with "file not found":
- Re-check the path style and ensure Windows drive-letter paths on Windows.

#### Step 4 - Images (Handwritten Notes, Diagrams, Sketches, Figures)
For each image file (.jpg, .jpeg, .png, .gif, .webp, .bmp, .tiff):
1. View the image using the appropriate tool
2. Interpret the image content (handwritten notes, diagrams, figures)
3. Create a textual description capturing all relevant information

#### Step 5 - Notes
Read files directly (.txt, .md, .rtf).
Use /mnt/skills/public/docx/SKILL.md for reading/writing .docx files.

## Step 6 — Supplementary documents (.pdf, .pptx, .xlsx, .docx)

Goal: extract relevant information from supplementary documents WITHOUT ad-hoc parsing code and WITHOUT Windows/Linux path mismatches.

### Non-negotiables (hard rules)
- NEVER run `cp`, `pip install`, `python -c`, `pdfplumber`, `soffice`, `pandoc`, or any ad-hoc parsing commands to read `.pdf/.pptx/.xlsx/.docx` from Windows paths.
- NEVER assume `C:\...` or `/mnt/c/...` is accessible inside a Linux sandbox.
- NEVER invent upload paths (e.g., `/mnt/user-data/uploads/...`) unless the environment explicitly provides them.
- Do not use the filesystem MCP server to "load built-in skill files." The filesystem server is for user-allowed directories, not Claude's internal skill library.

### Decision tree

A) If the supplementary file is uploaded/attached in Claude Desktop
- Use the corresponding built-in skill:
- View /mnt/skills/public/docx/SKILL.md skill for reading and editing DOCX files.
- View /mnt/skills/public/pdf/SKILL.md skill for reading PDF files.
- View /mnt/skills/public/xlsx/SKILL.md skill for reading and editing XLSX files.
- View /mnt/skills/public/pptx/SKILL.md skill for reading and editing PPTX files.

- Extract only relevant content for the report (key data, findings, timelines, etc.).
- Attribute extracted content by filename.

B) If the supplementary file is ONLY present in the Windows folder (discovered via `filesystem:list_directory`)
1) Text-like files (`.txt`, `.md`, `.csv`, `.json`)
- Read via filesystem `read_text_file` and extract relevant content.

2) Binary files (`.pdf`, `.pptx`, `.xlsx`, `.docx`) — IMPORTANT
- Do NOT attempt conversion or parsing via sandbox tools (pandoc/python/soffice/etc.).
- If a dedicated MCP document-parser tool is available:
  - Call the parser using the Windows path and use returned extracted text/tables in synthesis.
- Otherwise:
  - Ask the user to upload/attach the file(s) in Claude Desktop.
  - Continue processing what you can (transcripts, notes, images) and list the missing binaries under "Missing inputs".

Template + samples:
- If templates/sample documents are `.docx/.pdf/.pptx/.xlsx` and are only on Windows disk:
  - Ask the user to upload them.
  - If not provided, proceed with a clean default structure.

### Output handling
- If supplementary binaries are unavailable (not uploaded, and no parser tool), clearly list them:
  - Missing inputs: `<filename1>`, `<filename2>`, ...
- Produce the report using available evidence and a default format.
- Do not block the entire workflow just because supplementary binaries are missing.

### Step 7: Fuse Information

Combine all processed inputs into a single consolidated text block with clear separators:

```
=== TRANSCRIPTION: <filename> ===
<transcribed content>

=== HANDWRITTEN NOTES: <filename> ===
<interpreted content>

=== DIGITAL NOTES: <filename> ===
<note content>

=== DIAGRAM/FIGURE: <filename> ===
<description of diagram/figure>

=== SUPPLEMENTARY: <filename> ===
<extracted content>
```

### Step 7.5: Analyze Content for Section Inference

After fusing all content, analyze it to determine which sections to include in the report.

**Content Signal Detection:**

| Content Signal | Inferred Section |
|----------------|------------------|
| Multiple speakers identified | "Participants/Attendees" in header |
| Explicit decisions ("we decided", "agreed to", "the decision is", "going forward we will") | "Decisions Made" section |
| Assigned tasks with owners ("[Name] will...", "Action:", "TODO:", "assigned to") | "Action Items" table |
| Unresolved questions ("need to figure out", "TBD on", "question is") | "Open Questions" section |
| Data/statistics present (numbers, percentages, measurements) | "Data Summary" or "Findings" section |
| Recommendations mentioned ("recommend", "suggest", "should consider") | "Recommendations" section |
| Timeline/dates discussed (specific dates, milestones, deadlines) | "Timeline" or "Schedule" section |
| Risks/issues mentioned ("risk", "concern", "issue", "blocker", "problem") | "Risks & Issues" section |
| Q&A pattern detected (question-answer exchanges) | "Key Questions & Answers" section |

**Section inclusion rule:** Only include sections where content signals are detected. Never create empty sections or placeholders.

### Step 8: Check for Template and Sample Documents

Check the dedicated subfolders for template and sample:

**Template (`<input_folder>/templates/`):**
- Look for a blank .docx file with predefined structure (headers, sections, logos)
- If multiple files exist, use the first .docx file found

**Sample (`<input_folder>/sample_documents/`):**
- Look for a .docx or .pdf file defining the required style, format, tone, and length
- If multiple files exist, use the first document found

**Priority order for format determination:**
1. **Template provided:** Use template structure exactly, fill in content
2. **Sample provided (no template):** Mirror sample's sections, style, tone, and length
3. **Neither:** Use content-inferred format (see Output Format section)

### Step 9: Generate the Deliverable

Read the docx skill before creating the document:
```
view /mnt/skills/public/docx/SKILL.md
```

Then follow the docx skill's "Creating a new Word document" workflow to generate the output.

**If template provided:** Copy the template and fill in sections according to the template structure.

**If sample provided (no template):** Create a new document mirroring the sample's section structure and style.

**If neither:** Create a new document using the content-inferred output format below.

### Step 10: Save and Present

1. Save the document to the `input_documents` folder
2. Use `present_files` to share with the user

## Output Format (Dynamic - adapts to template, sample, or content)

### When Template Provided
- Copy template exactly
- Fill placeholders with relevant content
- Preserve all formatting, headers, logos
- Do NOT add sections not in template

### When Sample Provided (no template)
- Extract section headings from sample
- Mirror section order and structure
- Match tone and approximate length
- Do NOT add sections not in sample

### When Neither (Content-Inferred Format)

Use this base structure, adding/removing sections based on content signals detected in Step 7.5:

```
REPORT
======

Title: [Extracted or user-provided title]
Date: [Extracted date or generation date]
Prepared by: [If identifiable, otherwise omit]
Participants: [If multiple speakers identified, otherwise omit]

---

SUMMARY
-------
[2-4 paragraph overview of all content. Keep factual and objective.
Cover main topics in order of importance.]

---

KEY POINTS
----------
- [Major point 1]
- [Major point 2]
- [Major point 3]
[Continue as needed, ordered by importance]

---

[CONDITIONAL SECTIONS - include only if content signals detected]

DECISIONS MADE
--------------
[Include only if explicit decisions found in content]
1. [Decision text]
   - Context: [brief context if available]

ACTION ITEMS
------------
[Include only if tasks with owners found in content]
| # | Action Item | Owner | Due Date | Priority |
|---|-------------|-------|----------|----------|
| 1 | [description] | [name] | [date] | [H/M/L] |

[If owner/due date not specified, mark as "TBD"]

OPEN QUESTIONS
--------------
[Include only if unresolved questions found in content]
1. [Question that was raised but not resolved]

DATA/FINDINGS
-------------
[Include only if data, statistics, or analysis results present]
[Summary of key data points and findings]

RECOMMENDATIONS
---------------
[Include only if recommendations/suggestions found in content]
1. [Recommendation]
   - Rationale: [brief explanation if available]

TIMELINE/SCHEDULE
-----------------
[Include only if dates, milestones, or deadlines discussed]
| Milestone | Date | Status |
|-----------|------|--------|

RISKS & ISSUES
--------------
[Include only if risks, concerns, or issues mentioned]
| Risk/Issue | Impact | Mitigation |
|------------|--------|------------|

---

NEXT STEPS
----------
[Include only if actionable follow-up items identified]
- [Action or follow-up 1]
- [Action or follow-up 2]
```

## Guardrails

**Do:**
- Extract information faithfully from provided inputs
- Mark uncertain information as "TBD" or "unclear from source"
- Preserve original terminology and names from the inputs
- STRICTLY follow template/sample format when provided
- Only include sections where relevant content exists in inputs

**Do NOT:**
- Invent or hallucinate any information not present in inputs
- Add content not mentioned in source materials
- Make assumptions about data not explicitly stated
- Include sections if no relevant information exists for them
- Create empty sections with placeholder text like "None" or "N/A"

**If information is missing:**
- For required fields: Mark as "TBD" or "Not specified in source materials"
- For entire sections: Omit the section from the deliverable entirely
- If critical inputs are missing: Inform the user what additional materials would help

**Error handling:**
- If transcription fails: Report the error and continue with other inputs
- If a file cannot be parsed: Log the issue and proceed with remaining files
- If no usable inputs found: Ask the user to verify the folder path and file formats

## Examples

### Example 1: Standard Report with Multiple Inputs

**User prompt:**
"Create a report from the materials in /home/user/projects/analysis"

**Expected folder structure:**
```
/home/user/projects/analysis/
├── input_documents/
│   ├── interview-recording.mp4
│   ├── whiteboard-photo.jpg
│   └── my-notes.txt
├── templates/           # (empty or absent)
└── sample_documents/    # (empty or absent)
```

**Expected behavior:**
1. Validates folder structure, finds input_documents/ with 3 files
2. Transcribes recording using gaik-transcriber
3. Interprets whiteboard photo
4. Reads digital notes
5. Fuses all content with separators
6. Analyzes content for section signals
7. Generates Word document with applicable sections only
8. Saves to outputs and presents to user

### Example 2: With Template

**User prompt:**
"Use the template to create a report from the files in /reports/quarterly"

**Expected folder structure:**
```
/reports/quarterly/
├── input_documents/
│   ├── recording.m4a
│   └── data.xlsx
├── templates/
│   └── company-template.docx
└── sample_documents/    # (empty or absent)
```

**Expected behavior:**
1. Finds template in templates/ subfolder
2. Processes all materials in input_documents/
3. Copies the template and fills in content
4. Preserves template's structure, logos, and headers
5. Presents formatted document

### Example 3: With Sample (Style Guide)

**User prompt:**
"Create a document like the sample from /docs/client-report"

**Expected folder structure:**
```
/docs/client-report/
├── input_documents/
│   ├── call-recording.m4a
│   └── notes.md
├── templates/           # (empty or absent)
└── sample_documents/
    └── previous-report.docx
```

**Expected behavior:**
1. Finds sample in sample_documents/ subfolder
2. Analyzes sample's sections, style, tone, and length
3. Processes all materials in input_documents/
4. Creates document mirroring sample's structure
5. Matches sample's tone and approximate length

### Example 4: Minimal Input

**User prompt:**
"I just have a voice memo - can you create a summary? The folder is /recordings/client-call"

**Expected folder structure:**
```
/recordings/client-call/
├── input_documents/
│   └── voice-memo.m4a
├── templates/           # (empty or absent)
└── sample_documents/    # (empty or absent)
```

**Expected behavior:**
1. Validates structure, finds single audio file in input_documents/
2. Transcribes the audio file
3. Analyzes content for section signals
4. Generates deliverable with applicable sections only
5. Omits sections where no information exists

## References
Following these reference documents for detailed handling for each input file type, and guidance on each deliverable section.
- `reference/INPUT_FORMATS.md` – Detailed handling for each input file type
- `reference/OUTPUT_SECTIONS.md` – Guidance on each deliverable section
