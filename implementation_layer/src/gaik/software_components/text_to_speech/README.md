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
    send_instructions=None,  # None: by the model name (see Azure Configuration)
)

result = tts.synthesize(
    text="Hello from GAIK.",
    language="en",   # optional override
    voice="alloy",   # optional override
)
```

## Azure Configuration

When Azure mode is active, the component sends a direct HTTP request to the Azure TTS endpoint. It takes the endpoint and key from `api_config["tts_endpoint"]` and `api_config["api_key"]` when given, otherwise from these environment variables:
- `AZURE_API_KEY`
- `TTS_ENDPOINT`
- `AZURE_TTS_MODEL`

Example:

```env
AZURE_API_KEY=...
AZURE_TTS_MODEL=tts-hd
TTS_ENDPOINT=https://<resource>.cognitiveservices.azure.com/openai/deployments/tts-hd/audio/speech?api-version=2025-03-01-preview
```

The endpoint must be `https://` on an Azure host (`*.openai.azure.com`, `*.cognitiveservices.azure.com`, `*.services.ai.azure.com`) or on a host listed in `GAIK_ALLOWED_ENDPOINT_HOSTS`; otherwise the constructor raises `EndpointNotAllowedError`.

The Azure request payload matches this shape:

```json
{
  "model": "tts-hd",
  "input": "Hello from GAIK.",
  "voice": "alloy",
  "response_format": "mp3",
  "speed": 1.0
}
```

Both branches send the same body, so `response_format` and `speed` reach Azure too and the
audio comes back in the format `result.response_format` names. The instructions (the
language line, `default_instructions` and a call's `instructions`) go to a model whose name
contains `gpt` (`gpt-4o-mini-tts`), and never to the `tts-1` family (`tts-1`, `tts-1-hd` and
the deployment names `tts` and `tts-hd`, with an optional dated suffix such as `-1106`),
which reads the text as written. Any other name, which may be a `tts-1` deployment that
answers 400 to them, gets them only when you opt in: `TextToSpeech(..., send_instructions=True)`
or `api_config["tts_instructions"] = True`, for a `gpt-4o-mini-tts` deployment named, say,
`speech-fi`; `send_instructions=False` turns them off for a `gpt` name. A `TextToSpeech` built
with such a name and no switch logs one warning that the instructions are not sent.
`result.instructions` holds what was sent, or `None`. `speed` always goes to a model without
instructions, and to one with them only when it is not the default 1.0.

Azure's `tts-1` voices are `alloy`, `echo`, `fable`, `onyx`, `nova` and `shimmer`: the
default `voice="marin"` is a `gpt-4o-mini-tts` voice, so pass `voice=` with a `tts-hd`
deployment.

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
- `instructions` (the instructions sent, or `None` for a model that takes none)

Save the generated audio with:

```python
result.save("output_dir")
```

## Example

- `implementation_layer/examples/software_components/text_to_speech/text_to_speech_example.py`
