# Construction Diary Creation Skill for Claude Desktop

Transform construction site audio recordings into structured Työmaapäiväkirja (daily diary) documents — automatically.

---

## What Does This Skill Do?

This skill extracts structured information from Finnish construction site manager's audio recordings and creates official daily diary documentation. Simply provide an audio file, and Claude will:

- **Transcribe** the audio recording using Whisper AI
- **Extract** 20 standardized fields for Työmaapäiväkirja
- **Generate** a formatted Word document with a professional 2-column table
- **Validate** data against predefined work phase lists

### Extracted Fields

The skill extracts essential construction diary information including:
- Site details (Kohde, Laatija, Päivämäärä)
- Weather conditions (Sää)
- Personnel resources (Resurssit - Henkilöstö)
- Daily work tasks (Päivän työt)
- Work phases: started, ongoing, completed, interrupted (from predefined lists)
- Events, deviations, inspections, and supervisor notes

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
3. Upload `construction-diary-creation.zip` (created by setup script)

✅ **Setup complete!**

---

## How to Use

Simply provide the audio file path to Claude:

```
Process construction diary from C:\path\to\your\audio-file.mp3 using construction-diary-creation skill.
```

### What Happens Next

1. Claude transcribes the audio
2. Extracts 20 fields from the transcript
3. Creates a Word document with a 2-column table
4. Saves it as `Tyomaapaivakirja_[Date].docx`
5. Presents the file for download

---

## Example Output

The generated Word document contains:

```
TYÖMAAPÄIVÄKIRJA
================

| Kenttä                      | Arvo                           |
|-----------------------------|--------------------------------|
| Kohde                       | 3285-00 Komeetankuja 6, Espoo  |
| Laatija                     | Matti Virtanen                 |
| Sää                         | 3 °C, 2 m/s, 78 % suht. kosteus|
| Päivämäärä                  | 20.05.2024                     |
| Resurssit - Henkilöstö      | Työnjohtajat: 2 hlö, ...       |
| Työviikko                   | 21                             |
| Päivän työt                 | sisäpurku, rungon purku        |
| ...                         | ...                            |
```

**Key Features:**
- Fields not mentioned in audio are left empty (no guessing)
- Work phases are validated against predefined lists
- Brief, factual extraction with tight keywords
- Professional formatting suitable for official documentation

---

## Sample Data

Test the skill with included sample audio:

| File | Description |
|------|-------------|
| `data/fin-example-1.mp3` | Finnish construction diary recording |
| `data/en-example-1.mp3` | English example (for testing) |

**Try it:**
```
Process construction diary from [path-to-folder]\data\fin-example-1.mp3
```

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
- Work phase fields only accept predefined values (see SKILL.md)

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
      "args": ["C:\\path\\to\\construction-diary-creation\\transcription-MCP\\server.py"],
      "timeout": 600000
    }
  }
}
```

**Install Skill:**
1. Zip the `construction-diary-creation` folder (inner one with SKILL.md)
2. Upload to Claude Desktop: Settings → Capabilities → + Add

---

## Technical Details

### Project Structure

```
construction-diary-creation/
├── setup.bat                      # Automated setup wizard
├── construction-diary-creation/   # Skill definition
│   └── SKILL.md                   # Extraction workflow & field specifications
├── transcription-MCP/             # Audio transcription MCP server
│   ├── server.py                  # FastMCP server implementation
│   └── .env                       # API credentials
└── data/                          # Sample audio files
    ├── fin-example-1.mp3
    └── en-example-1.mp3
```

### How It Works

1. **MCP Server Launch** — Claude Desktop starts `transcription-MCP/server.py` as a background process
2. **Skill Invocation** — User provides audio file path
3. **Transcription** — MCP server calls OpenAI Whisper API to transcribe audio
4. **Extraction** — Claude analyzes transcript and extracts 20 structured fields
5. **Validation** — Work phases validated against predefined lists
6. **Document Generation** — Word document created with 2-column table
7. **Presentation** — File saved and presented to user

### Dependencies

- **Python packages:** `fastmcp`, `gaik[transcriber]`, `python-dotenv`
- **External APIs:** OpenAI Whisper API (for audio transcription)

## Getting Help

- **GitHub Issues** — Report bugs or request features
- **SKILL.md** — View detailed field specifications and extraction rules
- **GAIK Toolkit** — Part of the GAIK (Generative AI Knowledge Management) toolkit

---

## License & Attribution

This skill is part of the GAIK toolkit. Built using:
- [FastMCP](https://github.com/jlowin/fastmcp) - MCP server framework
- [GAIK](https://github.com/umairalimran/gaik) - Audio transcription library
- OpenAI Whisper API - Speech-to-text transcription
