# Report Writing Skill for Claude Desktop

Turn your scattered documents, recordings, and notes into professional Word reports — automatically.

![Report Writing Skill](images/img.png)

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
| Audio/Video | `.mp3`, `.m4a`, `.wav`, `.mp4`, `.mov`, `.avi`, and more |
| Images | `.jpg`, `.png`, `.gif`, `.webp`, `.bmp`, `.tiff` |
| Documents | `.pdf`, `.docx`, `.pptx`, `.xlsx` |
| Notes | `.txt`, `.md`, `.rtf`, `.html` |

---

## Prerequisites

Before setting up, please install:

1. **Claude Desktop** — Download from [claude.ai/download](https://claude.ai/download)
2. **Python 3.8+** — Download from [python.org](https://www.python.org/downloads/)
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
   - Enter your API key when asked

**Step 2: Configure Claude Desktop**

The script will create a configuration file. You need to copy it to Claude Desktop:

1. Open the generated file `claude_desktop_config.json` (the script offers to open it)
2. Copy all the content
3. Open Claude Desktop's config file:
   - Press `Win + R`
   - Paste: `%APPDATA%\Claude\claude_desktop_config.json`
   - Press Enter
4. Paste the content and save

**Step 3: Restart Claude Desktop**

1. Close Claude Desktop completely (check the system tray icon)
2. Open Task Manager and end any "Claude" processes
3. Start Claude Desktop again

**Step 4: Install the Skill**

1. Open Claude Desktop
2. Click the **Settings** icon (gear) → **Capabilities**
3. Click **"+ Add"**
4. Select the `report-writing.zip` file (created by the setup script)

✅ **Setup complete!** You're ready to use the skill.

---

### Option B: Manual Setup

If you prefer to set things up yourself:

**Step 1: Install Python Dependencies**

Open Command Prompt and run:
```
pip install fastmcp gaik[transcriber] python-dotenv
```

**Step 2: Configure API Key**

Create a file named `.env` in the `transcription-MCP` folder with:

For **OpenAI**:
```
OPENAI_API_KEY=your_api_key_here
OPENAI_API_TYPE=openai
```

For **Azure OpenAI**:
```
AZURE_API_KEY=your_api_key_here
AZURE_ENDPOINT=your_endpoint_url
AZURE_DEPLOYMENT=your_whisper_deployment
OPENAI_API_TYPE=azure
```

**Step 3: Configure Claude Desktop**

Open `%APPDATA%\Claude\claude_desktop_config.json` and add:

```json
{
  "mcpServers": {
    "gaik-transcriber": {
      "command": "python",
      "args": ["C:\\path\\to\\report-writing-skill\\transcription-MCP\\server.py"],
      "timeout": 600000
    },
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "C:\\"]
    }
  }
}
```

**Important:** Replace `C:\\path\\to\\` with the actual path where you saved this folder.

**Step 4: Install the Skill**

1. Zip the `report-writing` folder
2. Open Claude Desktop → Settings → Capabilities → + Add
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

- Check your API key in the `.env` file
- Ensure you have an active OpenAI account with credits
- Try a smaller audio file first to test

### "File not found" errors

- Use the full Windows path (e.g., `C:\Users\...`)
- Make sure your files are in `input_documents/` subfolder
- Check that the folder path has no typos

### Claude doesn't recognize the skill

- Go to Settings → Capabilities and verify the skill is listed
- Try removing and re-adding the skill
- Restart Claude Desktop

---

## Sample Data for Testing

The `sample_data/` folder contains example files you can use to test the skill:

| File | Description |
|------|-------------|
| `input_documents/meeting_recording.mp3` | Sample audio recording |
| `input_documents/sketch.png` | Handwritten notes image |
| `input_documents/notes.txt` | Text notes |
| `input_documents/roadmap-presentation.pptx` | PowerPoint slides |
| `input_documents/project-budget.xlsx` | Excel spreadsheet |
| `input_documents/deployment-freeze-policy.pdf` | PDF document |
| `templates/meeting-template.docx` | Sample template |
| `sample_documents/sample-meeting-minutes.docx` | Sample output format |

**Try it:**
```
Create a report from C:\path\to\report-writing-skill\sample_data
```

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
report-writing-skill/
├── setup.bat                 # Setup wizard script
├── report-writing/           # Claude skill definition
│   ├── SKILL.md              # Main workflow specification
│   ├── EVALUATION.md         # Test scenarios
│   └── reference/            # Detailed handling guides
├── transcription-MCP/        # Audio transcription server
│   ├── server.py             # FastMCP implementation
│   └── .env                  # API configuration
└── sample_data/              # Example files for testing
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

- **Python packages:** `fastmcp`, `gaik[transcriber]`, `python-dotenv`
- **Node.js packages:** `@modelcontextprotocol/server-filesystem`
- **External APIs:** OpenAI Whisper API (for audio transcription)
