# Models the GAIK demo app uses, and what Aitta would need

The demo app is not one chat model. Each demo calls a different **kind** of model, and
several demos use more than one kind in a single run. This note lists what the demos
call today and what a CSC Aitta deployment would have to provide, so each gap can be
checked against the Aitta catalog.

What Aitta itself serves was not verified here; the "needs" below are what the code
requires.

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

The server default is Azure OpenAI deployment `gpt-6.1-sol`.

| Demo | Models it calls |
| --- | --- |
| Extractor, Schema generator, Classifier | Structured output with the default model. Images in the classifier use vision |
| Parser | Vision with the default model. Some options use the HH Docling API |
| Vision extractor | Server: a menu of GPT-6 models (Responses API), Claude Sonnet and Gemini. Own key: one model, pages sent as images |
| Luvata order | Structured output, Docling API for parsing |
| Audio / Incident report / Diary | Speech to text (local Whisper if configured, else `gpt-4o-transcribe`), then structured output. Documents use vision |
| Document structured | Parser (vision or Docling) then structured output |
| Transcriber | Speech to text, Azure only (local Whisper first when configured) |
| Dental transcription | Local Whisper service only, no LLM |
| Text to speech | `tts-hd` on Azure |
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

## What Aitta would need

| Need | Why | Status in code |
| --- | --- | --- |
| A structured-output chat model | Almost every demo | Works with an own key. Only Gemma 4 31B has been tested. Smaller models can fail strict JSON schemas |
| A vision model | Parser, classifier on images, vision extractor, judge validation | Works through the shared chat path. Server vision extractor needs an Aitta branch |
| A speech-to-text model | Audio demos, transcriber, Report Writer sources | **Blocked in code**: audio classes refuse Aitta configs, even for local Whisper. Aitta config has no transcription model setting |
| An embedding model | RAG, Video search | `AITTA_EMBEDDING_MODEL` is empty by default. The RAG example index (3072 dimensions) and the Video search table (1536) would need re-embedding |
| A text-to-speech model | Text to speech | **Blocked in code**, same check |
| One model per call | Report Writer v2 and the judge panel use several models | One Aitta model serves every step, so steps cannot use different models |
| Claude | Solution Wizard conversation | Not available on Aitta |

Catalog status also matters: a model that is *Offline* does not answer, and a model
that is *Loading* can take minutes on the first request.

## Code changes in the toolkit demo app (and gaik)

1. Allow Aitta in the audio classes, or at least let `whisper_local` work with an Aitta
   config; add transcription, embedding and TTS model settings to the Aitta config
   (gaik library).
2. Route the demos that bypass the shared config through it: Transcriber, Table agent,
   Postgres agent (server path), Video search, single LLM judge, Parser multimodal.
3. Add an Aitta branch to the server vision extractor and add `aitta` to the judge
   providers.
4. Make RAG and Video search independent of one embedding model, or ship an index per
   model.
5. Add Report Writer v2 and the other multi-step demos to the own-key paths if wanted.

## Models listed in the UI today

OpenAI/Azure: `gpt-6-sol` (default), `gpt-6.1-sol`, `gpt-6-luna`, `gpt-6-astra`,
`gpt-5.6-terra`. Aitta: `google/gemma-4-31b-it`, `Qwen/Qwen3.6-27B`,
`openai/gpt-oss-120b`, `LumiOpen/Llama-Poro-2-70B-Instruct`.
