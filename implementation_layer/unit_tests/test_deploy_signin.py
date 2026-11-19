"""Sign-in through Keycloak: the proxy, its Route and Keycloak fit together.

``deploy.sh signin`` puts oauth2-proxy (``signin-proxy.yaml``) in front of a
stack's web app and points the stack's Route at it (``route-signin.yaml``); the
web app then checks the forwarded token (``lib/proxy-auth.ts``). Keycloak itself
is ``deploy/keycloak``. A wrong name or address in any of these lets nobody in,
or leads one stack's sign-in to another stack, and only shows on the cluster.
These tests render the files the way the scripts apply them.
"""

import json
import re
import subprocess
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

DEPLOY_DIR = Path(__file__).resolve().parents[1] / "deploy"
OPENSHIFT_DEPLOY = DEPLOY_DIR / "openshift" / "deploy.sh"
KEYCLOAK_DIR = DEPLOY_DIR / "keycloak"
PROJECT = "proj"


def render(manifest: str, instance: str) -> list[dict]:
    result = subprocess.run(
        ["bash", str(OPENSHIFT_DEPLOY), "render", manifest],
        capture_output=True,
        text=True,
        env={"PROJECT": PROJECT, "INSTANCE": instance, "PATH": "/usr/bin:/bin"},
    )
    assert result.returncode == 0, result.stderr
    assert "PLACEHOLDER" not in result.stdout
    docs: list[dict] = []
    for doc in yaml.safe_load_all(result.stdout):
        if doc:
            docs.extend(doc["items"] if doc.get("kind") == "List" else [doc])
    return docs


def keycloak_docs() -> list[dict]:
    text = (KEYCLOAK_DIR / "keycloak.yaml").read_text().replace("PROJECT_PLACEHOLDER", PROJECT)
    assert "PLACEHOLDER" not in text
    return yaml.safe_load(text)["items"]


def one(docs: list[dict], kind: str, name: str) -> dict:
    return next(d for d in docs if d["kind"] == kind and d["metadata"]["name"] == name)


def args_of(container: dict) -> dict[str, str]:
    return dict(a[2:].split("=", 1) for a in container["args"] if a.startswith("--") and "=" in a)


@pytest.fixture(params=["", "kc"], ids=["staging", "second"])
def instance(request) -> str:
    return request.param


@pytest.fixture
def name(instance: str) -> str:
    return "wizard-v2" if not instance else f"wizard-v2-{instance}"


def test_the_signin_route_keeps_the_stacks_route_and_leads_to_its_proxy(
    instance: str, name: str
) -> None:
    plain = one(render("route.yaml", instance), "Route", f"{name}-web")
    signin = one(render("route-signin.yaml", instance), "Route", f"{name}-web")
    # Same Route object (name, host, annotations), so applying it switches the
    # stack's address over instead of creating a second one.
    assert signin["metadata"] == plain["metadata"]
    assert signin["spec"]["tls"] == plain["spec"]["tls"]
    assert signin["spec"]["to"]["name"] == f"{name}-signin"
    proxy = render("signin-proxy.yaml", instance)
    service = one(proxy, "Service", f"{name}-signin")
    assert signin["spec"]["port"]["targetPort"] == service["spec"]["ports"][0]["targetPort"]


def test_the_proxy_forwards_to_this_stacks_web_app_only(instance: str, name: str) -> None:
    deployment = one(render("signin-proxy.yaml", instance), "Deployment", f"{name}-signin")
    args = args_of(deployment["spec"]["template"]["spec"]["containers"][0])
    assert args["upstream"] == f"http://{name}-web:3000"
    assert args["cookie-name"] == f"_{name}_signin"


def test_the_proxy_admits_only_approved_users_and_forwards_their_token(
    instance: str, name: str
) -> None:
    container = one(render("signin-proxy.yaml", instance), "Deployment", f"{name}-signin")["spec"][
        "template"
    ]["spec"]["containers"][0]
    args = args_of(container)
    assert args["allowed-group"] == "wizard-user"
    assert args["pass-access-token"] == "true"
    assert args["cookie-secure"] == "true"
    assert args["code-challenge-method"] == "S256"
    # The access token lives 15 minutes (realm-gaik.json); the proxy renews it
    # before the web app would see an expired one.
    assert args["cookie-refresh"].endswith("m") and int(args["cookie-refresh"][:-1]) < 15
    secrets = {e["name"]: e["valueFrom"]["secretKeyRef"]["name"] for e in container["env"]}
    assert set(secrets.values()) == {f"{name}-signin"}


