# Quickstart: send traces to the stack

For anyone writing instrumentation (hooks in toolkit components, an application's own spans). The
producer side of the contract is OpenTelemetry over OTLP/HTTP to the collector, nothing else: no storage
product in the producer, no direct calls to MLflow, Postgres or Prometheus.

## 1. Start the stack

Needs Docker (Colima on macOS: the clone must be under your home directory, which is what Colima
shares with its VM).

```bash
docker compose -f deploy/compose/docker-compose.yml up -d --build --wait
```

| Service | Address | What for |
|---|---|---|
| Collector (OTLP/HTTP) | `http://127.0.0.1:4318` | Where producers send |
| MLflow | `http://127.0.0.1:5000` | Traces, later evaluations and feedback |
| Grafana | `http://127.0.0.1:3000` (`admin` / `admin-local-only`) | Service health, alerts |
| Prometheus | `http://127.0.0.1:9090` | Metrics derived from spans and logs |

## 2. Send an example

```bash
uv run wp5-a1/examples/send_llm_call.py
```

It sends a component run (parent span) with one model call (child span). Open MLflow, experiment
*example-producer*, and the trace is there with its tokens and cost, the identity replaced by `enduser.pseudo.id`
and the prompt gone.

## 3. Point your own code at it

Standard OpenTelemetry environment variables, no GAIK-specific switch needed:

```bash
export OTEL_EXPORTER_OTLP_ENDPOINT=http://127.0.0.1:4318
export OTEL_SERVICE_NAME=my-component
```

Each application gets its own MLflow experiment, named after `OTEL_SERVICE_NAME`, when the name is
listed in `MLFLOW_EXPERIMENTS` (see `deploy/compose/docker-compose.yml`); anything else lands in
*Default*. To add one:

```bash
MLFLOW_EXPERIMENTS=wizard-v2-api,wizard-v2-web,gaik-poc,example-producer,my-component docker compose -f deploy/compose/docker-compose.yml up -d --wait
```

## What the collector does to every span

Before any destination sees it (`deploy/compose/otel-collector.yaml`, `transform/privacy`):

- `enduser.id` becomes `enduser.pseudo.id` (keyed hash); the raw value is deleted
- `client.address` is masked to /24 (IPv4) or /48 (IPv6)
- `gen_ai.input.messages`, `gen_ai.output.messages`, `gen_ai.prompt*`, `gen_ai.completion*`,
  `mlflow.spanInputs` and `mlflow.spanOutputs` are dropped

So producers send the identity as it is and keep content off by default; the collector is the second
line of defence, not the only one.

## Names

- OTel GenAI semantic conventions where they exist: `gen_ai.operation.name`, `gen_ai.system`,
  `gen_ai.request.model`, `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`
- `gaik.*` for the rest: `gaik.event.class` (`llm_call`, `evaluation`, `feedback`), `gaik.component`,
  `gaik.run.id`, `gaik.config.blueprint_version`, `gaik.cost.eur`

The `gaik.*` names are a **draft** until the event schema v1 is agreed; the example and this list change
with it.

## Check your change

```bash
cd shared/collection/sink && uv run --python 3.12 --extra dev pytest -q
```

The stack tests run against the compose stack and are skipped when it is not running. CI runs the same
tests against a fresh stack on every pull request.
