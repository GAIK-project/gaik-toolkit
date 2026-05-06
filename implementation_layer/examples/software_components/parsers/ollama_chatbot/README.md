# Ollama chatbot for a folder of mixed documents

Drop PDFs (text-layer, scanned, or dual), DOCX, and TXT files into a folder.
Get a local Ollama-powered chatbot that answers questions about them, using
[Open WebUI](https://github.com/open-webui/open-webui) as the chat front-end.

## What this does

```
input_docs/  -- PDFs, scans, DOCX, TXT
     |
     v
prepare_docs.py
   - PDFs   -> GAIK MultimodalParser (Google Gemini, vision)
   - DOCX   -> GAIK DocxParser (local, python-docx)
   - TXT    -> copied as-is
     |
     v
markdown_out/  -- clean .md per source file
     |
     v
Open WebUI (Knowledge collection)  +  Ollama (Gemma 3, llama3.1, ...)
     |
     v
Chat at http://localhost:8080
```

GAIK does the parsing because Open WebUI's built-in PDF reader does not OCR
scanned pages. Vision-LLM parsing handles scanned, dual, and image-heavy PDFs
in one pass and produces clean markdown.

The chat itself runs **locally** through Ollama -- no cloud calls per query.
The only external call is the one-time markdown extraction with Gemini.

## Quickstart (6 steps)

1. **Get a free Gemini API key** at <https://aistudio.google.com/app/apikey>
   (used only by `prepare_docs.py`, not by the chat).

2. **Install Ollama** from <https://ollama.com/download>.

3. **Start the stack** (Ollama + Open WebUI in Docker):

   ```bash
   cp .env.example .env          # then edit .env to add your GOOGLE_API_KEY
   docker compose up -d
   docker exec -it ollama ollama pull gemma3:4b
   ```

4. **Drop your files** into `input_docs/` (any mix of `.pdf`, `.docx`, `.txt`).

5. **Convert them to markdown:**

   ```bash
   pip install "gaik[multimodal-parser,parser-cpu]"
   python prepare_docs.py
   ```

   The script prints per-file results and a total Gemini cost at the end
   (typically a few cents -- well inside the free tier).

6. **Open the chat** at <http://localhost:8080>:
   - Sign up locally (the first user becomes admin).
   - Go to *Workspace -> Knowledge -> + Create Knowledge*.
   - Add the `.md` files from `markdown_out/` (drag-and-drop in the UI, or
     point to the `/data/docs` path inside the container).
   - In the chat input, type `#` and pick your knowledge collection.
   - Ask questions. Sources are cited inline.

## Updating

When you add or change files:

```bash
python prepare_docs.py     # idempotent: only re-parses changed files
```

Then re-import the changed `.md` files in Open WebUI's Knowledge view
(Open WebUI auto-detects file changes when you re-upload).

## Recommended models

| Laptop RAM | Model              | Size    | Notes                        |
| ---------- | ------------------ | ------- | ---------------------------- |
| 8 GB       | `gemma3:1b`        | 815 MB  | Fast, decent for English.    |
| 8 GB       | `gemma3:4b`        | 3.3 GB  | Multimodal. Handles 140+ langs incl. Finnish. |
| 16 GB      | `llama3.1:8b`      | ~5 GB   | Strong general reasoning.    |
| 16 GB      | `qwen2.5:7b`       | ~5 GB   | Good multilingual incl. Finnish. |
| 32 GB+     | `gemma3:12b`       | ~8 GB   | Best Gemma quality on a laptop. |

Pull a model with `docker exec -it ollama ollama pull <name>` and select it
in Open WebUI's model dropdown.

## Supported file types

| Type           | Parser                   | Notes                                   |
| -------------- | ------------------------ | --------------------------------------- |
| Text-layer PDF | `MultimodalParser`       | Layout, tables, formulas preserved.     |
| Scanned PDF    | `MultimodalParser`       | Vision OCR -- no Tesseract install.     |
| Dual PDF       | `MultimodalParser`       | Per-page handling (text + scanned mix). |
| `.docx`/`.doc` | `DocxParser`             | Local, no API call.                     |
| `.txt`/`.md`   | (copied as-is)           | Renamed to `.md` in `markdown_out/`.    |

## Free-tier limits (Gemini)

`gemini-2.5-flash` / `gemini-3-flash-preview` free tier as of writing:

- 15 requests / minute
- 1500 requests / day
- 1 M tokens / day

`MultimodalParser` sends one request per PDF (the whole file as one input).
For typical office documents this is well inside the free tier. The script
prints the cumulative cost in USD; on the free tier this stays at $0.

## Why this stack and not...

- **Open WebUI's own PDF upload?** It uses a basic text extractor with no
  OCR, so scanned and dual PDFs come out empty. GAIK MultimodalParser fixes
  that and produces markdown that Open WebUI's RAG index handles cleanly.
- **GAIK's `RAGWorkflow` end-to-end?** It is great when you want full
  control of the retrieval stack, but for a one-laptop chatbot Open WebUI
  ships chat UI, knowledge management, multi-user, and conversation
  history out of the box. We let it do that and use GAIK only where it
  excels (parsing).
- **Helpdesk-chatbots `apps/studio`?** Studio's PDF parser is text-layer
  only (no OCR), its search is PostgreSQL FTS (not semantic), and it is
  locked to Azure/OpenAI -- none of which fit "local Ollama over scanned
  PDFs in a folder."

## Known limits

- Open WebUI's RAG defaults to dense retrieval; for very large corpora you
  may want hybrid + rerank. If that becomes the bottleneck, the next step
  is a dedicated GAIK `RAGWorkflow` example -- not in scope here.
- `MultimodalParser` uploads each PDF to Gemini once. If your documents
  are confidential and cannot leave the machine, this example is **not**
  suitable -- use the (forthcoming) Docling-based offline variant instead.
- The markdown output is plain text. Images embedded in PDFs are described
  in markdown form by the vision model; the original images are not
  exported to disk in this example.

## Links

- GAIK toolkit docs: <https://gaik-project.github.io/gaik-toolkit/>
- `MultimodalParser` source: `implementation_layer/src/gaik/software_components/parsers/multimodal_parser/`
- Gemini API quickstart: <https://ai.google.dev/gemini-api/docs/quickstart>
- Open WebUI: <https://github.com/open-webui/open-webui>
- Ollama models: <https://ollama.com/library>
