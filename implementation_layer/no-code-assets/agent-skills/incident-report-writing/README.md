# Incident Report Writing Skill for Claude Desktop

Transform workplace incident and safety observation audio recordings into structured JSON reports — automatically.

---

## What Does This Skill Do?

This skill extracts structured information from employee or supervisor audio recordings describing incidents, near misses, safety observations, or safety initiatives. Simply provide an audio file, and Claude will:

- **Transcribe** the audio recording using Whisper AI
- **Extract** 17 standardized fields for incident reporting
- **Generate** a formatted JSON document with all extracted data
- **Validate** data against predefined fixed-option lists

### Extracted Fields

The skill extracts essential incident report information including:
- Report type (Safety observation, Safety-related initiative)
- Reporter details (Name, Organization, Summer employee status)
- Event details (Date/time, Location, Description)
- Safety classification (Observation type, Positive observation, Near miss)
- Root cause analysis (Direct cause selection from 16 categories)
- Response actions (Corrective actions performed and described)
- Documentation (Photo mentioned)

### Supported Audio Formats

`.mp3`, `.m4a`, `.wav`, `.ogg`, `.flac`, `.mp4`, `.mov`, `.avi`, `.mkv`, `.webm`

---

## Prerequisites

Before setting up, please install:

1. **Claude Desktop** — Download from [claude.ai/download](https://claude.ai/download)
2. **Python 3.8+** — Download from [python.org](https://www.python.org/downloads/)
   - During installation, check **"Add Python to PATH"**
3. **OpenAI API Key** (REQUIRED for transcription) — Get from [platform.openai.com/api-keys](https://platform.openai.com/api-keys)

---

## Setup

### Quick Setup (5 Minutes)

**Step 1: Run the Setup Script**

1. Double-click `setup.bat` in this folder
2. Follow the prompts:
   - Choose your API provider (OpenAI or Azure OpenAI)
   - Enter your API key

**Step 2: Configure Claude Desktop**

1. The script creates `claude_desktop_config.json` — open it when prompted
2. Copy all the content
3. Press `Win + R`, paste: `%APPDATA%\Claude\claude_desktop_config.json`, press Enter
4. Paste the content and save

**Step 3: Restart Claude Desktop**

1. Close Claude Desktop completely (check system tray)
2. Open Task Manager and end any "Claude" processes
3. Start Claude Desktop again

**Step 4: Install the Skill**

1. Open Claude Desktop
2. Settings (gear icon) → **Capabilities** → **+ Add**
3. Upload `incident-report-writing.zip` (created by setup script)

✅ **Setup complete!**

---

## How to Use

Simply provide the audio file path to Claude:

```
Process incident report from C:\path\to\your\audio-file.mp3 using incident-report-writing skill.
```

### What Happens Next

1. Claude transcribes the audio
2. Extracts 17 fields from the transcript
3. Creates a JSON document with all extracted data
4. Validates data against fixed-option lists
5. Presents the JSON output

---

## Example Output

The generated JSON contains:

```json
{
  "type_of_form": "Safety observation",
  "observation_type": "Safety",
  "positive_safety_observation": "",
  "reporter_name": "John Smith",
  "reporter_organization": "Luvata Pori Oy",
  "summer_employee": "No",
  "event_date_and_time": "15.03.2024 14:30",
  "building_or_site": "Building A",
  "detailed_location": "Assembly line 3",
  "location_clarification": "near welding station",
  "event_description": "Loose cables on floor",
  "near_miss": "Yes",
  "possible_consequences": "Trip hazard, potential fall",
  "direct_cause_of_the_event": "5S",
  "corrective_actions_performed": "Yes",
  "corrective_actions_description": "Cables secured, area cleaned",
  "photo_mentioned": "Yes"
}
```

**Key Features:**
- Fields not mentioned in audio are left empty (no guessing)
- Fixed-option fields are validated against predefined lists
- Brief, factual extraction with tight keywords
- JSON format ready for system integration
- Date/time formatting with zero-padding

---

## Sample Data

Test the skill with included sample audio:

| File | Description |
|------|-------------|
| `data/Sample 1.m4a` | Incident report recording |
| `data/Sample 2.m4a` | Safety observation recording |

**Try it:**
```
Process incident report from [path-to-folder]\data\Sample 1.m4a
```

---

## Field Specifications

### Fixed-Option Fields

The following fields only accept specific predefined values:

**Type of form:**
- Safety observation
- Safety-related initiative

**Observation type:**
- Safety
- Environmental protection
- Energy efficiency

**Reporter organization:**
- Luvata Pori Oy
- Luvata Oy
- Other

**Direct cause of the event:**
- 5S
- Technical failure
- Protective devices on machines
- Maintenance
- Tools and devices
- Work methods and instructions
- Work guidance / induction / training
- Following instructions and common standards
- Information flow / lack of information flow
- Working conditions
- Weather conditions
- Traffic
- First-aid supplies (used / shortages)
- PPE
- Hurry / insufficient resources
- Human / organizational factor

**Yes/No Fields:**
- Summer employee
- Near miss
- Corrective actions performed

**Yes-Only Fields:**
- Positive safety observation (only set if explicitly positive)
- Photo mentioned (only set if explicitly mentioned)

### Date/Time Format

- Both date and time: `dd.mm.yyyy HH:MM`
- Date only: `dd.mm.yyyy`
- If year not mentioned: `dd.mm`
- Zero-padded: `5.4` becomes `05.04`

---

## Troubleshooting

### "MCP server not found" error
- Ensure Claude Desktop is fully closed (check system tray)
- Verify the path in `claude_desktop_config.json` is correct
- Restart Claude Desktop

### Audio transcription not working
- Check your API key in `transcription-MCP\.env`
- Verify you have OpenAI credits available
- Test with a smaller audio file first

### Empty or incorrect fields
- The skill only extracts explicitly mentioned information
- If fields are empty, the information wasn't in the audio
- Fixed-option fields only accept predefined values (see SKILL.md)

### Fixed-option fields showing empty
- Ensure the transcript explicitly mentions the exact option
- The skill will not guess or infer fixed-option values
- Check SKILL.md for the complete list of allowed values

---

## Manual Setup (Alternative)

If you prefer manual configuration:

**Install Dependencies:**
```bash
pip install fastmcp gaik[transcriber] python-dotenv
```

**Configure API Key:**

Create `transcription-MCP\.env`:
```
OPENAI_API_KEY=your_api_key_here
OPENAI_API_TYPE=openai
```

**Configure Claude Desktop:**

Edit `%APPDATA%\Claude\claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "gaik-transcriber": {
      "command": "python",
      "args": ["C:\\path\\to\\incident-report-writing\\transcription-MCP\\server.py"],
      "timeout": 600000
    }
  }
}
```

**Install Skill:**
1. Zip the `incident-report-writing` folder (inner one with SKILL.md)
2. Upload to Claude Desktop: Settings → Capabilities → + Add

---

## Technical Details

### Project Structure

```
incident-report-writing/
├── setup.bat                      # Automated setup wizard
├── incident-report-writing/       # Skill definition
│   └── SKILL.md                   # Extraction workflow & field specifications
├── transcription-MCP/             # Audio transcription MCP server
│   ├── server.py                  # FastMCP server implementation
│   └── .env                       # API credentials
└── data/                          # Sample audio files
    ├── Sample 1.m4a
    └── Sample 2.m4a
```

### How It Works

1. **MCP Server Launch** — Claude Desktop starts `transcription-MCP/server.py` as a background process
2. **Skill Invocation** — User provides audio file path
3. **Transcription** — MCP server calls OpenAI Whisper API to transcribe audio
4. **Extraction** — Claude analyzes transcript and extracts 17 structured fields
5. **Validation** — Fixed-option fields validated against predefined lists
6. **JSON Generation** — JSON document created with all extracted data
7. **Presentation** — JSON output presented to user

### Dependencies

- **Python packages:** `fastmcp`, `gaik[transcriber]`, `python-dotenv`
- **External APIs:** OpenAI Whisper API (for audio transcription)

### Anti-Hallucination Design

The skill includes extensive guardrails to prevent AI hallucination:
- Only extracts explicitly mentioned information
- Returns empty strings for unmentioned fields
- Validates fixed-option fields against closed lists
- Keeps extracted values brief (keywords only)
- No inference, assumptions, or guessing

## Getting Help

- **GitHub Issues** — Report bugs or request features
- **SKILL.md** — View detailed field specifications and extraction rules
- **GAIK Toolkit** — Part of the GAIK (Generative AI Knowledge Management) toolkit

---

## Use Cases

This skill is designed for:
- Manufacturing facilities with incident reporting requirements
- Safety officers processing verbal incident reports
- Supervisors documenting safety observations
- Organizations using Luvata or similar safety reporting systems
- Converting verbal safety reports to structured data for analysis

---

## License & Attribution

This skill is part of the GAIK toolkit. Built using:
- [FastMCP](https://github.com/jlowin/fastmcp) - MCP server framework
- [GAIK](https://github.com/umairalimran/gaik) - Audio transcription library
- OpenAI Whisper API - Speech-to-text transcription
