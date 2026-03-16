# Text-to-Speech

Generate spoken audio from text using OpenAI or Azure OpenAI TTS.

## Installation

```bash
pip install gaik[text-to-speech]
```

`text-to-speech` does not add extra dependencies beyond the core `gaik` install. The extra exists for discoverability and consistency with other software components.

## Quick Start

```python
from gaik.software_components.text_to_speech import TextToSpeech, get_openai_config

config = get_openai_config(use_azure=True)

tts = TextToSpeech(
    api_config=config,
    language="fi",
    voice="alloy",
)
result = tts.synthesize("Tama on tekstista puheeksi -esimerkki.")
saved_path = result.save("tts_outputs")
print(saved_path)
```

## Supported Languages

The component currently exposes two language options:
- `fi`
- `en`

## Basic API

```python
from gaik.software_components.text_to_speech import TextToSpeech

tts = TextToSpeech(
    api_config=config,
    model="tts-hd",
    language="en",
    voice="alloy",
    response_format="mp3",
    speed=1.0,
    default_instructions=None,
)

result = tts.synthesize(
    text="Hello from GAIK.",
    language="en",   # optional override
    voice="alloy",   # optional override
)
```

## Azure Configuration

When Azure mode is active, the component sends a direct HTTP request to the Azure TTS endpoint. Set these environment variables:
- `AZURE_API_KEY`
- `TTS_ENDPOINT`
- `AZURE_TTS_MODEL`

Example:

```env
AZURE_API_KEY=...
AZURE_TTS_MODEL=tts-hd
TTS_ENDPOINT=https://<resource>.cognitiveservices.azure.com/openai/deployments/tts-hd/audio/speech?api-version=2025-03-01-preview
```

The Azure request payload matches this shape:

```json
{
  "model": "tts-hd",
  "input": "Hello from GAIK.",
  "voice": "alloy"
}
```

## OpenAI Configuration

For non-Azure use, the component uses the OpenAI client speech API.

If you want to override the default OpenAI model name, set:
- `OPENAI_TTS_MODEL`

## Output

`TextToSpeech.synthesize(...)` returns a `SpeechSynthesisResult` containing:
- `audio_bytes`
- `job_id`
- `model`
- `voice`
- `language`
- `response_format`
- `content_type`

Save the generated audio with:

```python
result.save("output_dir")
```

## Example

- `implementation_layer/examples/software_components/text_to_speech/text_to_speech_example.py`