def test_the_proxy_waits_as_long_as_the_route_for_a_streamed_reply(
    instance: str, name: str
) -> None:
    route = one(render("route-signin.yaml", instance), "Route", f"{name}-web")
    container = one(render("signin-proxy.yaml", instance), "Deployment", f"{name}-signin")["spec"][
        "template"
    ]["spec"]["containers"][0]
    assert (
        args_of(container)["upstream-timeout"]
        == route["metadata"]["annotations"]["haproxy.router.openshift.io/timeout"]
    )


def test_the_proxy_and_the_web_app_name_the_keycloak_that_issues_the_tokens(
    instance: str, name: str
) -> None:
    keycloak = one(keycloak_docs(), "Deployment", "gaik-keycloak")["spec"]["template"]["spec"][
        "containers"
    ][0]
    kc_host = next(e["value"] for e in keycloak["env"] if e["name"] == "KC_HOSTNAME")
    issuer = f"{kc_host}/realms/gaik"
    container = one(render("signin-proxy.yaml", instance), "Deployment", f"{name}-signin")["spec"][
        "template"
    ]["spec"]["containers"][0]
    assert args_of(container)["oidc-issuer-url"] == issuer
    # deploy.sh sets the web app's issuer from the same host.
    script = OPENSHIFT_DEPLOY.read_text()
    assert 'KEYCLOAK_HOST="gaik-keycloak-${PROJECT}.2.rahtiapp.fi"' in script
    assert kc_host == f"https://gaik-keycloak-{PROJECT}.2.rahtiapp.fi"
    assert '"WIZARD_OIDC_CLIENT_ID=$NAME"' in script


def test_images_are_pinned() -> None:
    images = [
        c["image"]
        for d in keycloak_docs() + render("signin-proxy.yaml", "kc")
        if d["kind"] == "Deployment"
        for c in d["spec"]["template"]["spec"]["containers"]
    ]
    for image in images:
        assert re.search(r":[\w.-]+$", image) and not image.endswith(":latest"), image


def test_keycloak_publishes_only_its_http_port() -> None:
    route = one(keycloak_docs(), "Route", "gaik-keycloak")
    assert route["spec"]["port"]["targetPort"] == "http"
    assert route["spec"]["tls"]["insecureEdgeTerminationPolicy"] == "Redirect"


def test_the_realm_lets_nobody_in_before_an_admin_approves() -> None:
    realm = json.loads((KEYCLOAK_DIR / "realm-gaik.json").read_text())
    assert realm["registrationAllowed"] is False
    assert realm["defaultGroups"] == ["/pending"]
    assert {g["name"] for g in realm["groups"]} >= {"pending", "wizard-user", "admin"}
    assert realm["bruteForceProtected"] is True
    assert realm["accessTokenLifespan"] == 15 * 60
    # A realm file that lists client scopes replaces Keycloak's default ones
    # (profile, email ...); the groups scope is added by deploy.sh setup.
    assert "clientScopes" not in realm and "defaultDefaultClientScopes" not in realm


def test_the_keycloak_script_prints_no_secret() -> None:
    script = (KEYCLOAK_DIR / "deploy.sh").read_text()
    # Secrets reach the pod on stdin or from its own environment, never as an
    # echoed value. The one exception is add-users writing temporary passwords
    # to its owner-only file ("$out", made under umask 077), not the terminal.
    assert '( umask 077; : > "$out" )' in script
    for line in script.splitlines():
        if re.search(r"\becho\b", line) and re.search(
            r"\$\{?(secret|pw|GOOGLE_CLIENT_SECRET)\b", line
        ):
            assert line.rstrip().endswith('>> "$out"'), line


def test_keycloak_mounts_every_file_of_the_gaik_theme() -> None:
    keycloak = one(keycloak_docs(), "Deployment", "gaik-keycloak")["spec"]["template"]["spec"]
    items = next(v for v in keycloak["volumes"] if v["name"] == "theme")["configMap"]["items"]
    theme_dir = KEYCLOAK_DIR / "theme" / "gaik"
    files = {str(p.relative_to(theme_dir)) for p in theme_dir.rglob("*") if p.is_file()}
    assert {i["path"] for i in items} == files
    # deploy.sh theme makes a key for each item.
    script = (KEYCLOAK_DIR / "deploy.sh").read_text()
    for item in items:
        assert f"--from-file={item['key']}=" in script
    realm = json.loads((KEYCLOAK_DIR / "realm-gaik.json").read_text())
    assert realm["loginTheme"] == "gaik"
    assert "parent=keycloak.v2" in (theme_dir / "login" / "theme.properties").read_text()


