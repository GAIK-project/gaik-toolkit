# Sample applications

End-user applications that consume the toolkit's components and the FastAPI backend. They live in their own repositories under the [GAIK-project](https://github.com/GAIK-project) organization so each can pick its own stack and release cycle.

| Application | Stack | Toolkit endpoints used |
|---|---|---|
| [`gaik-form-filler`](https://github.com/GAIK-project/gaik-form-filler) — Chrome extension that fills any web form with an LLM from free-form text, with a human-approved review step. | Vite + Bun + React 19, Manifest V3 | `/extract/form/`, `/form/understand/` |

Want to add yours? Open a PR that adds a row here.
