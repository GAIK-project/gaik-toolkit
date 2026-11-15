# Answer Generator

Generate answers from retrieved context with any configured chat model.

## Installation

```bash
pip install gaik[answer-generator]
```

**Note:** Works with any provider configured with `get_llm_config()` (OpenAI, Azure
OpenAI, Google, Anthropic, CSC Aitta, other OpenAI-compatible servers or optional
LiteLLM); `stream=True` needs streaming support. See the
[multi-provider guide](https://gaik-project.github.io/gaik-toolkit/toolkit/multi-provider-llm/).

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

Without `config`, the generator uses `get_openai_config(use_azure)`. Pass
`config=get_llm_config("aitta")` (or another provider) to use a different chat model.

### Custom Prompt

Custom prompts must include both `{query}` and `{context}`; a prompt missing either is
rejected when `AnswerGenerator` is created. Only these placeholders are substituted; other
braces remain literal, so a JSON example needs no escaping, nested or not:
`{"answer": {"text": "..."}}` stays as written. A prompt written for Python's
`str.format`, where every other brace is doubled (`{{"answer": "..."}}`), still works:
its `{{` and `}}` become single braces.

### Retrieved text as data

Each retrieved chunk reaches the model inside its own `<source_material>` block
in the user message, with a random id for each call and a label naming its
document, page and chunk (`report.pdf, page 3, chunk 12`); the block starts with
the `[Document: name, Page: X]` line that citations are taken from. The question
stays outside the blocks, and the system message holds the instructions with the
sentence in `SOURCE_MATERIAL_INSTRUCTION`
([`gaik.software_components.source_material`](../../source_material.py)). A
sentence in an indexed document cannot close its block or change the task. With
a custom prompt, your template is the user message and `{context}` becomes the
blocks. Conversation history keeps, as before, the earlier questions and answers
only, not the chunks retrieved for them. The call and its return value are
unchanged.

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
