# Transcriber

Transcribe audio and video files with configurable transcription backends and optional transcript error fixing.

## Installation

```bash
pip install gaik[transcriber]
```

## System Requirements

- For basic API transcription of supported formats, no extra system dependency is required.
- For chunking and video decoding through PyDub, install `ffmpeg`.

```bash
ffmpeg -version
```

## Quick Start

```python
from gaik.software_components.transcriber import Transcriber, get_openai_config

config = get_openai_config(use_azure=True)

transcriber = Transcriber(
    api_config=config,
    output_dir="transcripts",
    enhanced_transcript=True,
)

result = transcriber.transcribe(file_path="meeting.mp3")
print(result.raw_transcript)
print(result.enhanced_transcript)
print(result.usage)  # token counts, or audio_seconds for whisper-1; empty for local Whisper
```

## Transcription Models

`transcription_model` supports only:
- `"whisper"`
- `"whisper-1"`
- `"gpt-4o-transcribe"`
- `"whisper_local"`

Resolution policy:
- If `transcription_model` is not provided:
  - Azure uses the config value, typically `whisper` or `gpt-4o-transcribe`
  - OpenAI uses the config value, falling back to `whisper-1`
- If `transcription_model="whisper"` or `"whisper-1"`:
  - Azure resolves to the configured Azure transcription deployment, typically `whisper`
  - OpenAI resolves to `whisper-1` — plain `whisper` is not a valid OpenAI model id and returns a 404
- If `transcription_model="gpt-4o-transcribe"`:
  - Azure/OpenAI both use `gpt-4o-transcribe`
- If `transcription_model="whisper_local"`:
  - ignores `use_azure`
  - uses the local transcription endpoint through `whisper_local.py`

An explicit `transcription_model` always wins over the one in `api_config`.

## Chunking Behavior

- Every remote model (`whisper`, `whisper-1`, `gpt-4o-transcribe`) goes through the same
  guard: the file is sent in a single request when it is within both `max_size_mb` and
  `max_duration_seconds`, and split with PyDub otherwise.
- OpenAI refuses any request longer than **1400 s** (`audio duration ... is longer than
  1400 seconds which is the maximum for this model`), so `max_duration_seconds` defaults
  to `1200` and is capped at 1400 even if you pass a larger value. Lower it freely; raising
  it above the ceiling has no effect.
- `whisper_local` uses the local transcription server path and does not use PyDub chunking.

## Transcript Error Fixing

If `enhanced_transcript=True`, the transcriber runs the raw transcript through the standalone `enhance_transcript` software component.

- Input: raw transcript text
- Output: corrected transcript text
- Returned in:
  - `result.enhanced_transcript`

Optional pass-through instructions:
- `enhanced_transcript_instructions`

If `enhanced_transcript_instructions` is provided, it is forwarded to the second pass of `TranscriptEnhancer` as `additional_instructions`.

Example:

```python
transcriber = Transcriber(
    api_config=config,
    enhanced_transcript=True,
    enhanced_transcript_instructions="Keep company names and product names exactly as written.",
)
```

Note: the result field name remains `enhanced_transcript` for compatibility, even though it now contains the corrected transcript returned by `TranscriptEnhancer`.

## Local Whisper Mode

When using `transcription_model="whisper_local"`, pass:
- `local_api_base` (required)
- `local_api_key` (required)

Optional local parameters:
- `language="auto"`
- `diarization=False`
- `speaker_count=None`
- `min_speakers=None`
- `max_speakers=None`
- `initial_prompt=None`

If these local-only options are given while the model is not `whisper_local`, they are ignored with a message.

### How `language` works with `whisper_local`

When `transcription_model="whisper_local"`, the `language` value is sent to the remote Whisper server and used there to select the ASR model.

Typical behavior with the current HH server implementation:
- `language="fi"`:
  - uses `Finnish-NLP/whisper-large-finnish-v3-ct2`
- `language="en"`:
  - uses `large-v3` with English
- `language="auto"`:
  - uses `large-v3` with automatic language detection

So the combination works in two layers:
- `transcription_model="whisper_local"` selects the local/remote Whisper server path
- `language` selects the ASR model or language mode inside that server

## Basic API

```python
from gaik.software_components.transcriber import Transcriber

transcriber = Transcriber(
    api_config=config,
    output_dir="workspace",
    compress_audio=True,            # backward-compatible, currently not used
    enhanced_transcript=True,
    max_size_mb=25,
    max_duration_seconds=1200,
    default_prompt="...",
    transcription_model=None,
    enhanced_transcript_instructions=None,
    language="auto",
    diarization=False,
    speaker_count=None,
    min_speakers=None,
    max_speakers=None,
    initial_prompt=None,
    local_api_base=None,
    local_api_key=None,
)

result = transcriber.transcribe(
    file_path="audio.mp3",
    custom_context="",
    use_case_name=None,
    compress_audio=None,            # backward-compatible, currently not used
)
```

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `AZURE_API_KEY` | Azure mode | Azure OpenAI API key |
| `AZURE_ENDPOINT` | Azure mode | Azure OpenAI endpoint URL |
| `OPENAI_API_KEY` | OpenAI mode | OpenAI API key |
| `AZURE_API_VERSION` | Optional | API version |
| `AZURE_TRANSCRIPTION_MODEL` | Optional | Azure transcription deployment/model |
| `OPENAI_TRANSCRIPTION_MODEL` | Optional | OpenAI transcription model |

## Examples

- `implementation_layer/examples/software_components/transcriber/transcriber_example.py`
- `implementation_layer/examples/software_components/transcriber/transcriber_exmaple_local_model.py`

## License

MIT - see `LICENSE`.
