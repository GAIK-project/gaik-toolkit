# Models the GAIK demo app uses, and how it runs on CSC Aitta

The demo app is not one chat model. Each demo calls a different **kind** of model, and
several demos use more than one kind in a single run. This note lists what the demos
call and what was measured against CSC Aitta on 2026-11-16, through gaik and through the
demo's own API.

## Kinds of model

| Kind | How the code calls it |
| --- | --- |
| Structured output | Strict JSON schema through `chat.completions.parse` (extractor, classifier, curator, reviewer, SQL agents) |
| Plain chat | `chat.completions.create`, also streaming (RAG answers, report writer) |
| Vision | Image parts (`image_url`) in a chat call. The server vision extractor also uses the OpenAI Responses API and the Claude and Gemini APIs |
| Speech to text | OpenAI-style `/audio/transcriptions` (`gpt-4o-transcribe`), or a separate local Whisper service with its own API |
| Embeddings | `/embeddings` (`text-embedding-3-small` or `-large`) |
| Text to speech | Azure/OpenAI speech endpoint (`tts-hd`) |
| Claude | Solution Wizard conversation (Claude Agent SDK) and an optional Claude model in the vision extractor |

No demo uses OpenAI function calling. The Postgres and table agents use structured
output.

## What each demo calls today

The server default is Azure OpenAI deployment `gpt-6-luna` (`AZURE_DEPLOYMENT`). A
signed-in user can switch the demos marked "own key works" below to another server model
from the model menu; see the README for the list and who may use the team-only models.

| Demo | Models it calls |
| --- | --- |
| Extractor, Schema generator, Classifier | Structured output with the default model. Images in the classifier use vision |
| Parser | Vision with the default model. Some options use the HH Docling API |
| Vision extractor | Server: a menu of GPT-6 models (Responses API), Claude Sonnet and Gemini. Own key: one model, pages sent as images |
| Luvata order | Structured output, Docling API for parsing |
| Audio / Incident report / Diary | Speech to text (HH's local Whisper server first, `Finnish-NLP/whisper-large-finnish-v3` for Finnish, else `gpt-4o-transcribe`), then structured output with the picked model. Documents use vision. The result names both models |
| Document structured | Parser (vision or Docling) then structured output |
| Transcriber | Speech to text, Azure only (local Whisper first when configured) |
| Dental transcription | Local Whisper service only, no LLM |
| Text to speech | `tts-hd` on Azure. The Nova voice is left out: the deployment answers it with HTTP 429 (2026-11-04) |
| RAG | Embeddings `text-embedding-3-large` (the bundled example index is built with it) and plain chat |
| Video search | Embeddings `text-embedding-3-small`, 1536 dimensions, stored in pgvector. No chat |
| Postgres agent, Table agent | Structured output. They use Azure or OpenAI directly |
| LLM judge | Structured output. The panel uses `gpt-6-luna`, `gpt-6-sol`, `gpt-5.6-terra`. Page validation uses vision |
| Report Writer v1 | Speech to text, vision, chat, structured review. UI defaults: `gpt-4o-transcribe`, `gpt-6-luna`, review model `gpt-5.5-deployment` |
| Source normalizer | Speech to text and vision |
| Knowledge curator / synthesis | Structured output (curator, reviewer) and plain chat (writer) |
| Report Writer v2 | Five steps, each with its own model setting: vision, transcription, curator, writer, reviewer. All default to the server model |
| Solution Wizard | Claude for the conversation. Image attachments use vision, audio uses speech to text |

## Where a user's own key works

With a key entered in the UI, the demo sends every call to the one model chosen:
Extractor, Vision extractor, Schema generator, Classifier, Parser, Postgres agent,
Incident report / Diary / audio and document pipelines, single LLM judge, and image
attachments in the Wizard. It does not reach RAG, Table agent, Video search,
Transcriber, Text to speech, Report Writer (v1 and v2), Source normalizer, Knowledge
curator / synthesis, Luvata order or the judge panel.

## CSC Aitta, tested 2026-11-16

Aitta's catalog (`GET https://aitta-api.csc.fi/model`) listed 24 models: 20 chat models,
two speech models (`openai/whisper-large-v3`, `-turbo`) and two embedding models
(`intfloat/multilingual-e5-large`, `lightonai/modernbert-embed-large`). A model that is
*offline* starts on its first request; Whisper and E5 started within a few minutes of a
preload request.

### Chat models through gaik

Each model got the same five calls through gaik's shared client: a chat, a stream, a
strict JSON schema (an invoice with a line list), `DataExtractor`, and an image with a
schema.

| Model | Chat, stream | JSON schema | DataExtractor | Image | Speed |
| --- | --- | --- | --- | --- | --- |
| `google/gemma-4-31b-it` | yes | yes | yes | yes | 18 tokens/s |
| `Qwen/Qwen3.8-27B` | yes | yes | yes | yes | 21 tokens/s |
| `Qwen/Qwen3.6-35B-A3B` | yes | yes | yes | yes | 54 tokens/s, long reasoning |
| `openai/gpt-oss-120b` | yes | yes | yes | no: answers without reading it | 60 tokens/s |
| `Qwen/Qwen3-Coder-Next` | yes | yes | yes | no: HTTP 500 | not measured |
| `Qwen/Qwen-AgentWorld-35B-A3B` | yes | yes | yes | no: HTTP 500 | not measured |
| `allenai/OLMo-7B-0724-Instruct` | yes | yes | yes | no: HTTP 500 | not measured |
| `swiss-ai/Apertus-8B-Instruct-2509` | yes | wrong values | yes | no: HTTP 500 | not measured |

Every model reasons before it answers, and Aitta takes no option that turns that off
(`enable_thinking` is ignored, and `reasoning_effort` accepts only `low`, `medium` and
`high`). A structured answer therefore takes 8 seconds on gpt-oss 120B and 35 to 47
seconds on Gemma 4 and Qwen 3.8.

### The demo's own routes, with an Aitta model picked

| Demo route | Model | Result |
| --- | --- | --- |
| Extraction from plain language (schema generation, then extraction) | gpt-oss 120B | 76 s, correct |
| | Qwen 3.6 35B | 180 s, one of two invoice lines |
| | Gemma 4 31B | over 400 s |
| Classifier | gpt-oss 120B | 5 s, correct |
| LLM judge, text pair | gpt-oss 120B | 4 s |
| Parser, vision, one image | Gemma 4 31B | 19 s |
| | gpt-oss 120B | refused before the call: text only |
| Transcriber | Whisper large v3 | 93 s of speech in 5 s |
| Audio to structured data | Whisper large v3, gpt-oss 120B | 62 s; 140 s with the transcript fix |
| RAG example (38 chunks), then one question | E5 large, gpt-oss 120B | indexed in 3 s, answered with citations in 6 s |

Schema generation makes four to six model calls in a row, which is why it is slow on
Aitta. It also failed on gpt-oss and Qwen until gaik accepted `"enum": []` as "no
enum" (`FieldSpec`, fixed in this repository, in a gaik release after 0.9.0): the
deployed API installs gaik from PyPI, so until that release a new schema written with
an Aitta model can fail, while the ready-made examples and saved schemas work.

### What the demo does with an Aitta model

- The model menu lists Gemma 4 31B (reads images) and gpt-oss 120B (three times
  faster, text only) when the server has `AITTA_API_KEY`. `DEMO_SERVER_MODELS` can list
  others, with `:text` for a text-only one.
- Idle models: Aitta stops a model that has had no requests (Whisper large v3 and E5
  were offline again about 40 minutes after their last call), and the next request
  waits minutes for it. `GET /model-settings/server` therefore reports the state of the
  speech and embedding models, the demo page says when one is idle, and picking an
  Aitta model in the menu calls `POST /model-settings/aitta/warm`, which asks Aitta to
  start the idle ones (at most once in five minutes).
- `openai/whisper-large-v3-turbo`, the newer and faster Whisper, did not start on
  2026-11-16: Aitta reported its status as `failed` and requests to it did not return.
  The demo stays on `openai/whisper-large-v3`; `AITTA_TRANSCRIPTION_MODEL` switches it
  once turbo runs.
- The audio pages' listening options belong to the HH Whisper server (a set language,
  speaker detection, timed text). With an Aitta model picked they are shown as not
  used, since Aitta's Whisper detects the language itself and returns the text alone.
  Hints and the transcript fix still apply.
