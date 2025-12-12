# Transcriber

Transcribe audio and video files using OpenAI Whisper with optional GPT enhancement for improved formatting.

## Installation

```bash
pip install gaik[transcriber]
```

**Note:** Video processing requires ffmpeg. See [System Requirements](#system-requirements) below.

---

## System Requirements

### Optional: FFmpeg (for Video Processing)

The transcriber works **without ffmpeg** for basic audio transcription (.mp3, .wav, .m4a files).

**FFmpeg is only needed for:**
- Video Processing video files (.mp4, .avi, .mov, .mkv, etc.) - extracts audio
- Compression Compressing large audio files (>25MB) - reduces file size for Whisper API

**Installation:**

**Windows:**
```powershell
winget install ffmpeg
```

**macOS:**
```bash
brew install ffmpeg
```

**Linux:**
```bash
sudo apt-get install ffmpeg  # Ubuntu/Debian
```

**Verify:**
```bash
ffmpeg -version
```

---

## Quick Start

```python
from gaik.building_blocks.transcriber import Transcriber, get_openai_config

# Configure
config = get_openai_config(use_azure=True)

# Create transcriber
transcriber = Transcriber(
    api_config=config,
    output_dir="transcripts",
    enhanced_transcript=True  # Use GPT enhancement
)

# Transcribe
result = transcriber.transcribe(
    file_path="meeting.mp3",
    custom_context="Meeting transcription"
)

# Save results
saved_paths = result.save("output/")
print(result.enhanced_transcript)
```

---

## Features

- **Whisper Integration** - OpenAI Whisper for accurate speech-to-text
- **Automatic Chunking** - Handles files > 25MB with context-aware splitting
- **GPT Enhancement** - Optional post-processing for improved formatting
- **Audio Formats** (no ffmpeg): mp3, wav, m4a, ogg
- **Video Formats** (requires ffmpeg): mp4, avi, mov, mkv, flv
- **Audio Compression** (requires ffmpeg): Automatic compression for large files
- **Multi-Provider** - OpenAI and Azure OpenAI support

---

## Basic API

### Transcriber

```python
from gaik.building_blocks.transcriber import Transcriber

transcriber = Transcriber(
    api_config: dict,                          # From get_openai_config()
    output_dir: str | Path = "workspace",      # Working directory
    compress_audio: bool = True,               # Enable compression
    enhanced_transcript: bool = True,          # Enable GPT enhancement
    max_size_mb: int = 25,                     # Chunk size limit
    max_duration_seconds: int = 1500,          # Duration limit
    default_prompt: str = DEFAULT_PROMPT       # Custom Whisper prompt
)

# Transcribe file
result = transcriber.transcribe(
    file_path: str | Path,
    custom_context: str = "",              # Optional context
    use_case_name: str | None = None,      # Optional use case name
    compress_audio: bool | None = None     # Override compression
) -> TranscriptionResult
```

### TranscriptionResult

```python
# Result object
result.raw_transcript         # Original Whisper output
result.enhanced_transcript    # GPT-enhanced version (if enabled)
result.job_id                 # Unique identifier

# Save to disk
saved_paths = result.save(
    directory: str,
    save_raw: bool = True,
    save_enhanced: bool = True
) -> dict[str, Path]
```

### Configuration

```python
from gaik.building_blocks.transcriber import get_openai_config

# Azure OpenAI (default)
config = get_openai_config(use_azure=True)

# Standard OpenAI
config = get_openai_config(use_azure=False)
```

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `AZURE_API_KEY` | Azure only | Azure OpenAI API key |
| `AZURE_ENDPOINT` | Azure only | Azure OpenAI endpoint URL |
| `OPENAI_API_KEY` | OpenAI only | Standard OpenAI API key |
| `AZURE_API_VERSION` | Optional | API version (default: 2024-12-01-preview) |

---

## Examples

See [examples/building_blocks/transcriber/](../examples/building_blocks/transcriber/) for complete examples.

---

## Resources

- **Repository**: [github.com/GAIK-project/gaik-toolkit](https://github.com/GAIK-project/gaik-toolkit)
- **Examples**: [examples/building_blocks/](https://github.com/GAIK-project/gaik-toolkit/tree/main/examples/building_blocks)
- **Contributing**: [CONTRIBUTING.md](../CONTRIBUTING.md)
- **Issues**: [github.com/GAIK-project/gaik-toolkit/issues](https://github.com/GAIK-project/gaik-toolkit/issues)

## License

MIT - see [LICENSE](../LICENSE)






