# Transcriber Example

Examples for the Transcriber software component.

## Files

- `transcriber_example.py` - Azure/OpenAI transcription example with enhanced_transcript enabled
- `transcriber_exmaple_local_model.py` - local whisper service example using `transcription_model="whisper_local"`

## What These Examples Show

- API-based transcription with OpenAI or Azure OpenAI
- Optional transcript error fixing through the `enhance_transcript` software component
- Local transcription service usage with runtime endpoint and key
- Accessing raw and corrected transcript outputs

## Usage

```bash
python transcriber_example.py path/to/audio.mp3
```

```bash
python transcriber_exmaple_local_model.py
```

## Related Documentation

- [Transcriber Component](https://github.com/GAIK-project/gaik-toolkit/tree/main/implementation_layer/src/gaik/software_components/transcriber)
- [Software Components Overview](https://gaik-project.github.io/gaik-toolkit/toolkit/software-components#transcriber)
