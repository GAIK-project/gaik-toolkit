# Evaluation Prompts

Test prompts for validating the report-writing skill.

---

## Eval 1: Multi-Input with Content Inference

**Prompt:**
"Create a report from the materials in /projects/analysis - there's a recording, some photos, and my typed notes."

**Folder structure needed:**
```
/projects/analysis/
├── input_documents/
│   ├── recording.mp4
│   ├── whiteboard1.jpg
│   ├── whiteboard2.jpg
│   └── notes.txt
├── templates/           # (empty)
└── sample_documents/    # (empty)
```

**Pass Criteria:**
- Validates folder structure before processing
- Finds and processes files in input_documents/ subfolder
- Calls `gaik-transcriber:transcribe_audio` MCP tool for transcribing audio/video
- Views and interprets both image files
- Reads the text notes file
- Creates fused content with clear separators between sources
- Analyzes content for section signals (decisions, action items, data, etc.)
- Generates Word document with applicable sections only
- Saves to the input folder and presents file
- Does NOT include sections for which no content signals exist

**Failure Modes:**
- Looks for files in root folder instead of `input_documents/`
- Skips the transcription step
- Ignores image files
- Invents content not in source materials
- Includes empty sections with placeholder text
- Fails to present the final file

---

## Eval 2: Template-Driven Report

**Prompt:**
"Use the template to create a report from the materials in /docs/quarterly. There's also a sample showing how we like them formatted."

**Folder structure needed:**
```
/docs/quarterly/
├── input_documents/
│   ├── recording.m4a
│   └── slides.pptx
├── templates/
│   └── company-template.docx
└── sample_documents/
    └── sample-q3-report.docx
```

