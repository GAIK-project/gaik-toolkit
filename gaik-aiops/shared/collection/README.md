# Collection, storage and correlation layer

One layer, built once, serving two consumers:

- WP4: security audit log (append-only, retention, pseudonymised identity, masked client address)
- WP5: central logging

Event envelope (draft): `schema/envelope.md`.
Metrics (usage, latency, errors): `metrics.md`.

```
producer --OTLP--> OpenTelemetry Collector --OTLP/HTTP JSON--> sink --> Postgres
                   (privacy processing)                                 collection.audit_events
                                                                        collection.log_events
                                                                        collection.correlated_events
```

| Path | What |
|---|---|
| `sql/001_schema.sql` | Tables, append-only guard for audit events, `purge_expired()`, correlation view, grants |
| `sink/` | OTLP/HTTP logs receiver that writes to Postgres (Python, psycopg) |
| `schema/envelope.md` | Envelope attributes, retention and privacy rules (draft) |
| `../../deploy/compose/otel-collector.yaml` | Ingress and privacy processing |

## Run and test locally

```bash
docker compose -f deploy/compose/docker-compose.yml up -d --build --wait
```

```bash
cd shared/collection/sink && uv run --python 3.12 --extra dev pytest -q
```

The stack tests send events through the collector and check pseudonymisation, address masking, the
append-only guarantees, role permissions, purging, and the metrics derived from spans and logs in
Prometheus, and that a span reaches MLflow pseudonymised, address-masked and without prompt or response
content (`tests/test_mlflow_stack.py`). They are skipped when the stack is not running.

The collector drops the spans of `wizard-v2-api`'s `/health` probes, the server span and its child
spans, from the traces pipeline before anything else is done with them (`filter/health`), so they
reach neither MLflow nor the span metrics. Other services' spans are not filtered.

MLflow runs at `http://127.0.0.1:5000`. Each application listed in `MLFLOW_EXPERIMENTS` (service names,
default `wizard-v2-api,wizard-v2-web,gaik-poc,example-producer`) gets its own experiment, named after
its `service.name`: the one-shot `mlflow-setup` service creates the experiments and writes the
collector's routes to them (`deploy/compose/mlflow/setup_experiments.py`), because MLflow assigns
experiment ids itself. Traces from any other service go to experiment `0` (Default). Adding an
application means adding its name and running `up` again. On an existing `pgdata` volume the init scripts do not run
again, so create the MLflow database once by hand:

```bash
docker compose -f deploy/compose/docker-compose.yml exec -T postgres psql -U wp45 -d observability < deploy/compose/initdb/01-mlflow.sql
```

Pseudonymisation key from the vault instead of `PSEUDONYM_KEY`: `deploy/compose/openbao.yml` overlay,
see `wp4/secrets/README.md`. Either way the collector pseudonymises once, so a user has one pseudonym in
Postgres, MLflow and Prometheus (`tests/test_one_pseudonym.py`).

## Not yet covered

- MLflow has no sign-in in front of it; it listens on localhost only (OIDC in front is WP4 work)
- Body content is stored as sent; per-class body rules are an open point in the envelope draft
- Scheduled purge (a cron job or Kubernetes CronJob calling `collection.purge_expired()`)
