"""Grafana login through Keycloak with the WP4 role mapping (browser flow driven over HTTP).

Start first:
  docker compose -f deploy/compose/docker-compose.yml -f deploy/compose/identity.yml up -d --build --wait
Skipped when Grafana has no OIDC login configured.
"""

import html
from contextlib import closing
import re

import httpx
import pytest

GRAFANA = "http://localhost:3000"
AUDIT_QUERY = {"queries": [{"refId": "A", "datasource": {"uid": "audit-store"}, "format": "table",
                            "rawSql": "SELECT count(*) FROM collection.audit_events"}]}


def _oidc_enabled() -> bool:
    try:
        r = httpx.get(f"{GRAFANA}/login/generic_oauth", timeout=3)
    except httpx.HTTPError:
        return False
    return r.status_code in (302, 303) and "localhost:8180" in r.headers.get("location", "")


pytestmark = pytest.mark.skipif(not _oidc_enabled(), reason="Grafana with OIDC overlay not running")


def login(user: str) -> httpx.Client:
    client = httpx.Client(follow_redirects=True, timeout=15)
    page = client.get(f"{GRAFANA}/login/generic_oauth")
    action = html.unescape(re.search(r'<form[^>]+id="kc-form-login"[^>]+action="([^"]+)"', page.text).group(1))
    # Keycloak marks its cookies Secure. Browsers send those to http://localhost, httpx does not.
    for cookie in client.cookies.jar:
        cookie.secure = False
    client.post(action, data={"username": user, "password": f"{user}-local-only", "credentialId": ""})
    return client


def orgs(client: httpx.Client) -> dict[str, str]:
    r = client.get(f"{GRAFANA}/api/user/orgs")
    return {o["name"]: o["role"] for o in r.json()} if r.status_code == 200 else {}


def audit_query(client: httpx.Client, org_id: int) -> int:
    return client.post(f"{GRAFANA}/api/ds/query", json=AUDIT_QUERY,
                       headers={"X-Grafana-Org-Id": str(org_id)}).status_code


def test_admin_gets_main_admin_and_security_viewer():
    with closing(login("security-admin")) as c:
        user = c.get(f"{GRAFANA}/api/user").json()
        assert user["login"] == "security-admin" and user["isGrafanaAdmin"] is False
        assert orgs(c) == {"Main Org.": "Admin", "Security": "Viewer"}
        assert audit_query(c, 2) == 200
        # Viewer in Security: can read the audit log, cannot change its datasource.
        assert c.delete(f"{GRAFANA}/api/datasources/uid/audit-store",
                        headers={"X-Grafana-Org-Id": "2"}).status_code == 403


@pytest.mark.parametrize("user", ["viewer", "expert", "approver"])
def test_other_roles_are_viewers_without_audit_access(user):
    with closing(login(user)) as c:
        assert orgs(c) == {"Main Org.": "Viewer"}
        assert c.get(f"{GRAFANA}/api/dashboards/uid/gaik-service-health").status_code == 200
        # The audit datasource does not exist in their organisation, and they cannot switch to Security.
        assert audit_query(c, 1) != 200
        assert audit_query(c, 2) in (401, 403)
        assert c.get(f"{GRAFANA}/api/dashboards/uid/gaik-audit-trail").status_code == 404


def test_user_without_role_is_refused():
    with closing(login("norole")) as c:
        assert c.get(f"{GRAFANA}/api/user").status_code == 401
        assert orgs(c) == {}
