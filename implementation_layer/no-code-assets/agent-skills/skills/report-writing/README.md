# Report Writing Skill for Claude Desktop

Turn your scattered documents, recordings, and notes into professional Word reports — automatically.

---

## What Does This Skill Do?

This skill helps you **create structured reports** from multiple sources without manual copy-pasting. Simply point Claude to a folder containing your materials, and it will:

- **Transcribe** audio and video recordings
- **Read** handwritten notes from photos
- **Extract** content from PDFs, PowerPoint, Excel, and Word files
- **Combine** everything into a single, well-formatted Word document

### Example Use Cases

| Scenario | Input | Output |
|----------|-------|--------|
| Meeting documentation | Recording + whiteboard photos + notes | Meeting minutes with action items |
| Research summary | Interview recordings + data files | Research report with findings |
| Project update | Status documents + presentations | Executive summary |
| Client deliverable | Multiple source documents | Formatted report on your template |

### Supported File Types

| Type | Formats |
|------|---------|
| Audio/Video | `.mp3`, `.m4a`, `.wav`, `.ogg`, `.flac`, `.webm`, `.mp4`, `.mpeg`, `.mpga` |
| Images | `.jpg`, `.jpeg`, `.png`, `.gif`, `.webp` |
| Documents | `.pdf`, `.docx`, `.pptx`, `.xlsx` |
| Notes | `.txt`, `.md`, `.rtf`, `.html` |

---

## Prerequisites

Before setting up, please install:

