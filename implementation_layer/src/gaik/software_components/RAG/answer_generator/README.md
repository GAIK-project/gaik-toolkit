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

- **Citations** - Optional citations, built from the retrieved chunks
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

cited = generator.generate_with_citations(
    query: str,
    context: str | list[Document],
    stream: bool | None = None,
)  # -> CitedAnswer(.answer, .citations, .dropped_citations)
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

### Citations

With `citations=True` each retrieved chunk gets a reference: its block starts with
`[1] [Document: name, Page: X]` for the first chunk, `[2] ...` for the second, and the
model is asked to cite by those references only. The citations are then built in
code from the chunks:

- each reference in the answer becomes `[document_name, page X]`, taken from that
  chunk's metadata; references next to each other that name one page show it once;
- a `[name, page X]` the model writes itself is kept only when a retrieved chunk has
  that document and page, and removed otherwise.

`generate()` returns the answer with its citations built this way.
`generate_with_citations()` also returns `citations`, a list of `Citation`
(`reference`, `document_name`, `page_number` and the retrieved `document`) in the
order the answer first cites them, and `dropped_citations`, the `[name, page X]`
citations it removed, as the model wrote them. When the answer streams, both lists
are filled in once the stream has been read to the end.

`citations` only ever holds retrieved chunks, but not every source the model writes
is caught. Only two bracket forms are read:

- a list of numbers (`[1]`, `[1, 3]`) whose numbers are all retrieved chunks'
  references. A list with any other number (`[0]`, `[2019]`, or `[7]` with four
  chunks) is left as written and is not a citation, so a number the model invents
  stays in the text;
- a document with a page (`[report.pdf, page 3]`).

Text in other forms, such as `[fake.pdf]` or `(report.pdf, page 3)`, is left as
written and is not listed anywhere. A bracket is never read inside a fenced code
block or an inline code span, directly after a name, a digit, `)` or `]` (`arr[0]`,
`matrix[1][2]`), or after `=` (`nums = [1, 2]`); a Markdown link stays as it is too.
A string context has no chunks to number: the model is asked to cite as
`[document_name, page X]`, as in gaik 0.11.0, the answer is returned as the model
wrote it, and `citations` and `dropped_citations` stay empty. With `citations=False`
the answer is returned as the model wrote it.

### Retrieved text as data

Each retrieved chunk reaches the model inside its own `<source_material>` block
in the user message, with a random id for each call and a label naming its
document, page and chunk (`report.pdf, page 3, chunk 12`); the block starts with
the `[Document: name, Page: X]` line, after the chunk's reference with
`citations=True`. The question
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