**Pass Criteria:**
- Validates folder structure
- Finds template in templates/ subfolder
- Finds sample in sample_documents/ subfolder
- Processes files in input_documents/ (recording and slides)
- Copies the template (doesn't create from scratch)
- Analyzes sample for style, tone, and length
- Fills template following sample's format
- Preserves template's logos and headers
- Final document matches sample's structure and tone

**Failure Modes:**
- Ignores templates/ subfolder and creates new document
- Ignores sample_documents/ subfolder
- Looks for template/sample in input_documents/
- Corrupts template formatting
- Mixes template with default output format
- Adds sections not in template

---

## Eval 3: Sample-Style Matching (No Template)

**Prompt:**
"Create a document like the sample from /reports/client-summary"

**Folder structure needed:**
```
/reports/client-summary/
├── input_documents/
│   ├── call-recording.m4a
│   └── notes.md
├── templates/           # (empty)
└── sample_documents/
    └── previous-report.docx
```

**Pass Criteria:**
- Finds sample in sample_documents/ subfolder
- Analyzes sample's sections, style, tone, and length
- Processes all materials in input_documents/
- Creates document mirroring sample's section structure
- Matches sample's tone and approximate length
- Does NOT add sections not present in sample

**Failure Modes:**
- Ignores sample and uses default format
- Only copies style, ignores section organization
- Adds sections not in sample
- Drastically different length than sample

---

## Eval 4: Minimal Input (Audio Only)

**Prompt:**
"I just have a voice memo - can you create a summary? The folder is /recordings/client-call"

**Folder structure needed:**
```
/recordings/client-call/
├── input_documents/
│   └── voice-memo.m4a
├── templates/           # (empty or absent)
└── sample_documents/    # (empty or absent)
```

**Pass Criteria:**
- Handles single-file input gracefully
- Correctly locates file in `input_documents/` subfolder
- Successfully transcribes the audio
- Creates Word document with available sections only
- Omits sections where no content signals exist
- Acknowledges any limitations in the output

**Failure Modes:**
- Fails without multiple inputs
- Looks for audio file in root folder
- Invents content to fill all sections
- Includes empty sections with "None" or "N/A"
- Produces generic boilerplate unrelated to actual content

---

## Eval 5: Error Recovery

**Prompt:**
"Process the files in /docs/project-update"

**Folder structure needed:**
```
/docs/project-update/
├── input_documents/
│   ├── recording.mp4       # (corrupted or unreadable)
│   ├── notes.md
│   └── diagram.png
├── templates/           # (empty)
└── sample_documents/    # (empty)
```

**Pass Criteria:**
- Validates folder structure correctly
- Attempts transcription and handles failure gracefully
- Reports the transcription error clearly
- Continues processing other valid files in input_documents/
- Generates document from available content
- Notes in output that transcription failed

**Failure Modes:**
- Crashes on transcription failure
- Abandons all processing after one error
- Silent failure (produces document without mentioning issue)
- Claims transcription succeeded when it didn't

---

## Eval 6: Missing Input Folder

**Prompt:**
"Create a report from my documents"

**Pass Criteria:**
- Recognizes no folder path provided
- Asks user for the folder path
- Explains required folder structure (input_documents/, templates/, sample_documents/)
- Does NOT guess or assume a path
- Proceeds correctly once valid path with correct structure is provided

**Failure Modes:**
- Attempts to process without valid path
- Makes up a folder path
- Does not explain the required subfolder structure
- Crashes or produces error without guidance

---

## Eval 7: Content with Decisions & Action Items

**Prompt:**
"Summarize this planning session from /projects/planning"

**Folder structure needed:**
```
/projects/planning/
├── input_documents/
│   ├── planning-session.mp3
│   └── notes.txt
├── templates/           # (empty)
└── sample_documents/    # (empty)
```

**Content should include:**
- Explicit decisions ("We decided to...", "The team agreed...")
- Action items with owners ("John will...", "Sarah needs to...")
- Some open questions ("We need to figure out...")

**Pass Criteria:**
- Detects decision signals and includes "Decisions Made" section
- Detects task assignments and includes "Action Items" table
- Detects open questions and includes "Open Questions" section
- Does NOT include sections without content signals (e.g., no Data/Findings if no data)

**Failure Modes:**
- Uses fixed template regardless of content
- Misses decision or action item signals
- Includes all sections with placeholders
- Invents decisions or actions not in source

---

## Eval 8: Data-Heavy Content

**Prompt:**
"Create a report from /research/findings"

**Folder structure needed:**
```
/research/findings/
├── input_documents/
│   ├── data-analysis.xlsx
│   ├── survey-results.pdf
│   └── field-notes.txt
├── templates/           # (empty)
└── sample_documents/    # (empty)
```

**Content characteristics:**
- Heavy on data, statistics, percentages
- Contains findings and recommendations
- No explicit decisions or action items with owners

**Pass Criteria:**
- Includes "Data/Findings" section with key statistics
- Includes "Recommendations" section if recommendations found
- Does NOT include "Decisions Made" section (no decision signals)
- Does NOT include "Action Items" section (no task assignments)
- Synthesizes data from multiple sources coherently

**Failure Modes:**
- Ignores Excel data
- Includes entire Excel content verbatim
- Adds Action Items or Decisions sections without signals
- Fails to extract meaningful data points

---

## Notes for Testing

### Test Environment Setup
1. Create test folders with the required subfolder structure:
   ```
   <test_folder>/
   ├── input_documents/   # Place test files here
   ├── templates/         # Place template here (if testing)
   └── sample_documents/  # Place sample here (if testing)
   ```
2. Ensure `gaik-transcriber` MCP server is running
3. Have sample template and sample output documents ready for Eval 2

### Model-Specific Considerations
- **Haiku**: May need simpler prompts; verify all steps are followed
- **Sonnet**: Expected primary model; full workflow should execute
- **Opus**: Test with complex multi-file scenarios

### Common Issues to Watch
- Failure to call gaik-transcriber (critical for audio processing)
- Looking for files in root folder instead of input_documents/
- Looking for template/sample in input_documents/ instead of their subfolders
- Inventing content not in source materials
- Including empty sections instead of omitting them
- Not using template when provided
- Forgetting to present final file to user
- Including sections without content signals (e.g., Action Items when no tasks assigned)
- Ignoring template/sample structure when provided
