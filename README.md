# GAIK Toolkit

[![PyPI version](https://badge.fury.io/py/gaik.svg)](https://pypi.org/project/gaik/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Tests](https://github.com/GAIK-project/gaik-toolkit/actions/workflows/test.yml/badge.svg)](https://github.com/GAIK-project/gaik-toolkit/actions)

Generative AI-Enhanced Knowledge Management in Business (GAIK) is a research and development project that builds a business-oriented Generative AI (GenAI) toolkit for knowledge management.

The toolkit focuses on three fundamental knowledge processes:

- **Knowledge capture** - Extracting and structuring information from documents, voice, video, emails, and other sources
- **Knowledge access** - Providing precise, contextual access to organizational knowledge across repositories, systems, and formats
- **Knowledge generation** - Producing reports, proposals, summaries, and other business texts based on captured and accessed knowledge

The toolkit is a combination of modular components that could either be used as standalone components or combined together to develop a specific use case. For example, an incident report writing through phone calls in industries may include the combination of transcriber and extractor. 

## Installation

```bash
# Install all packages
pip install gaik[all]

# Or install individual packages, e.g.,
pip install gaik[extractor]    # Data extraction only
```

## Packages

| Package | Description | Documentation |
|---------|-------------|---------------|
| **extractor** | Extract structured data using natural language requirements | [📖 Docs](packages/python/gaik/src/gaik/extractor/README.md) |
| **parsers** | Convert PDFs to Markdown with vision models or local parsing | [📖 Docs](packages/python/gaik/src/gaik/parsers/README.md) |
| **transcriber** | Transcribe audio/video with Whisper and GPT enhancement | [📖 Docs](packages/python/gaik/src/gaik/transcriber/README.md) |

## Documentation

- **Getting Started** - See package documentation above
- **Examples** - [examples/](examples/)
- **Contributing** - [CONTRIBUTING.md](CONTRIBUTING.md)

## Requirements

- Python 3.10+
- OpenAI or Azure OpenAI API access
- Optional: FFmpeg (for video transcription)

## License

MIT - see [LICENSE](LICENSE)