def test_the_proxy_shows_the_gaik_page_from_this_stacks_templates(instance: str, name: str) -> None:
    deployment = one(render("signin-proxy.yaml", instance), "Deployment", f"{name}-signin")
    spec = deployment["spec"]["template"]["spec"]
    container = spec["containers"][0]
    assert args_of(container)["custom-templates-dir"] == "/templates"
    volume = next(v for v in spec["volumes"] if v["name"] == "templates")
    assert volume["configMap"]["name"] == f"{name}-signin-templates"
    assert any(m["mountPath"] == "/templates" for m in container["volumeMounts"])


def test_the_waiting_page_signs_out_at_keycloak() -> None:
    page = (DEPLOY_DIR / "openshift" / "signin-templates" / "error.html").read_text()
    # A user the proxy turned away has no proxy session; only Keycloak's own
    # logout lets them try another account. deploy.sh fills the address in.
    assert 'href="SIGN_OUT_URL_PLACEHOLDER"' in page
    assert "{{ if and (eq .StatusCode 403)" in page
    script = OPENSHIFT_DEPLOY.read_text()
    assert "SIGN_OUT_URL_PLACEHOLDER" in script and "$SIGNIN_DEPLOYMENT-templates" in script
    # The page loads nothing from elsewhere.
    assert not re.search(r"""(src|href)=["']https?://""", page)
    assert "@import" not in page and "<script" not in page


def test_the_nightly_clean_up_runs_as_the_maintenance_client() -> None:
    cron = yaml.safe_load((KEYCLOAK_DIR / "keycloak-maintenance.yaml").read_text())
    assert cron["kind"] == "CronJob" and cron["spec"]["concurrencyPolicy"] == "Forbid"
    pod = cron["spec"]["jobTemplate"]["spec"]["template"]["spec"]
    container = pod["containers"][0]
    assert container["command"][-2:] == ["/scripts/prune-pending.sh", "7"]
    env = {e["name"]: e for e in container["env"]}
    assert env["KC_CLIENT_ID"]["value"] == "gaik-maintenance"
    # kcadm reads the secret from KC_CLI_CLIENT_SECRET; it is never an argument.
    assert (
        env["KC_CLI_CLIENT_SECRET"]["valueFrom"]["secretKeyRef"]["name"]
        == "gaik-keycloak-maintenance"
    )
    assert container["securityContext"]["readOnlyRootFilesystem"] is True
    keycloak_image = one(keycloak_docs(), "Deployment", "gaik-keycloak")["spec"]["template"][
        "spec"
    ]["containers"][0]["image"]
    assert container["image"] == keycloak_image


def test_the_clean_up_deletes_only_pending_people_never_a_service_account() -> None:
    script = (KEYCLOAK_DIR / "prune-pending.sh").read_text()
    assert "service-account-*) continue" in script
    assert "--secret" not in script and "--password" not in script
    # Logs ids and counts, not addresses.
    assert "email" not in script
    # The Keycloak image has no awk.
    code = [line for line in script.splitlines() if not line.lstrip().startswith("#")]
    assert not any(re.search(r"\bawk\b", line) for line in code)


def test_approvers_get_user_management_in_this_realm_only() -> None:
    script = (KEYCLOAK_DIR / "deploy.sh").read_text()
    grant = script.split("--gname admin --cclientid realm-management", 1)[1].split("\n\n", 1)[0]
    roles = set(re.findall(r"--rolename ([\w-]+)", grant))
    assert roles == {"view-users", "manage-users", "query-users", "query-groups"}
    assert "manage-realm" not in script and "realm-admin" not in script
    assert "adminEventsEnabled=true" in script and "adminEventsDetailsEnabled=false" in script
    # Admin passwords reach kcadm through KC_CLI_PASSWORD, not its arguments.
    assert '--password "$KC_BOOTSTRAP_ADMIN_PASSWORD"' not in script


