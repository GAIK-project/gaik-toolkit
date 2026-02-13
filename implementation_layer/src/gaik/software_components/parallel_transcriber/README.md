# Parallel Transcriber

Production-quality parallel audio/video transcription using FFmpeg chunking and Azure OpenAI Whisper / GPT-4o Transcribe Diarize.

## Installation

```bash
pip install gaik[parallel-transcriber]
```

## System Requirements

### FFmpeg (required)

Unlike the sequential `transcriber` component, `parallel_transcriber` **requires FFmpeg** for all operations (chunking, audio extraction, duration probing).

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
ffmpeg -version && ffprobe -version
```

---

## Quick Start

```python
from gaik.software_components.parallel_transcriber import (
    ParallelTranscriber, TranscriptionConfig,
)
from gaik.software_components.config import get_openai_config

# Configure Azure OpenAI
api_cfg = get_openai_config(use_azure=True)

# Customise pipeline (all optional)
config = TranscriptionConfig(
    chunk_duration_minutes=15,
    chunk_overlap_seconds=10.0,
    transcription_workers=4,
    response_format="srt",
)

# Run transcription
transcriber = ParallelTranscriber(api_cfg, config)
result = transcriber.transcribe("interview.mp4")

# Use the result
print(result.plain_text)          # stripped plain text
result.save("output/")            # saves as .srt / .txt / .vtt
print(result.total_chunks)        # number of parallel chunks used
print(result.total_duration_seconds)
```

---

## Features

- **Parallel FFmpeg chunking** - splits long audio into overlapping chunks processed concurrently
- **Overlap deduplication** - SRT merging removes duplicate subtitles in overlap regions
- **Whisper + GPT-4o Diarize** - two model backends via `TranscriptionModel` enum
- **Thread-safe cancellation** - `SimpleCancellation` / `check_cancelled` callback protocol
- **Progress callbacks** - stage-based progress reporting (`extracting`, `splitting`, `transcribing`, `merging`, `complete`)
- **Retry with backoff** - automatic retry for transient errors and 429 rate limits
- **Video support** - automatic audio extraction from video files
- **Format conversion** - output as SRT, VTT, plain text, or JSON
- **Environment-based config** - `TranscriptionConfig.from_env()` reads all knobs from env vars

---

## API

### ParallelTranscriber

```python
transcriber = ParallelTranscriber(
    api_config: dict,                     # From get_openai_config()
    config: TranscriptionConfig | None,   # Pipeline parameters (defaults used if None)
)

result = transcriber.transcribe(
    file_path: str | Path,
    check_cancelled: Callable[[], None] | None = None,
    progress_callback: Callable[[str, int, int, str], None] | None = None,
) -> TranscriptionResult
```

### TranscriptionConfig

All parameters with sensible defaults. Key fields:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `chunk_duration_minutes` | 20 | Nominal chunk length |
| `chunk_overlap_seconds` | 15.0 | Overlap between adjacent chunks |
| `transcription_workers` | 3 | Parallel API calls (Whisper) |
| `ffmpeg_split_workers` | 3 | Parallel FFmpeg encode processes |
| `response_format` | `"srt"` | Output format (srt/vtt/text/json) |
| `model` | `WHISPER` | `TranscriptionModel.WHISPER` or `GPT4O_DIARIZE` |
| `language` | `None` | Language code or None for auto-detect |
| `max_retries` | 2 | Retries for transient errors |
| `max_429_retries` | 4 | Extra retries for rate limits |

Use `TranscriptionConfig.from_env()` to read all parameters from environment variables.

### TranscriptionResult

```python
result.content                  # Raw transcription content
result.format                   # "srt", "vtt", "text", etc.
result.plain_text               # Extracted plain text (strips SRT formatting)
result.total_chunks             # Number of chunks used
result.total_duration_seconds   # Audio duration
result.save("output/")          # Save to file (extension auto-added)
```

---

## Cancellation

```python
from gaik.software_components.parallel_transcriber import (
    ParallelTranscriber, SimpleCancellation,
)

cancel = SimpleCancellation()

# From another thread:
# cancel.cancel()

result = transcriber.transcribe(
    "long_recording.mp4",
    check_cancelled=cancel.check,
)
```

---

## Environment Variables

| Variable | Description |
|----------|-------------|
| `AZURE_API_KEY` | Azure OpenAI API key |
| `AZURE_ENDPOINT` | Azure OpenAI endpoint URL |
| `OPENAI_API_KEY` | Standard OpenAI API key |
| `CHUNK_DURATION_MINUTES` | Override chunk length |
| `CHUNK_OVERLAP_SECONDS` | Override overlap duration |
| `TRANSCRIPTION_WORKERS` | Override API parallelism |
| `FFMPEG_SPLIT_WORKERS` | Override FFmpeg parallelism |
| `RESPONSE_FORMAT` | Override output format |
| `TRANSCRIPTION_LANGUAGE` | Override language |
| `TRANSCRIPTION_MODEL` | `whisper` or `gpt-4o-transcribe-diarize` |

See `TranscriptionConfig.from_env()` docstring for the full list.

---

## Differences from `transcriber/`

| | `transcriber` | `parallel_transcriber` |
|--|---------------|------------------------|
| **Chunking** | PyDub (Python) | FFmpeg (subprocess) |
| **Parallelism** | Sequential | ThreadPoolExecutor |
| **FFmpeg** | Optional (video/compression only) | Required |
| **Overlap dedup** | None | SRT-based time + text matching |
| **Models** | Whisper only | Whisper + GPT-4o Diarize |
| **Cancellation** | Not supported | Thread-safe callback protocol |
| **Progress** | Not supported | Stage-based callbacks |
| **Extra deps** | `pydub` | None (FFmpeg on PATH) |

---

## Resources

- **Repository**: [github.com/GAIK-project/gaik-toolkit](https://github.com/GAIK-project/gaik-toolkit)
- **Issues**: [github.com/GAIK-project/gaik-toolkit/issues](https://github.com/GAIK-project/gaik-toolkit/issues)

## License

MIT - see [LICENSE](../../../../../LICENSE)
