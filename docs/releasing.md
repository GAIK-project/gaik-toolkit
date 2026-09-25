# Release certification

Every tag and PyPI release is gated by the same local/CI command:

```sh
uv run python scripts/release_check.py --live --version X.Y.Z
```

Commit the intended release first, including `gaik_validated_version.txt` set to
the planned version. The report is bound to that commit. Development install
versions may differ before tagging; the wizard pin and built wheel must match
`--version`, and the registry audit must have no actionable drift.

The command synchronizes **all extras**, runs the offline unit suite, wizard tests
and strict registry audit, builds/checks the distributions, then makes real
authenticated requests with synthetic data. Required live checks are chat,
streaming, SchemaGenerator → DataExtractor, AnswerGenerator, and a PDF through
DocumentClassifier. Embedder is also required when an embedding model is selected.
It writes a sanitized `results/release-check.json` and exits nonzero for any failed,
missing, incomplete, or timed-out required check. It never treats having a key as
successful authentication. Reports contain model IDs and status, never credentials,
raw request/response bodies, or provider exception messages.

Packaging must produce one wheel and one source distribution, each below 10 MiB.
The wheel is built from the source distribution and both must preserve every
library Python file, SQL script, and `py.typed` marker byte for byte. The source
archive allows only the library and build metadata; demo applications, evaluation
data, environment files, and repository media are excluded by `MANIFEST.in`.
Artifact names, sizes, and SHA-256 hashes are recorded in the report. The publish
job repeats this validation and fails if any upload fails, including an existing
artifact; it does not report a partially uploaded version as successful.

Configure a small representative matrix with environment variables:

| Variable | Meaning |
| --- | --- |
| `RELEASE_PROVIDERS` | Comma-separated providers; defaults to `azure` |
| `RELEASE_AZURE_MODEL` | Exact Azure deployment; CI defaults to `gpt-6-luna` |
| `RELEASE_OPENAI_MODEL` | Exact OpenAI model ID |
| `RELEASE_GOOGLE_MODEL` | Exact Gemini model ID |
| `RELEASE_VERTEX_MODEL` | Exact Vertex AI model ID; requires Google Cloud credentials/project |
| `RELEASE_AITTA_MODEL` | Exact Aitta catalog model ID |
| `RELEASE_ANTHROPIC_MODEL` | Exact Anthropic model ID |
| `RELEASE_<PROVIDER>_EMBEDDING_MODEL` | Optional explicit embedding model/deployment |
| `RELEASE_<PROVIDER>_BACKENDS` | `native` (default), `litellm`, or `native,litellm` |

Standard provider credential variables are used by `get_llm_config()`. Local model
selection also accepts the corresponding standard model variable, e.g.
`AZURE_DEPLOYMENT`, when no release-specific model is set; the resolved ID is always
recorded. Missing selected credentials or models fail. Verify current official
catalogs before setting model IDs. Every changed provider/model family needs live
evidence; the full catalog is evaluated separately when needed.

For native and LiteLLM certification of the same deployment, set e.g.
`RELEASE_AZURE_BACKENDS=native,litellm`. The runner maps the native deployment ID
to `azure/<deployment>` and forwards the Azure endpoint and API version explicitly.
For Google it uses `gemini/`, and for OpenAI/Aitta it uses `openai/`. CI always keeps
the native Azure target even if the repository variable selects only LiteLLM.

Each selected provider gets at most 10 calls through the real provider clients,
normally 7 without embeddings. A thin client decorator caps output at 2048 tokens
per call while the components execute their public methods. The budget proxies
preserve constructor-selected raw OpenAI/Azure SDK paths and native adapter paths;
they do not replace raw SDK clients with adapters or normalize sampling parameters.
This tests the components' actual default behavior on the selected model. The request timeout
defaults to 180 seconds and the provider subprocess deadline to 900 seconds.
For a cold Aitta model or a reasoning model, explicitly adjust `--request-timeout`,
`--provider-timeout`, or `--output-tokens` (maximum 8192). The model list is never
expanded automatically. Embeddings use only two short synthetic strings.

For additional provider certification without rebuilding a release, run the same
worker directly and retain its sanitized report:

```sh
uv run --no-sync python scripts/release_smoke.py --provider openai --model MODEL_ID --result results/openai-live.json
```

This individual report is supplementary evidence; it does not replace the full
release gate. The publish workflow runs the full gate on the exact tag commit,
always requires Azure, adds any providers in the repository `RELEASE_PROVIDERS`
variable, and uploads the report as a workflow artifact. Ordinary pull requests
still run deterministic tests without requiring credentials.
