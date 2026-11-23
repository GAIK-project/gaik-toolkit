"""Dashboard and alerting platform checks against the local compose stack.

Alert rule logic itself is unit-tested with promtool
(deploy/compose/prometheus/tests/collection-alerts.test.yml).
Skipped when the stack is not reachable.
"""

import base64
import json
import os
import urllib.error
import urllib.parse
import urllib.request

import pytest

PROM = "http://127.0.0.1:9090"
ALERTMANAGER = "http://127.0.0.1:9093"
GRAFANA = "http://127.0.0.1:3000"
GRAFANA_AUTH = "admin:" + os.environ.get("GRAFANA_ADMIN_PASSWORD", "admin-local-only")


def get(url: str, auth: str | None = None, org: int | None = None):
    req = urllib.request.Request(url)
    if org is not None:
        req.add_header("X-Grafana-Org-Id", str(org))
    if auth:
        req.add_header("Authorization", "Basic " + base64.b64encode(auth.encode()).decode())
    with urllib.request.urlopen(req, timeout=5) as resp:
        return json.load(resp)


def _up() -> bool:
    try:
        get(f"{GRAFANA}/api/health")
        get(f"{ALERTMANAGER}/api/v2/status")
    except Exception:  # noqa: BLE001
        return False
    return True


pytestmark = pytest.mark.skipif(not _up(), reason="compose stack not running")


def test_prometheus_sends_alerts_to_alertmanager():
    active = get(f"{PROM}/api/v1/alertmanagers")["data"]["activeAlertmanagers"]
    assert any("alertmanager:9093" in a["url"] for a in active)


def test_alert_rules_loaded_and_healthy():
    groups = get(f"{PROM}/api/v1/rules?type=alert")["data"]["groups"]
    rules = {r["name"]: r for g in groups for r in g["rules"]}
    assert {
        "HighErrorRatio",
        "HighLatencyP95",
        "ErrorLogs",
        "CollectorDown",
        "EventDeliveryBacklog",
        "EventDeliveryFailing",
    } <= set(rules)
    assert all(r["health"] in ("ok", "unknown") and not r.get("lastError") for r in rules.values())


def test_collector_is_monitored():
    targets = get(f"{PROM}/api/v1/targets")["data"]["activeTargets"]
    collector = [t for t in targets if t["labels"]["job"] == "otel-collector"]
    assert collector and collector[0]["health"] == "up"


def test_grafana_requires_login():
    with pytest.raises(urllib.error.HTTPError) as err:
        get(f"{GRAFANA}/api/search")
    assert err.value.code == 401


def test_grafana_datasources_reach_their_backends():
    # The audit store lives in the separate "Security" organisation (id 2).
    for uid, org in (("prometheus", 1), ("audit-store", 2)):
        health = get(f"{GRAFANA}/api/datasources/uid/{uid}/health", GRAFANA_AUTH, org)
        assert health["status"] == "OK", (uid, health)
    status = get(f"{GRAFANA}/api/datasources/proxy/uid/alertmanager/api/v2/status", GRAFANA_AUTH)
    assert "cluster" in status


def test_dashboards_are_provisioned_in_their_folders():
    found = {
        (org, d["uid"]): d["folderTitle"]
        for org in (1, 2)
        for d in get(f"{GRAFANA}/api/search?type=dash-db", GRAFANA_AUTH, org)
    }
    assert found == {
        (1, "gaik-service-health"): "Monitoring",
        (1, "gaik-wizard-operations"): "Monitoring",
        (1, "gaik-hackathon-live"): "Monitoring",
        (2, "gaik-audit-trail"): "Security",
    }


def test_audit_store_is_not_in_the_main_organisation():
    # Any member of an organisation can query its datasources through the API (Grafana OSS), so the
    # audit store must not exist where viewers are.
    uids = {d["uid"] for d in get(f"{GRAFANA}/api/datasources", GRAFANA_AUTH, 1)}
    assert "audit-store" not in uids


def test_dashboard_queries_return_data_shape():
    # Every Prometheus expression in the service dashboard must parse.
    dash = get(f"{GRAFANA}/api/dashboards/uid/gaik-service-health", GRAFANA_AUTH)["dashboard"]
    exprs = [t["expr"] for p in dash["panels"] for t in p.get("targets", []) if "expr" in t]
    assert exprs
    for expr in exprs:
        expr = expr.replace('=~"$service"', '=~".+"')
        url = f"{PROM}/api/v1/query?" + urllib.parse.urlencode({"query": expr})
        assert get(url)["status"] == "success", expr