- Speech: `get_transcription_api_config()` sends recordings to Aitta's Whisper on the
  same key. gaik's `Transcriber` refuses a config with `provider="aitta"`, so the demo
  addresses Aitta's `/audio/transcriptions` as an OpenAI base URL. The local Whisper
  server is not tried first, and no other model stands behind it.
- Embeddings: RAG embeds with `intfloat/multilingual-e5-large` (1024 dimensions), with
  E5's `query: ` and `passage: ` prefixes. E5 reads 512 tokens, and Aitta answers a
  longer input with HTTP 500 instead of truncating it, so a passage is cut to 700
  characters for its vector (350 if Aitta still refuses); the stored chunk keeps its
  full text. Each example collection is built per model pair, since vectors of one
  embedding model cannot be searched with another.
- Images: a text-only model is refused with HTTP 400 on the routes that send page
  images (vision parsers, Vision Extractor, vision parsing in the document pipeline and
  RAG), instead of returning an answer that ignored the image.
- Not on Aitta: text to speech (Aitta has no speech synthesis), Video search (its table
  holds 1536-dimension vectors), the table agent, Report Writer,
  Knowledge curator and synthesis, Luvata order, the judge panel and the Solution
  Wizard. Their pages say that they run on the server's own model.
- Not tested on Aitta: the Postgres agent, the hallucination and page-validation
  judges, the Web scraper's extraction step and the incident and diary pages. They take
  the picked model like the routes above.

### Limits to know

- Terms: research and development use, no personal or sensitive data, no availability
  guarantee. The pages say so when an Aitta model is picked.
- The token is bound to one CSC user and one LUMI project and expires after 90 days.
- Rate limits are per user and minute: about a hundred embedding requests within two
  minutes brought HTTP 429. With one server token, all demo users share that limit.
- An own Aitta token in the key dialog runs the same routes as any own key, with
  Whisper on that token; RAG and the Transcriber take a server model only.

## Models listed in the UI today

Server models: see the README. Own key, OpenAI/Azure: `gpt-6-luna` (default),
`gpt-6-sol`, `gpt-6.1-sol`, `gpt-6-astra`, `gpt-5.6-terra`. Own key, Aitta:
`google/gemma-4-31b-it`, `openai/gpt-oss-120b` (text only), `Qwen/Qwen3.8-27B`.
