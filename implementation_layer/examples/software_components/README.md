# Software Components Examples

This folder contains usage examples for all GAIK software components. Each component is a standalone building block that can be used individually or composed into custom pipelines.

## Available Examples

### [Classifier](./classifier)
Document classification using natural language category definitions. Zero-shot classification with AI-powered semantic understanding.

### [Extractor](./extractor)
Structured data extraction from text using plain-language field requirements. Multiple examples showing basic to advanced extraction scenarios.

### [Parsers](./parsers)
Document parsing examples for PDFs and Word documents. Includes both local (PyMuPDF) and vision-based parsing strategies.

### [Transcriber](./transcriber)
Audio and video transcription using OpenAI Whisper with optional transcript enhancement.

### [Text-to-Speech](./text_to_speech)
Generate spoken audio from text using OpenAI or Azure OpenAI TTS.

### [RAG Components](./RAG)
Individual examples for each of the five RAG components: Parser, Embedder, Vector Store, Retriever, and Answer Generator.

### [PostgreSQL Agent](./postgres_agent)
Read-only text-to-SQL query agent. Ask a PostgreSQL database questions in natural language; the agent introspects the schema, generates validated read-only SQL, runs it, and answers.

## Getting Started

1. Choose the component you want to explore
2. Navigate to the component's folder
3. Read the component-specific README for details
4. Run the example scripts

## Requirements

All examples require the GAIK package to be installed:

```bash
pip install gaik
```

Set up your API keys as environment variables:

```bash
export OPENAI_API_KEY="your-key-here"
# Or for other providers: ANTHROPIC_API_KEY, GOOGLE_API_KEY, etc.
```

## Related Documentation

- [Software Components Overview](https://gaik-project.github.io/gaik-toolkit/toolkit/software-components)
- [Component Source Code](https://github.com/GAIK-project/gaik-toolkit/tree/main/implementation_layer/src/gaik/software_components)
- [Software Modules Examples](../software_modules) - For complete end-to-end pipelines
