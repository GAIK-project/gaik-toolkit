# Answer Generator

Generate answers from retrieved context using OpenAI or Azure OpenAI.

## Installation

```bash
pip install gaik[answer-generator]
```

**Note:** Requires OpenAI or Azure OpenAI API access.

---

## Quick Start

```python
from gaik.software_components.RAG.answer_generator import AnswerGenerator

generator = AnswerGenerator(citations=True, stream=False)
answer = generator.generate(
    query="What is the total amount?",
    context="Invoice total amount is $1,500."
)

print(answer)
```

---

## Features

- **Citations** - Optional citation formatting in answers
- **Custom Prompt** - Provide a custom prompt template
- **Streaming** - Stream or return full responses
- **Conversation History** - Optional last-n Q/A memory

---

## Basic API

### AnswerGenerator

```python
generator = AnswerGenerator(
    config: dict | None = None,
    use_azure: bool = True,
    model: str | None = None,
    citations: bool = False,
    prompt: str | None = None,
    stream: bool = True,
    conversation_history: bool = False,
    last_n: int = 10,
)
```

### Methods

```python
answer = generator.generate(
    query: str,
    context: str | list[Document],
    stream: bool | None = None,
)  # -> str | Iterable[str]
```

---

## Configuration

This software component uses `gaik.software_components.config` for OpenAI/Azure configuration.

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `AZURE_API_KEY` | Azure only | Azure OpenAI API key |
| `AZURE_ENDPOINT` | Azure only | Azure OpenAI endpoint URL |
| `AZURE_DEPLOYMENT` | Azure only | Azure deployment name |
| `OPENAI_API_KEY` | OpenAI only | Standard OpenAI API key |
| `AZURE_API_VERSION` | Optional | API version (default: 2025-03-01-preview) |

---

## Examples

See [implementation_layer/examples/software_components/RAG/](../../../../implementation_layer/examples/software_components/RAG/) for usage:
- `answer_generator_example.py` - Basic answer generation

---

## Resources

- **Repository**: [github.com/GAIK-project/gaik-toolkit](https://github.com/GAIK-project/gaik-toolkit)
- **Examples**: [implementation_layer/examples/software_components/](https://github.com/GAIK-project/gaik-toolkit/tree/main/implementation_layer/examples/software_components)
- **Contributing**: [CONTRIBUTING.md](../../../../CONTRIBUTING.md)
- **Issues**: [github.com/GAIK-project/gaik-toolkit/issues](https://github.com/GAIK-project/gaik-toolkit/issues)

## License

MIT - see [LICENSE](../../../../LICENSE)
