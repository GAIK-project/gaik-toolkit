# Software Modules Examples

This folder contains usage examples for GAIK software modules. Each module is a production-ready, end-to-end pipeline that combines multiple software components into a single workflow.

## Available Examples

### [Audio-to-Structured-Data](./audio_to_structured_data)
Complete pipeline for transcribing audio/video files and extracting structured data. Combines Transcriber and Extractor components. Includes real-world construction diary example.

**Use cases:** Incident reporting, field work diaries, meeting minutes, voice-to-data workflows

### [Documents-to-Structured-Data](./documents_to_structured_data)
Complete pipeline for parsing documents (PDF/Word) and extracting structured data. Combines Document Parser and Extractor components.

**Use cases:** Invoice processing, contract analysis, form digitization, document data extraction

### [RAG-Workflow](./RAG_workflow)
Complete pipeline for building question-answering systems over document collections. Combines all five RAG components (Parser, Embedder, Vector Store, Retriever, Answer Generator).

**Use cases:** Knowledge base search, document Q&A, research assistance, customer support knowledge retrieval

## Modules vs Components

- **Software Modules** - Ready-to-use pipelines that handle complete workflows with minimal setup
- **Software Components** - Individual building blocks for custom pipeline construction

If you need fine-grained control or want to build custom workflows, see the [Software Components Examples](../software_components).

## Getting Started

1. Choose the module that matches your use case
2. Navigate to the module's folder
3. Read the module-specific README for details
4. Run the pipeline example script

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

- [Software Modules Overview](https://gaik-project.github.io/gaik-toolkit/toolkit/software-modules)
- [Module Source Code](https://github.com/GAIK-project/gaik-toolkit/tree/main/implementation_layer/src/gaik/software_modules)
- [Software Components Examples](../software_components) - For individual component usage
