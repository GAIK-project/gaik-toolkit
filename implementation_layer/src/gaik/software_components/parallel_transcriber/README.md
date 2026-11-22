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

### Input limits

`ParallelTranscriber(api_cfg, config, limits=InputLimits(...))` refuses a file over
`max_media_seconds` (6 hours) with `InputLimitError` before audio is extracted or any
transcription call is made, on every backend; `whisper_local_max_audio_minutes` is a
second cap for Whisper Local only. `max_media_bytes` is off by default: the size of a
video says little about its audio. The length is read with ffprobe; when that fails, it
is measured again from the extracted audio before the first call. A file whose header
holds no length (a WebM a browser wrote while recording) is measured by decoding its
audio, and a recording whose length cannot be read at all is refused. Every ffprobe
call has a 60-second timeout, decoding a 10-minute one. GPT-4o Diarize, Whisper Local and
a recording to split need the length before the first call, so a file that is not audio or
video at all is refused there with `InputLimitError` (or `ValueError` with
`max_media_seconds=None`), not with ffprobe's `CalledProcessError`.

A chunk that FFmpeg cannot create, even on its sequential retry, stops the run with a
`RuntimeError` that names the missing time ranges, and a chunk whose transcription fails
after its retries stops the run too: the chunks not yet sent are not sent (each would be a
paid request), and the error is raised once the running ones finish. A chunk the provider
transcribes as empty text is not an error, so a stretch of speech the provider returns
nothing for looks like silence;
compare the transcript's timestamps with the recording where a gap matters. Each chunk's
encoded length is read back with ffprobe, so the check holds at every `audio_bitrate`. A
chunk shorter than asked for is retried like a failed one; if it is still short while audio
continues past it, it is a missing stretch and stops the run. Chunks past the real end of
the audio, which a file whose header overstates its length produces, are skipped and
logged, and a recording in which no chunk holds audio stops the run with a `RuntimeError`.
A last chunk that adds more than 0.25 s past the chunks before it is kept; a smaller tail
(part of a word at most) is not sent, since OpenAI refuses audio under 0.1 s and a model
asked about near-silence can make words up.

### Models on the Whisper backend

`TranscriptionModel.WHISPER` sends `api_config["transcription_model"]`. A Whisper model or
deployment (`whisper`, `whisper-1`) is asked for SRT, which gives subtitle timestamps and
the overlap merge. A GPT-4o transcription model (`gpt-4o-transcribe`, the default of
`get_openai_config()`, or `gpt-4o-mini-transcribe`) takes only `json` or `text`, so it is
asked for `json` and gives text without timestamps: each chunk becomes one subtitle over its
own stretch of the recording, and the words two chunks both give for their overlap are kept
once: the end of one chunk's text and the start of the next one's are lined up over every
length up to the overlap's words, and the best match (a difflib ratio of at least 0.75 with
at least 4 words in common, or 0.85 with 3) is taken from the next chunk, so one word heard
differently does not repeat the overlap, and a phrase said twice away from where the chunks
meet never lines them up. A word of the earlier chunk before the lined-up stretch is kept.
Without such a match both texts are kept whole, so a very short or mostly silent overlap may
appear twice in the transcript. Use Whisper or `GPT4O_DIARIZE` where
per-sentence timestamps matter. Such a model also refuses a request over 1400 s, so a
recording longer than 23 minutes is split even when it is small, into chunks of at most
`(1400 - 2 x chunk_overlap_seconds) / 60` minutes.

The name decides the format: `json` for a name that contains `gpt` and not `whisper`, SRT
otherwise. For a deployment whose name says neither, set
`TranscriptionConfig(whisper_request_format="json")` (or `"srt"`), or `WHISPER_REQUEST_FORMAT`.

On Azure the Whisper backend resolves the provider as `Transcriber` does
(`provider: "azure"` needs no `use_azure` flag) and sends to `azure_audio_endpoint` when it
is set, else to `azure_endpoint`, else to `base_url`, in the same order, as that resource's
deployment route (`/openai/deployments/<model>/audio/transcriptions`). A trailing `/openai/v1`
or `/openai/deployments/...` is cut from the endpoint, and a bare trailing `/openai` on an
Azure host (`*.azure.com`, Azure Government `*.azure.us`, Azure China `*.azure.cn`, API
Management `*.azure-api.net`), so `https://<resource>.openai.azure.com/openai/v1` works for
Whisper and GPT-4o Diarize alike, while a gateway such as `https://gw.example.com/openai/prod`
keeps its own path. A `base_url` you set yourself (an APIM or LiteLLM gateway, say) no longer
wins over an `azure_endpoint`, or the `azure_audio_endpoint` that `get_llm_config()` fills from
`AZURE_ENDPOINT`: to send the audio through a gateway, set `azure_audio_endpoint` to it.

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
result.language                 # Language code or "auto"
result.model_used               # Model string (e.g. "whisper")
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

### Azure / OpenAI credentials

| Variable | Description |
|----------|-------------|
| `AZURE_API_KEY` | Azure OpenAI API key |
| `AZURE_ENDPOINT` | Azure OpenAI endpoint URL |
| `OPENAI_API_KEY` | Standard OpenAI API key |

### Pipeline parameters (`TranscriptionConfig.from_env()`)

| Variable | Default | Description |
|----------|---------|-------------|
| `CHUNK_DURATION_MINUTES` | 20 | Nominal chunk length (minutes) |
| `CHUNK_OVERLAP_SECONDS` | 15.0 | Overlap between adjacent chunks |
| `MAX_SINGLE_FILE_MB` | 24.0 | Max file size before chunking |
| `GPT4O_CHUNK_DURATION_MINUTES` | 23 | Chunk length for GPT-4o (25 min API limit − 2 min margin) |
| `TRANSCRIPTION_WORKERS` | 3 | Parallel API calls (Whisper) |
| `FFMPEG_SPLIT_WORKERS` | 3 | Parallel FFmpeg encode processes |
| `FFMPEG_THREADS_PER_PROCESS` | 1 | FFmpeg threads per subprocess (alias: `FFMPEG_THREADS`) |
| `GPT4O_CHUNK_PARALLELISM` | 4 | Parallel API calls (GPT-4o Diarize) |
| `FFMPEG_CHUNK_TIMEOUT_SECONDS` | 3600 | Timeout per FFmpeg chunk encode |
| `API_TIMEOUT_SECONDS` | 600 | API call timeout, alias `AZURE_OPENAI_TIMEOUT_SECONDS` (keep ≥ ~25s × `GPT4O_CHUNK_DURATION_MINUTES`) |
| `MAX_RETRIES` | 2 | Retries for transient errors |
| `RETRY_BASE_DELAY_SECONDS` | 1.0 | Base delay between retries |
| `MAX_429_RETRIES` | 4 | Extra retries for rate limits |
| `AUDIO_BITRATE` | 128k | FFmpeg audio bitrate |
| `AUDIO_SAMPLE_RATE` | 16000 | FFmpeg audio sample rate |
| `AUDIO_CHANNELS` | 1 | FFmpeg audio channels |
| `RESPONSE_FORMAT` | srt | Output format (srt/vtt/text/json) |
| `TRANSCRIPTION_LANGUAGE` | auto | Language code or auto-detect |
| `WHISPER_PROMPT` | — | Optional Whisper prompt |
| `TRANSCRIPTION_MODEL` | whisper | `whisper` or `gpt-4o-transcribe-diarize` |
| `WHISPER_REQUEST_FORMAT` | — | `srt` or `json`; unset decides by the model name |

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
