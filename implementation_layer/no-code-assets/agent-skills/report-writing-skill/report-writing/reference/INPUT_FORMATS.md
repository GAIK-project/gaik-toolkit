# Input Formats Reference

Detailed handling instructions for each supported input file type.

## Contents
- Audio/Video Recordings
- Image Files
- Digital Notes
- Supplementary Documents
- Template and Sample Detection

---

## Audio/Video Recordings

### Supported Formats
`.mp3`, `.m4a`, `.wav`, `.ogg`, `.flac`, `.mp4`, `.mov`, `.avi`, `.mkv`, `.webm`

### Processing Method
Use the `gaik-transcriber:transcribe_audio` MCP tool:

```
gaik-transcriber:transcribe_audio
  file_path: "<full_path_to_audio_or_video_file>"
  enhanced: false  # Default. Set to true only if user explicitly requests enhanced/high-quality transcription.
```

**Important notes:**
- The `file_path` must be the full path to the audio/video file
- The MCP server is pre-configured on Claude Desktop

### Output Handling
Preserve the transcribed text without doing any changes. 

### Error Handling
If transcription fails:
1. Log the error message
2. Note in the fused content: `[TRANSCRIPTION FAILED: <filename> - <error>]`
3. Continue processing other files

---

## Image Files

### Supported Formats
`.jpg`, `.jpeg`, `.png`, `.gif`, `.webp`, `.bmp`, `.tiff`, `.heic`

### Types of Image Content

**Handwritten Notes:**
- View the image using the `view` tool
- Transcribe all legible text
- Note illegible portions as `[illegible]`
- Preserve structure (bullets, numbering, arrows indicating relationships)

**Diagrams/Flowcharts:**
- Describe the diagram type (flowchart, org chart, architecture, etc.)
- List all elements/nodes
- Describe connections and relationships
- Note any text labels

**Whiteboard Photos:**
- Transcribe all text content
- Describe any drawings or diagrams
- Note spatial relationships between items
- Capture any indicated priorities (stars, circles, underlines)

**Figures/Charts:**
- Describe the chart type
- Extract data points if readable
- Note axis labels and legends
- Summarize the key insight the figure conveys

### Output Format
```
Image Type: [Handwritten notes / Diagram / Whiteboard / Figure]
Content:
[Interpreted content here]

Visual Elements:
[Description of non-text elements]
```

---

## Notes

### Supported Formats
`.txt`, `.md`, `.rtf`, `.html`

### Processing Method
Read directly without using any specific built-in skill or tool. 

For HTML files, extract text content and preserve structure.

### Preservation
- Keep original formatting (headers, bullets, numbering)
- Preserve emphasis (bold, italic) indicators
- Maintain paragraph structure

---

## Supplementary Documents

### PowerPoint Files (.pptx, .ppt)

**Extraction method:**
Use the built-in/available pptx skill to process `.pptx` and `.ppt` files. 
**IMPORTANT:** DO NOT USE ANY OTHER TOOL EXCEPT THE BUILT-IN `pptx` skill. 

**Content to extract:**
- Slide titles
- Bullet points and text
- Speaker notes (from `ppt/notesSlides/`)
- Table content

**Output format:**
```
SLIDE 1: [Title]
- [Bullet 1]
- [Bullet 2]
Notes: [Speaker notes if present]

SLIDE 2: [Title]
...
```

### PDF Files

**Extraction method:**
Use the built-in/available pdf skill to process to process the `.pdf` files. 
**IMPORTANT:** DO NOT USE ANY OTHER TOOL EXCEPT THE BUILT-IN `pdf` skill. 


### Excel Files 

**Extraction method:**
Use the built-in/available xlsx skill to  process Excel files.
**IMPORTANT:** DO NOT USE ANY OTHER TOOL EXCEPT THE BUILT-IN `xlsx` skill. 

**Interpretation requirements:**
- Describe what the data represents
- Note any totals, summaries, or highlighted values
- Explain relevance to the report context

### Word Documents (.docx)

**Extraction method:**
Use docx skill to process the `.docx` files. 

Preserves:
- Headings and structure
- Lists and tables
- Basic formatting

---

## Template and Sample Detection

### Folder Structure

Templates and samples are stored in dedicated subfolders:

```
<input_folder>/
├── input_documents/     # All source materials go here
├── templates/           # Blank template with structure/formatting
└── sample_documents/    # Sample showing desired style/format/tone
```

### Identifying Templates

Check `<input_folder>/templates/` for:
- Any `.docx` or `.pdf` file (use first one found if multiple exist)

**Template characteristics:**
- Placeholder text like `[Insert here]`, `<Title>`, `{{content}}`
- Empty sections with headers
- Company logos and formatting without substantive content
- Predefined headers, footers, section structure

### Identifying Sample Documents

Check `<input_folder>/sample_documents/` for:
- Any `.docx` or `.pdf` file (use first one found if multiple exist)

**Sample characteristics:**
- Complete document with realistic content
- Consistent formatting throughout
- Clear section structure to emulate
- Demonstrates desired tone and length

### Using Templates and Samples

**When template is found in templates/:**
1. Copy the template file
2. Identify placeholder locations
3. Replace placeholders with extracted content
4. Preserve all formatting, headers, logos

**When sample is found in sample_documents/:**
1. Analyze the sample's structure, tone, and length
2. Match section organization
3. Emulate writing style (formal/informal, bullet vs prose)
4. Match approximate section lengths

**When both are found:**
1. Use template as the base document
2. Apply sample's style to content filling