# --- The AIOps stack (gaik-aiops, its own Rahti project) signs in at the same Keycloak ---

AIOPS_RAHTI = (
    DEPLOY_DIR.parents[1] / "gaik-aiops" / "deploy" / "k8s" / "stack" / "overlays" / "rahti"
)
KEYCLOAK_PUBLIC = "https://gaik-keycloak-gaik.2.rahtiapp.fi"


def aiops_docs(name: str) -> list[dict]:
    return [d for d in yaml.safe_load_all((AIOPS_RAHTI / name).read_text()) if d]


def test_mlflows_route_leads_to_the_sign_in_and_only_the_sign_in_is_open_to_the_router() -> None:
    route = one(aiops_docs("routes.yaml"), "Route", "mlflow")
    assert route["spec"]["to"]["name"] == "mlflow-signin"
    assert route["spec"]["port"]["targetPort"] == 4180
    policies = aiops_docs("networkpolicy-router.yaml")
    selected = {p["spec"]["podSelector"]["matchLabels"]["app.kubernetes.io/name"] for p in policies}
    assert selected == {"grafana", "mlflow-signin"}
    kustomization = (AIOPS_RAHTI / "kustomization.yaml").read_text()
    assert (
        "- mlflow-signin.yaml" in kustomization
        and "- path: patch-grafana-oidc.yaml" in kustomization
    )


def test_mlflows_sign_in_admits_the_aiops_groups_at_the_gaik_keycloak() -> None:
    deployment = one(aiops_docs("mlflow-signin.yaml"), "Deployment", "mlflow-signin")
    container = deployment["spec"]["template"]["spec"]["containers"][0]
    args = container["args"]
    assert f"--oidc-issuer-url={KEYCLOAK_PUBLIC}/realms/gaik" in args
    assert "--upstream=http://mlflow-auth:8080" in args
    assert sorted(a for a in args if a.startswith("--allowed-group=")) == [
        "--allowed-group=aiops-admin",
        "--allowed-group=aiops-viewer",
    ]
    assert {e["valueFrom"]["secretKeyRef"]["name"] for e in container["env"]} == {
        "aiops-mlflow-signin"
    }
    keycloak = one(keycloak_docs(), "Deployment", "gaik-keycloak")["spec"]["template"]["spec"][
        "containers"
    ][0]
    kc_host = next(e["value"] for e in keycloak["env"] if e["name"] == "KC_HOSTNAME")
    assert kc_host.replace(PROJECT, "gaik") == KEYCLOAK_PUBLIC


def test_mlflow_still_cannot_delete_and_gets_none_of_the_sign_ins_headers() -> None:
    conf = (AIOPS_RAHTI / "mlflow-auth-nginx.conf").read_text()
    assert "auth_basic" not in conf
    assert "/delete[^/]*$" in conf and "$request_method = DELETE" in conf
    for header in (
        "Authorization",
        "X-Forwarded-Access-Token",
        "X-Forwarded-Email",
        "X-Forwarded-Groups",
        "Cookie",
    ):
        assert f'proxy_set_header {header} "";' in conf
    assert "htpasswd" not in (AIOPS_RAHTI / "mlflow-auth.yaml").read_text()


def test_grafana_maps_the_aiops_groups_and_refuses_everyone_else() -> None:
    patch = aiops_docs("patch-grafana-oidc.yaml")[0]
    env = {e["name"]: e for e in patch["spec"]["template"]["spec"]["containers"][0]["env"]}
    assert env["GF_AUTH_GENERIC_OAUTH_ROLE_ATTRIBUTE_STRICT"]["value"] == "true"
    # Viewer for both groups only; the mapping raises aiops-admin in Main Org. alone.
    assert env["GF_AUTH_GENERIC_OAUTH_ROLE_ATTRIBUTE_PATH"]["value"].endswith("&& 'Viewer'")
    assert env["GF_AUTH_GENERIC_OAUTH_ORG_MAPPING"]["value"] == (
        "aiops-admin:1:Admin,aiops-admin:Security:Viewer,aiops-viewer:1:Viewer"
    )
    assert env["GF_AUTH_GENERIC_OAUTH_ALLOW_ASSIGN_GRAFANA_ADMIN"]["value"] == "false"
    for key in ("CLIENT_ID", "CLIENT_SECRET"):
        ref = env[f"GF_AUTH_GENERIC_OAUTH_{key}"]["valueFrom"]["secretKeyRef"]
        assert ref["name"] == "aiops-grafana-signin"
    for key in ("AUTH_URL", "TOKEN_URL", "API_URL"):
        assert env[f"GF_AUTH_GENERIC_OAUTH_{key}"]["value"].startswith(
            f"{KEYCLOAK_PUBLIC}/realms/gaik/"
        )
    realm = json.loads((KEYCLOAK_DIR / "realm-gaik.json").read_text())
    assert {"aiops-admin", "aiops-viewer"} <= {g["name"] for g in realm["groups"]}


