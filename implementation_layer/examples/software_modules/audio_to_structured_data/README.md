# Audio-to-Structured-Data Module Examples

This folder demonstrates how to use the Audio-to-Structured-Data module, which combines the Transcriber and Extractor components into a single end-to-end pipeline.

## Files

- `pipeline_example.py` - Complete example showing the full audio-to-structured-data workflow
- `sample.mp3` - Sample audio file for testing the pipeline
- `diary_workflow/` - Real-world example: construction site diary creation from voice recordings

## What These Examples Show

- How to process audio files and extract structured data in one pipeline
- How to define field requirements in plain language
- How to get both transcripts and structured output from a single function call
- How to use schema reuse for efficient repeated processing
- Real-world application: creating structured construction site diaries from worker voice notes

## Usage

```bash
# Run the basic pipeline example
python pipeline_example.py

# Explore the diary workflow example
cd diary_workflow
# See diary_workflow folder for specific instructions
```

## Module Outputs

The pipeline returns:
- **Raw Transcript** - Verbatim speech-to-text output
- **Enhanced Transcript** - GPT-refined, readable version
- **Structured Fields** - All defined fields extracted and validated
- **Reusable Schema** - Pydantic schema saved for future runs

## Related Documentation

- [Audio-to-Structured-Data Module](https://github.com/GAIK-project/gaik-toolkit/tree/main/implementation_layer/src/gaik/software_modules/audio_to_structured_data)
- [Software Modules Overview](https://gaik-project.github.io/gaik-toolkit/toolkit/software-modules#audio-to-structured-data)
- [Transcriber Component](https://github.com/GAIK-project/gaik-toolkit/tree/main/implementation_layer/src/gaik/software_components/transcriber)
- [Extractor Component](https://github.com/GAIK-project/gaik-toolkit/tree/main/implementation_layer/src/gaik/software_components/extractor)
