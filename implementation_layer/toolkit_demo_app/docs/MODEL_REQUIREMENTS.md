# Models the GAIK demo needs

The demo is not one chat model. Each demo asks for a different **kind** of model, and
some demos use several kinds in one run. A single model, however good, covers only
the kinds it offers.

## Kinds of model

| Kind | What it is used for | Typical model |
| --- | --- | --- |
| Chat with structured output | Extractor, classifier, schema generator, LLM judge, incident report, diary | `gpt-6-sol`, `gpt-6.1-sol` |
| Vision (image input) | Vision extractor, Vision/Vision+ parsers, scanned forms, Report Writer image sources | a chat model with image input |
| Tool calling | Text-to-SQL and table agents | a chat model with function calling |
| Speech to text | Audio extraction, transcriber, Report Writer recordings | `gpt-4o-transcribe` |
| Embeddings | RAG indexing and search | `text-embedding-3-small` / `-large` |
| Text to speech | Text-to-speech demo | `tts-hd`, `gpt-4o-mini-tts` |
| Agent chat | Solution Wizard conversation | Claude (hosted) |

## Which demos need what

| Demo | Kinds needed | Own model (key in the UI) |
| --- | --- | --- |
| Extractor, Schema generator, Classifier | structured output | yes |
| Vision extractor, Parser (vision) | structured output + vision | yes, if the model takes images |
| LLM judge | structured output (a panel uses several models) | yes, one model |
| Incident report | structured output + speech to text for audio input | text and document paths only |
| Postgres / Table agent | tool calling | Postgres agent yes |
| Diary | structured output + speech to text | text only |
| RAG | embeddings + chat | no |
| Text to speech | text to speech | no |
| Report Writer v2 | vision + speech to text + curator + writer + reviewer (one model each, chosen per step) | no |
| Solution Wizard | Claude for the conversation; own model only for image attachments | partly |

## Why one Aitta model does not run everything

- **One model per request.** With an Aitta token the demo sends every call to the one
  model you chose. A demo that needs a vision model *and* a speech model *and* a chat
  model cannot be served by one of them.
- **Gemma is a chat/vision model.** It does not offer speech to text, embeddings or
  text to speech, so the audio, RAG and TTS demos cannot run on it.
- **Catalog status matters.** In the Aitta catalog a model is *Online*, *Loading* or
  *Offline*. A model that is not online does not answer, and the first request to a
  model that is loading can take minutes.
- **Smaller models are weaker at structured output.** The extractor and schema
  generator need valid JSON that matches a schema. Models such as Poro are best kept to
  simple schemas.
- **Experimental.** The demo's Aitta path was tested with Gemma 4 31B only.

## Models to have available for a full demo

| Purpose | Model |
| --- | --- |
| Main chat / structured output | `gpt-6-sol` (default), `gpt-6.1-sol` (newest) |
| Cheap or fast tasks | `gpt-6-luna` |
| Hard reasoning | `gpt-6-astra` |
| Vision | a GPT-6 model with image input |
| Speech to text | `gpt-4o-transcribe` |
| Embeddings | `text-embedding-3-small` or `-large` |
| Text to speech | `tts-hd` |
| Wizard | a hosted Claude model |

Aitta models listed in the UI: `google/gemma-4-31b-it`, `Qwen/Qwen3.6-27B` (vision),
`openai/gpt-oss-120b`, `LumiOpen/Llama-Poro-2-70B-Instruct`. Check their status in the
Aitta catalog before a demo.