def test_grafanas_sign_in_page_offers_only_sign_in_with_gaik() -> None:
    patch = aiops_docs("patch-grafana-oidc.yaml")[0]
    env = {e["name"]: e for e in patch["spec"]["template"]["spec"]["containers"][0]["env"]}
    assert env["GF_AUTH_DISABLE_LOGIN_FORM"]["value"] == "true"
    # The local admin then has no sign-in page; the README says how to get in without Keycloak.
    readme = (AIOPS_RAHTI / "README.md").read_text()
    assert "GF_AUTH_DISABLE_LOGIN_FORM=false" in readme


def test_cpu_limits_stay_within_rahtis_ratio() -> None:
    # Rahti's LimitRange refuses a container whose CPU limit is more than 8 times its request (the
    # Keycloak database's pod was refused at 10). The AIOps project asks for 5 at most.
    def millicores(value: str) -> float:
        return float(value[:-1]) if value.endswith("m") else float(value) * 1000

    containers = [
        c
        for d in keycloak_docs()
        + render("signin-proxy.yaml", "kc")
        + aiops_docs("mlflow-signin.yaml")
        if d["kind"] == "Deployment"
        for c in d["spec"]["template"]["spec"]["containers"]
    ]
    cron = yaml.safe_load((KEYCLOAK_DIR / "keycloak-maintenance.yaml").read_text())
    containers += cron["spec"]["jobTemplate"]["spec"]["template"]["spec"]["containers"]
    for c in containers:
        r = c["resources"]
        assert (
            millicores(r["limits"]["cpu"]) <= 5 * millicores(r["requests"]["cpu"])
            or c["name"] == "keycloak"
        ), c["name"]
        assert millicores(r["limits"]["cpu"]) <= 8 * millicores(r["requests"]["cpu"]), c["name"]


def test_a_theme_change_reaches_browsers_within_the_hour() -> None:
    keycloak = one(keycloak_docs(), "Deployment", "gaik-keycloak")["spec"]["template"]["spec"][
        "containers"
    ][0]
    env = {e["name"]: e.get("value") for e in keycloak["env"]}
    assert env["KC_SPI_THEME__STATIC_MAX_AGE"] == "3600"


def test_the_proxies_fix_their_callback_and_trust_forwarded_headers_from_the_cluster_only(
    instance: str, name: str
) -> None:
    wizard = one(render("signin-proxy.yaml", instance), "Deployment", f"{name}-signin")
    mlflow = one(aiops_docs("mlflow-signin.yaml"), "Deployment", "mlflow-signin")
    expected = {
        id(wizard): f"https://{name}-web-{PROJECT}.2.rahtiapp.fi/oauth2/callback",
        id(mlflow): "https://mlflow-gaik-aiops.2.rahtiapp.fi/oauth2/callback",
    }
    for deployment in (wizard, mlflow):
        args = args_of(deployment["spec"]["template"]["spec"]["containers"][0])
        assert args["redirect-url"] == expected[id(deployment)]
        assert args["trusted-proxy-ip"] == "10.128.0.0/14"
    route = one(render("route-signin.yaml", instance), "Route", f"{name}-web")
    assert "host" not in route["spec"]  # the host Rahti assigns is the one the callback names


