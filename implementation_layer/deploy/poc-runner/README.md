# wizard-v2-poc-runner

The image a sandbox PoC run executes in. `deploy/openshift/sandbox-job.yaml`
(S5-1 / #89) names it for both of its containers: the init container fetches and
unzips the package over HTTP, the run container executes `python run_poc.py` in
`/workspace/poc`. #91's SandboxRunner submits those Jobs.

## Build

```bash
cd implementation_layer/deploy/openshift
PROJECT=<staging-project> ./deploy.sh poc-runner
```

Locally, without a cluster:

```bash
docker build -t wizard-v2-poc-runner:local implementation_layer/deploy/poc-runner
```

## Two decisions worth knowing

**Dependencies are baked in, not installed per run.** The Job sets
`readOnlyRootFilesystem: true` and `activeDeadlineSeconds: 600`, so a
`pip install -r requirements.txt` at run time would need a writable
site-packages and would spend minutes of the run's own budget on packages that
never change. Baking them in also means the run needs no PyPI egress, which
matters once #90 restricts egress to the LLM endpoints.

**Only the extras the five use cases import.** `gaik[all-cpu]` looks like the
safe superset and is not: its classifier/RAG/Finnish-NLP extras drag in the CUDA
build of torch, and the image came out at **7.32 GB, 5.1 GB of it GPU stack** a
sandbox that only calls HTTP APIs never executes. Worse than waste — a Job's
deadline clock covers the image pull. The named union is **744 MB**.

| | size |
|---|---|
| `gaik[all-cpu]` + llm-judge + vision-extract | 7.32 GB |
| the eight extras the use cases need, + ffmpeg | 744 MB |

A PoC that selects a component outside that set (a classifier, a RAG workflow)
fails on import. That is the intended trade: the acceptance criterion is those
five use cases, and adding an extra is a one-line `GAIK_EXTRAS` change plus a
rebuild. The build's import smoke test is what keeps such a miss legible.

`ffmpeg` is installed because pydub shells out to it and UC01 hands it audio.
Without it pydub only warns at import, then fails deep inside the transcriber.

## Version pinning

`GAIK_VERSION` pins the toolkit the runs execute against (currently 0.9.0 from
PyPI). A generated PoC's `requirements.txt` asks for `gaik[extract]` and friends
unversioned, so without the pin two runs a week apart could use different
toolkits. The wizard's component registry is synced against one version — bump
this together with `gaik-sync` (see AGENTS.md), never on its own.

## Verified locally, and what is not

Run against a scaffolded UC01 package under the Job's own constraints
(`--user 1001:0 --read-only --tmpfs /tmp --cap-drop ALL`):

- `run_poc.py` is found and executed — this is the entrypoint the manifest names
  and the scaffolder writes, after #159's fix
- gaik imports resolve; `AudioToStructuredData` loads
- the run works as a non-root arbitrary UID with a read-only root filesystem
- ffmpeg is on PATH and pydub picks it up
- it stops at `ERROR: No audio file found in .../sample_input` — an application
  error, not an infrastructure one

**Not verified:** an actual model call. That needs `AZURE_API_KEY`, which no
developer machine here holds, so the first real end-to-end run happens in Rahti
with the `gaik-demo-api-keys` secret the manifest reads.
