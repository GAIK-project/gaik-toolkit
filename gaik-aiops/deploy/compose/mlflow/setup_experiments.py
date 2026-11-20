"""Create one MLflow experiment per application and write the collector's routes to them.

MLflow assigns experiment ids itself, so the collector cannot name them in a static config. This runs
once before the collector starts: it makes sure an experiment exists for every application in
MLFLOW_EXPERIMENTS (experiment name = OTel service.name), then writes a collector config fragment that
routes each application's traces to its experiment. Traces from any other service go to the Default
experiment (id 0) through the base config's otlphttp/mlflow exporter.

An application's pipeline to MLflow can leave spans out (NOT_IN_MLFLOW). That happens after the span
metrics are taken, so Prometheus and Grafana count those requests as before.

The fragment is JSON, which the collector reads as YAML. Re-running is safe: existing experiments are
reused.

Environment:
    MLFLOW_TRACKING_URI   e.g. http://mlflow:5000
    MLFLOW_EXPERIMENTS    comma-separated service names
    ROUTES_FILE           where to write the fragment
"""

import json
import os
import re
import sys

from mlflow import MlflowClient

NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")

# Spans MLflow does not store, by application: conditions for the collector's filter processor, read
# for each span (a span that matches one is dropped). They apply only in that application's pipeline
# to MLflow, so the span metrics, and the alerts and dashboards built on them, still see every span.
#
# The filter sees one span at a time, not the trace. A request is left out whole only while each of
# its spans matches a condition, so a span added under one of these requests in the application needs
# its condition here, or it is stored alone.
KEEP_FAILED = " and status.code != STATUS_CODE_ERROR"
NOT_IN_MLFLOW = {
    "wizard-v2-api": [
        # Kubernetes probes, every few seconds: the GET /health server span and FastAPI's child spans
        # under it, which carry only the endpoint function's name. A failing probe is left out too:
        # an outage would otherwise fill MLflow with probes, and the error ratio already shows it.
        'attributes["http.route"] == "/health"',
        'attributes["code.function.name"] == "wizard_api.main.health"',
        # The web app's page requests, which are no step of a session and would each be a row of their
        # own beside the conversation: listing, opening and creating a session, and claiming old ones. The
        # server spans are matched by name, because PATCH /sessions/{session_id} (kept: it carries the
        # session) has the same route as the GET. A route that is not listed here is always stored.
        # A page request the API failed (5xx: the server span has an error status) keeps that span,
        # with its route and status code. The child spans are left out whatever their status, so a
        # refused request (4xx), where only a child span is marked, leaves no span without its parent.
        'name == "GET /sessions"' + KEEP_FAILED,
        'name == "GET /sessions/{session_id}"' + KEEP_FAILED,
        'name == "POST /sessions"' + KEEP_FAILED,
        'name == "POST /owners/claim"' + KEEP_FAILED,
        'attributes["code.function.name"] == "wizard_api.routers.sessions.list_sessions"',
        'attributes["code.function.name"] == "wizard_api.routers.sessions.get_session"',
        'attributes["code.function.name"] == "wizard_api.routers.sessions.create_session"',
        'attributes["code.function.name"] == "wizard_api.routers.owners.claim_legacy_sessions"',
        # What the web app reads in the background while a session is open: the PoC tab's package,
        # its file list, one file and the test inputs, every few seconds, and a reply's stream being
        # rejoined. They carry the session, so each would be a row inside it, between the turns,
        # gate changes and test runs the session is read for. What the user does there (uploading
        # an input, checking or running the package, saving a file) is stored. A read the API failed
        # keeps its server span, as above.
        'name == "GET /sessions/{session_id}/poc"' + KEEP_FAILED,
        'name == "GET /sessions/{session_id}/poc/files"' + KEEP_FAILED,
        'name == "GET /sessions/{session_id}/poc/file"' + KEEP_FAILED,
        'name == "GET /sessions/{session_id}/poc/input"' + KEEP_FAILED,
        'name == "GET /sessions/{session_id}/chat/stream"' + KEEP_FAILED,
        'attributes["code.function.name"] == "wizard_api.routers.sessions.download_poc"',
        'attributes["code.function.name"] == "wizard_api.routers.sessions.list_poc_files"',
        'attributes["code.function.name"] == "wizard_api.routers.sessions.read_poc_file"',
        'attributes["code.function.name"] == "wizard_api.routers.sessions.list_poc_inputs"',
        'attributes["code.function.name"] == "wizard_api.routers.sessions.chat_stream"',
    ],
}


def experiment_ids(client: MlflowClient, names: list[str]) -> dict[str, str]:
    ids = {}
    for name in names:
        found = client.get_experiment_by_name(name)
        ids[name] = found.experiment_id if found else client.create_experiment(name, tags={"service.name": name})
    return ids


def routes(ids: dict[str, str]) -> dict:
    exporters, processors, pipelines, table = {}, {}, {}, []
    for name, experiment_id in ids.items():
        key = re.sub(r"[^A-Za-z0-9_-]", "_", name)
        exporters[f"otlphttp/mlflow-{key}"] = {
            "traces_endpoint": "http://mlflow:5000/v1/traces",
            "headers": {"x-mlflow-experiment-id": experiment_id},
        }
        pipeline = {"receivers": ["routing/mlflow"], "exporters": [f"otlphttp/mlflow-{key}"]}
        if name in NOT_IN_MLFLOW:
            # The filter is defined and used in this fragment alone: the base config does not know it.
            processors[f"filter/mlflow-{key}"] = {"error_mode": "ignore", "traces": {"span": NOT_IN_MLFLOW[name]}}
            pipeline["processors"] = [f"filter/mlflow-{key}"]
        pipelines[f"traces/mlflow-{key}"] = pipeline
        table.append({
            "statement": f'route() where attributes["service.name"] == "{name}"',
            "pipelines": [f"traces/mlflow-{key}"],
        })
    pipelines["traces/mlflow-default"] = {"receivers": ["routing/mlflow"], "exporters": ["otlphttp/mlflow"]}
    # Only the exporters change: the collector merges this fragment into the base config and
    # replaces lists, so the traces pipeline keeps the base's receivers and processors (the
    # privacy rules and the session rule) and spans reach the router processed.
    pipelines["traces"] = {"exporters": ["spanmetrics", "routing/mlflow"]}
    fragment = {
        "connectors": {"routing/mlflow": {"default_pipelines": ["traces/mlflow-default"], "table": table}},
        "exporters": exporters,
        "service": {"pipelines": pipelines},
    }
    if processors:
        fragment["processors"] = processors
    return fragment


def unfiltered(names: list[str]) -> list[str]:
    """Applications with spans to leave out that get no pipeline of their own, so no filter either."""
    return sorted(set(NOT_IN_MLFLOW) - set(names))


def main() -> int:
    names = [n.strip() for n in os.environ.get("MLFLOW_EXPERIMENTS", "").split(",") if n.strip()]
    bad = [n for n in names if not NAME.match(n)]
    if bad:
        print(f"invalid service names: {bad}", file=sys.stderr)
        return 1
    ids = experiment_ids(MlflowClient(), names)
    # With no applications listed the fragment is empty and every trace goes to Default.
    with open(os.environ["ROUTES_FILE"], "w", encoding="utf-8") as fh:
        json.dump(routes(ids) if ids else {}, fh, indent=2)
    for name, experiment_id in ids.items():
        print(f"{name} -> experiment {experiment_id}")
    for name in unfiltered(names):
        print(f"warning: {name} is not in MLFLOW_EXPERIMENTS, so all its spans are stored, in Default", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
