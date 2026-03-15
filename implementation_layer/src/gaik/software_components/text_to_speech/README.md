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

tts = TextToSpeech(api_config=config)
result = tts.synthesize("Tama on tekstista puheeksi -esimerkki.", language="fi")
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
    model="gpt-4o-mini-tts",
    voice="alloy",
    response_format="mp3",
    speed=1.0,
    default_instructions=None,
)

result = tts.synthesize(
    text="Hello from GAIK.",
    language="en",
    instructions="Use a calm and clear speaking style.",
)
```

## Azure / OpenAI Model Names

By default the component uses `gpt-4o-mini-tts`.

If you use Azure and your deployment name is different, set:
- `AZURE_TTS_MODEL`

If you use standard OpenAI and want to override the default model name, set:
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
