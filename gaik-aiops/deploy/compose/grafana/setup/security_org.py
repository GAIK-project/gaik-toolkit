"""Creates the Grafana "Security" organisation with the audit datasource and dashboards (idempotent).

Why a separate organisation: Grafana OSS has no datasource permissions, and any member of an
organisation can query every datasource in it through /api/ds/query, regardless of folder permissions.
Keeping the audit store in its own organisation, joined only by the admin role (OIDC org mapping), is
what keeps the audit log away from viewers and experts.

File provisioning cannot create organisations and fails on unknown ones, so this runs against the API
after Grafana starts. It then re-applies every RECONCILE_SECONDS (default 300), so changes made by hand
are reverted, and signals readiness with the file /tmp/ready for the container healthcheck.
Environment: GRAFANA_URL, GRAFANA_ADMIN_USER, GRAFANA_ADMIN_PASSWORD, AUDIT_READER_PASSWORD,
DASHBOARDS_DIR, RECONCILE_SECONDS (0 = run once and exit).
"""

import base64
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

URL = os.environ.get("GRAFANA_URL", "http://grafana:3000").rstrip("/")
AUTH = base64.b64encode(f"{os.environ['GRAFANA_ADMIN_USER']}:{os.environ['GRAFANA_ADMIN_PASSWORD']}".encode()).decode()
ORG = "Security"


def api(method, path, body=None, org=None):
    headers = {"Authorization": f"Basic {AUTH}", "Content-Type": "application/json"}
    if org is not None:
        headers["X-Grafana-Org-Id"] = str(org)
    req = urllib.request.Request(f"{URL}{path}", method=method, headers=headers,
                                 data=None if body is None else json.dumps(body).encode())
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


class SetupError(Exception):
    pass


def ok(result, what):
    status, body = result
    if status >= 300:
        raise SetupError(f"{what}: HTTP {status} {body}")
    return body


def wait_for_grafana():
    for _ in range(60):
        try:
            if api("GET", "/api/health")[0] == 200:
                break
        except OSError:
            pass
        time.sleep(2)
    else:
        sys.exit("grafana not reachable")


def apply():
    status, org = api("GET", f"/api/orgs/name/{ORG}")
    org_id = org["id"] if status == 200 else ok(api("POST", "/api/orgs", {"name": ORG}), "create org")["orgId"]

    datasource = {
        "name": "Audit store", "uid": "audit-store", "type": "grafana-postgresql-datasource", "access": "proxy",
        "url": "postgres:5432", "user": "collection_reader",
        "jsonData": {"database": "observability", "sslmode": "disable", "postgresVersion": 1600},
        "secureJsonData": {"password": os.environ["AUDIT_READER_PASSWORD"]},
    }
    if api("GET", "/api/datasources/uid/audit-store", org=org_id)[0] == 200:
        ok(api("PUT", "/api/datasources/uid/audit-store", datasource, org=org_id), "update datasource")
    else:
        ok(api("POST", "/api/datasources", datasource, org=org_id), "create datasource")

    if api("GET", "/api/folders/security", org=org_id)[0] != 200:
        ok(api("POST", "/api/folders", {"uid": "security", "title": "Security"}, org=org_id), "create folder")
    for path in sorted(Path(os.environ.get("DASHBOARDS_DIR", "/dashboards/security")).glob("*.json")):
        dash = json.loads(path.read_text())
        dash.pop("id", None)
        ok(api("POST", "/api/dashboards/db", {"dashboard": dash, "folderUid": "security", "overwrite": True},
               org=org_id), f"dashboard {path.name}")
        # Remove copies left in the main organisation by volumes created before the split.
        api("DELETE", f"/api/dashboards/uid/{dash['uid']}", org=1)

    status, folders = api("GET", "/api/folders", org=1)
    for folder in folders if status == 200 else []:
        if folder["title"] == "Security":
            api("DELETE", f"/api/folders/{folder['uid']}", org=1)

    return org_id


def main():
    wait_for_grafana()
    try:
        print(f"security organisation ready (id {apply()})", flush=True)
    except SetupError as exc:
        sys.exit(str(exc))
    interval = int(os.environ.get("RECONCILE_SECONDS", "300"))
    if interval <= 0:
        return
    Path("/tmp/ready").touch()
    while True:
        time.sleep(interval)
        try:
            apply()
        except (SetupError, OSError) as exc:
            print(f"reconcile failed: {exc}", file=sys.stderr, flush=True)


if __name__ == "__main__":
    main()
