"""Metrics pipeline checks against the local compose stack.

Spans, log records and a producer metric go in through the collector; the
derived and passed-through series must show up in Prometheus.
Skipped when the stack is not reachable.
"""

import json
import secrets
import time
import urllib.parse
import urllib.request

import pytest

OTLP = "http://127.0.0.1:4318"
PROM = "http://127.0.0.1:9090"


def _up() -> bool:
    try:
        urllib.request.urlopen(f"{PROM}/-/ready", timeout=2)
        urllib.request.urlopen(OTLP, timeout=2)
    except urllib.error.HTTPError:
        return True
    except Exception:  # noqa: BLE001
        return False
    return True


pytestmark = pytest.mark.skipif(not _up(), reason="compose stack not running")


def post(path: str, body: dict) -> None:
    req = urllib.request.Request(
        f"{OTLP}{path}", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}
    )
    urllib.request.urlopen(req, timeout=5)


def query(expr: str) -> list[dict]:
    url = f"{PROM}/api/v1/query?" + urllib.parse.urlencode({"query": expr})
    with urllib.request.urlopen(url, timeout=5) as resp:
        return json.load(resp)["data"]["result"]


def wait_value(expr: str, timeout: float = 30) -> dict[str, float]:
    """Poll until the query returns something; result keyed by status_code or ''."""
    deadline = time.time() + timeout
    while True:
        result = query(expr)
        if result or time.time() > deadline:
            return {r["metric"].get("status_code", ""): float(r["value"][1]) for r in result}
        time.sleep(1)


@pytest.fixture(scope="module")
def service() -> str:
    name = f"metrics-test-{secrets.token_hex(4)}"
    now = time.time_ns()
    resource = {"attributes": [{"key": "service.name", "value": {"stringValue": name}}]}
    spans = [
        {
            "traceId": secrets.token_hex(16),
            "spanId": secrets.token_hex(8),
            "name": "POST /items",
            "kind": 2,  # server
            "startTimeUnixNano": str(now - ms * 1_000_000),
            "endTimeUnixNano": str(now),
            "status": {"code": code},
        }
        for ms, code in [(40, 1), (120, 1), (900, 2)]
    ]
    post("/v1/traces", {"resourceSpans": [{"resource": resource, "scopeSpans": [{"spans": spans}]}]})
    post(
        "/v1/logs",
        {
            "resourceLogs": [
                {
                    "resource": resource,
                    "scopeLogs": [
                        {
                            "logRecords": [
                                {"timeUnixNano": str(now), "severityNumber": 17, "body": {"stringValue": "failed"}},
                                {"timeUnixNano": str(now), "severityNumber": 9, "body": {"stringValue": "ok"}},
                            ]
                        }
                    ],
                }
            ]
        },
    )
    post(
        "/v1/metrics",
        {
            "resourceMetrics": [
                {
                    "resource": resource,
                    "scopeMetrics": [
                        {
                            "metrics": [
                                {
                                    # Delta on purpose: the pipeline must convert it for Prometheus.
                                    "name": "producer.items.processed",
                                    "sum": {
                                        "aggregationTemporality": 1,
                                        "isMonotonic": True,
                                        "dataPoints": [
                                            {
                                                "startTimeUnixNano": str(now - 10**9),
                                                "timeUnixNano": str(now),
                                                "asInt": "5",
                                            }
                                        ],
                                    },
                                }
                            ]
                        }
                    ],
                }
            ]
        },
    )
    return name


def test_request_counts_by_status_from_spans(service):
    calls = wait_value(f'traces_span_metrics_calls_total{{service_name="{service}"}}')
    assert calls == {"STATUS_CODE_OK": 2.0, "STATUS_CODE_ERROR": 1.0}


def test_latency_histogram_from_spans(service):
    sel = f'service_name="{service}"'
    assert wait_value(f"sum(traces_span_metrics_duration_milliseconds_count{{{sel}}})") == {"": 3.0}
    # 40 ms and 120 ms fall under 250 ms; the 900 ms span does not.
    assert wait_value(f'sum(traces_span_metrics_duration_milliseconds_bucket{{{sel}, le="250"}})') == {"": 2.0}


def test_log_volume_and_errors_from_logs(service):
    assert wait_value(f'gaik_log_records_total{{service_name="{service}"}}') == {"": 2.0}
    assert wait_value(f'gaik_log_errors_total{{service_name="{service}"}}') == {"": 1.0}


def test_producer_metric_passes_through_as_cumulative(service):
    assert wait_value(f'producer_items_processed_total{{service_name="{service}"}}') == {"": 5.0}


def test_recording_rules_are_loaded_and_healthy():
    with urllib.request.urlopen(f"{PROM}/api/v1/rules", timeout=5) as resp:
        rules = [r for g in json.load(resp)["data"]["groups"] for r in g["rules"]]
    names = {r["name"] for r in rules}
    assert {"gaik:requests:rate5m", "gaik:request_errors:ratio5m", "gaik:request_latency_ms:p95_5m"} <= names
    assert all(r["health"] in ("ok", "unknown") and not r.get("lastError") for r in rules)