def test_mlflows_waiting_page_is_the_wizards_with_mlflows_sign_out() -> None:
    shared = (DEPLOY_DIR / "openshift" / "signin-templates" / "error.html").read_text()
    sign_out = (
        f"{KEYCLOAK_PUBLIC}/realms/gaik/protocol/openid-connect/logout?client_id=aiops-mlflow"
        "&amp;post_logout_redirect_uri=https%3A%2F%2Fmlflow-gaik-aiops.2.rahtiapp.fi%2F"
    )
    assert (AIOPS_RAHTI / "mlflow-signin-error.html").read_text() == shared.replace(
        "SIGN_OUT_URL_PLACEHOLDER", sign_out
    )
    container = one(aiops_docs("mlflow-signin.yaml"), "Deployment", "mlflow-signin")["spec"][
        "template"
    ]["spec"]["containers"][0]
    assert "--custom-templates-dir=/templates" in container["args"]
    assert "mlflow-signin-templates" in (AIOPS_RAHTI / "kustomization.yaml").read_text()


def test_a_sign_in_stacks_web_app_is_applied_with_its_sign_in_settings() -> None:
    script = OPENSHIFT_DEPLOY.read_text()
    # One rollout, never in dev-login mode behind the proxy, without the dev account list.
    assert 'oc set env --local -f - "${env[@]}" -o yaml' in script
    assert "WIZARD_DEV_USERS-" in script
    code = [line for line in script.splitlines() if not line.lstrip().startswith("#")]
    assert not any(
        re.search(r"^\s*mapfile\b|[;&|]\s*mapfile\b|\bmapfile -t", line) for line in code
    )


def test_keycloak_asks_everyone_for_a_second_factor_and_records_sign_ins() -> None:
    script = (KEYCLOAK_DIR / "deploy.sh").read_text()
    assert (
        "authentication/required-actions/CONFIGURE_TOTP" in script
        and "defaultAction=true" in script
    )
    assert '"requiredActions=[\\"UPDATE_PASSWORD\\",\\"CONFIGURE_TOTP\\"]"' in script or (
        '\'requiredActions=["UPDATE_PASSWORD","CONFIGURE_TOTP"]\'' in script
    )
    assert "require_totp_for_existing" in script
    # A Google sign-in skips the browser flow; the post-broker flow asks for the second factor.
    assert 'postBrokerLoginFlowAlias="gaik post broker otp"' in script and "auth-otp-form" in script
    assert "eventsEnabled=true" in script and "eventsExpiration=2592000" in script
    assert "realms/master -s bruteForceProtected=true" in script


def test_the_keycloak_script_signs_in_once_and_keeps_the_scripts_stdin() -> None:
    script = (KEYCLOAK_DIR / "deploy.sh").read_text()
    assert script.count("KC_CLI_PASSWORD=") == 1
    # kcadm reads a password from stdin when it has one; the sign-in must not eat
    # the secret or JSON meant for the script after it.
    signin = script.split("KC_SIGNIN='", 1)[1].split("'\n", 1)[0]
    assert "</dev/null" in signin
    # The Google client id is an argument, not spliced into the pod's script.
    assert "'\"$GOOGLE_CLIENT_ID\"'" not in script


def test_a_changed_stylesheet_gets_a_new_address() -> None:
    # Keycloak's theme file addresses do not change with their content, and a browser that fetched
    # the old stylesheet kept it (the sign-in card stayed squeezed after the fix). deploy.sh theme puts a
    # digest of the stylesheet in its address.
    script = (KEYCLOAK_DIR / "deploy.sh").read_text()
    theme_fn = script.split("theme() {", 1)[1].split("\n}\n", 1)[0]
    assert 'shasum -a 256 "$t/resources/css/gaik.css"' in theme_fn
    assert "s#css/gaik.css#css/gaik.css?v=$version#" in theme_fn
    assert '--from-file=theme.properties="$props"' in theme_fn
    props = (KEYCLOAK_DIR / "theme" / "gaik" / "login" / "theme.properties").read_text()
    assert "css/gaik.css" in props


def test_the_waiting_page_is_shown_only_for_an_account_outside_the_group() -> None:
    page = (DEPLOY_DIR / "openshift" / "signin-templates" / "error.html").read_text()
    # oauth2-proxy's 403 for an account outside --allowed-group carries its default message; a sign-in
    # that lost its CSRF cookie is a 403 too, and must not read as "awaiting approval".
    refused = (
        '(eq .StatusCode 403) (eq .Message "You do not have permission to access this resource.")'
    )
    assert page.count(refused) == 2  # title and body
    assert "{{ else if eq .StatusCode 403 }}" in page
    assert (
        "oc rollout restart"
        in OPENSHIFT_DEPLOY.read_text().split("deploy_signin() {", 1)[1].split("\n}\n", 1)[0]
    )