1. **Claude Desktop** — Download from [claude.ai/download](https://claude.ai/download)
2. **Python 3.11+** — Download from [python.org](https://www.python.org/downloads/)
   - During installation, check **"Add Python to PATH"**
3. **Node.js** — Download from [nodejs.org](https://nodejs.org/)
4. **OpenAI API Key** (for audio transcription) — Get from [platform.openai.com/api-keys](https://platform.openai.com/api-keys)

---

## Setup

### Option A: Easy Setup (Recommended)

Use our setup script to configure everything automatically.

**Step 1: Run the Setup Script**

1. Double-click `setup.bat` in this folder
2. Follow the on-screen prompts:
   - Choose your API provider (OpenAI or Azure)
   - Enter your API key (it is saved as your user environment variable, not in a file)
   - Choose the folder Claude may work on, and keep your recordings there

**Step 2: Configure Claude Desktop**

The script will create a configuration file. You need to copy it to Claude Desktop:

1. Open the generated file `claude_desktop_config.json` (the script offers to open it)
2. Open Claude Desktop's config file:
   - Press `Win + R`
   - Paste: `%APPDATA%\Claude\claude_desktop_config.json`
   - Press Enter
3. If that file is missing or empty, paste the whole generated content. Otherwise add only the `"gaik-transcriber": {...}` entry to its existing `"mcpServers"` object, keep everything else, and save.

**Step 3: Restart Claude Desktop**

1. Close Claude Desktop completely (check the system tray icon)
2. Open Task Manager and end any "Claude" processes
3. Start Claude Desktop again

**Step 4: Install the Skill**

1. Open Claude Desktop
2. Open **Customize** → **Skills**
3. Click **Add** → **Upload skill**
4. Select the `report-writing.zip` file (created by the setup script)

✅ **Setup complete!** You're ready to use the skill.

---

### Option B: Manual Setup

If you prefer to set things up yourself:

**Step 1: Install Python Dependencies**

Open Command Prompt and run:
```
python -m venv transcription-MCP\.venv
transcription-MCP\.venv\Scripts\python.exe -m pip install mcp==1.30.0 "gaik[transcriber]==0.11.1" python-dotenv==1.2.4
```

**Step 2: Configure API Key**

Save the key as a user environment variable, not in a file. Open Command Prompt and run
(for **OpenAI**):
```
setx OPENAI_API_KEY "your_api_key_here"
```
For **Azure OpenAI**, save `AZURE_API_KEY` the same way and put the endpoint and deployment
in the server's `env` settings below. On Windows the transcriber reads a key that is missing
from its own environment from your user environment variables, so the key need not be in
`claude_desktop_config.json`.

**Step 3: Configure Claude Desktop**

Open `%APPDATA%\Claude\claude_desktop_config.json` and add:

```json
{
  "mcpServers": {
    "gaik-transcriber": {
      "command": "C:\\path\\to\\report-writing\\transcription-MCP\\.venv\\Scripts\\python.exe",
      "args": ["C:\\path\\to\\report-writing\\transcription-MCP\\server.py",
               "--folder", "C:\\Users\\you\\Documents\\GAIK"],
      "env": {"OPENAI_API_TYPE": "openai"},
      "timeout": 600000
    },
    "filesystem": {
      "command": "node",
      "args": ["C:\\path\\to\\report-writing\\filesystem-MCP\\node_modules\\@modelcontextprotocol\\server-filesystem\\dist\\index.js",
               "C:\\Users\\you\\Documents\\GAIK"]
    }
  }
}
```

Install the file access server first: in the `filesystem-MCP` folder run
`npm ci --omit=dev --ignore-scripts`, which checks every package against the integrity
hash pinned in `package-lock.json`.

**Important:** Replace `C:\\path\\to\\` with the actual path where you saved this folder,
and `C:\\Users\\you\\Documents\\GAIK` with the folder Claude may work on. Both servers
work only inside that folder; never give a whole drive such as `C:\\`.

For Azure OpenAI, `env` holds `"OPENAI_API_TYPE": "azure"`, `AZURE_ENDPOINT` and `AZURE_TRANSCRIPTION_MODEL` instead.
The folder must not be a whole drive, your whole user folder or a folder that holds this one.

**Step 4: Install the Skill**

1. Zip `SKILL.md`, `EVALUATION.md` and the `reference` folder
2. Open Claude Desktop → Customize → Skills → Add → Upload skill
3. Upload the zip file

**Step 5: Restart Claude Desktop**

Close and reopen Claude Desktop to apply changes.

---

## How to Use

### Step 1: Organize Your Documents

Create a folder with this structure:

```
My-Report/
├── input_documents/      ← Put your source files here (REQUIRED)
├── templates/            ← Put your template here (OPTIONAL)
└── sample_documents/     ← Put a sample report here (OPTIONAL)
```

**Required:** At least one file in `input_documents/`

**Optional:**
- `templates/` — A blank Word template with your preferred structure/formatting
- `sample_documents/` — An example report showing your desired style and tone

### Step 2: Ask Claude to Create the Report

In Claude Desktop, simply say:

```
Create a report from the materials in C:\Users\YourName\Documents\My-Report using report-writing skill
```

Or be more specific:

```
Process the documents in C:\Projects\Team-Meeting using report-writing skill, focusing on action items and decisions
```

*A quicker (and better) method is to upload all files (except audio file) to Claude Desktop (preferrably a zip file of the same zip folder), and provide the path to the audio file (if any) explicitly.*

```
Process the documents in C:\Projects\Team-Meeting using report-writing skill. In addition to these documents, read one more audio file from local drive C:\Downloads\meeting_recording.mp3.

```

### Step 3: Get Your Report

Claude will:
1. Process all your files
2. Create a Word document with the appropriate sections
3. Save it in your `input_documents` folder
4. Present it to you for download

---

## Examples

### Example 1: Basic Report

**Your request:**
```
Create a report from C:\Work\Project-Update
```

**Your folder:**
```
Project-Update/
└── input_documents/
    ├── meeting-recording.mp4
    ├── my-notes.txt
    └── status-slide.pptx
```

**Result:** A Word document with Summary, Key Points, and any detected Decisions or Action Items.

---

### Example 2: Report with Template

**Your request:**
```
Use our company template to create a report from C:\Work\Quarterly-Review
```

**Your folder:**
```
Quarterly-Review/
├── input_documents/
│   ├── review-call.m4a
│   └── data.xlsx
└── templates/
    └── company-report-template.docx   ← Your branded template
```

**Result:** Your template filled in with extracted content.

---

### Example 3: Match a Previous Report's Style

**Your request:**
```
Create a report like last month's from C:\Reports\February using report-writing skill
```

**Your folder:**
```
February/
├── input_documents/
│   └── interview.mp3
└── sample_documents/
    └── january-report.docx   ← Example to follow
```

**Result:** A new report matching the style, tone, and structure of your sample.

---

## What Gets Included in the Report?

The skill automatically detects what sections to include based on your content:

| If your content contains... | The report will include... |
|----------------------------|---------------------------|
| Multiple speakers | Participants list |
| "We decided...", "Agreed to..." | Decisions Made section |
| "John will...", "Action item:" | Action Items table |
| Unanswered questions | Open Questions section |
| Numbers, statistics | Data/Findings section |
| "We recommend...", "Should consider..." | Recommendations section |
| Dates, deadlines | Timeline section |
| "Risk", "issue", "blocker" | Risks & Issues section |

**Note:** Sections are only included if relevant content is found. Empty sections are never created.

---

## Troubleshooting

### "MCP server not found" error

- Make sure Claude Desktop is fully closed (check system tray)
- Verify the path in `claude_desktop_config.json` is correct
- Restart Claude Desktop

### Audio transcription not working

- Check that the key is saved without showing it: in a new Command Prompt run
  `powershell -c "[bool][Environment]::GetEnvironmentVariable('OPENAI_API_KEY','User')"`
  (or `AZURE_API_KEY`); `False` means it is missing, so run `setup.bat` again
- The transcriber only takes audio and video files inside the folder you chose in setup
  (`--folder` in `claude_desktop_config.json`); move the recording there
- The key is a user environment variable, so other programs you run can read it too; use a
  key made for this skill, and remove it when you stop using it:
  `reg delete HKCU\Environment /v OPENAI_API_KEY /f`
- Ensure you have an active OpenAI account with credits
- Try a smaller audio file first to test

### "File not found" errors

- Use the full Windows path (e.g., `C:\Users\...`)
- Make sure your files are in `input_documents/` subfolder
- Check that the folder path has no typos

### Claude doesn't recognize the skill

- Go to Customize → Skills and verify the skill is listed
- Try removing and re-adding the skill
- Restart Claude Desktop

---

## Sample Data for Testing

The repository has a synthetic dataset you can use to test the skill: a fictional house
condition assessment with three recordings, PDF and Word reports, a spreadsheet and a floor
plan. Download the folder
[`house_condition_assessment/inputs`](https://github.com/GAIK-project/gaik-toolkit/tree/main/implementation_layer/examples/software_modules/report_writer/house_condition_assessment/inputs)
and, if you want, `sample_report.docx` one level up as the style sample.

| File | Description |
|------|-------------|
| `rec1_exterior_attic.mp3`, `rec2_interior_wet_rooms.mp3`, `rec3_building_services.mp3` | Inspection recordings |
| `renovation_report_1998.pdf`, `roof_renovation_2012.pdf` | Earlier renovation reports |
| `moisture_survey_2019.docx` | Word document |
| `maintenance_log.xlsx` | Excel spreadsheet |
| `floor_plan.png` | Image |

**Try it:**
```
Create a house condition report from C:\path\to\inputs
```

[`expected_behaviours.md`](https://github.com/GAIK-project/gaik-toolkit/blob/main/implementation_layer/examples/software_modules/report_writer/house_condition_assessment/expected_behaviours.md)
lists what a good report does with these sources.

---

## Tips for Best Results

1. **Name files descriptively** — `budget-discussion.mp3` is better than `recording1.mp3`
2. **Use high-quality recordings** — Clear audio produces better transcriptions
3. **Provide a template** — If you need specific formatting or branding
4. **Provide a sample** — If you want a particular style or tone
5. **Be specific in your request** — Mention focus areas like "focus on action items"

---

## Getting Help

- **Full article:** [Medium - Building this Claude Skill](https://medium.com/@umairali.khan/i-created-a-claude-skill-that-turns-piles-of-messy-documents-media-into-a-structured-report-19e9950f93b2)
- **Issues:** Create an issue in the GitHub repository

---

## Technical Details

For developers and advanced users interested in how this works:

### Project Structure

```
report-writing/
├── setup.bat                 # Setup wizard script
├── SKILL.md                  # Claude skill definition: main workflow
├── EVALUATION.md             # Test scenarios
├── reference/                # Detailed handling guides
├── filesystem-MCP/           # File access server, pinned in package-lock.json
└── transcription-MCP/        # Audio transcription server
    ├── server.py             # FastMCP implementation
    └── .venv/                # the transcriber's own Python (created by setup.bat)
```

### How It Works

1. **Skill invocation** — Claude loads the skill when you mention report-related keywords
2. **File discovery** — Uses MCP filesystem server to list files in your folder
3. **Content extraction** — Each file type is processed appropriately:
   - Audio/video → MCP transcription server → text
   - Images → Claude's vision capability → text description
   - Documents → Built-in skills (PDF, PPTX, XLSX, DOCX)
4. **Content fusion** — All extracted text is combined with clear source markers
5. **Section inference** — Content is analyzed for signals (decisions, actions, etc.)
6. **Report generation** — Word document created using template/sample/default structure

### Dependencies

- **Python packages:** `mcp==1.30.0`, `gaik[transcriber]==0.11.1`, `python-dotenv==1.2.4`
- **Node.js packages:** `@modelcontextprotocol/server-filesystem@2026.8.31`, installed with
  `npm ci` from `filesystem-MCP/package-lock.json` (pinned versions and integrity hashes)
- **External APIs:** OpenAI Whisper API (for audio transcription)
