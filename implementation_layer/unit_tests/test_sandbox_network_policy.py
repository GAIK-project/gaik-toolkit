"""What a sandbox PoC run may reach over the network (networkpolicy-sandbox.yaml).

The run is code an agent generated, so the policy is part of the isolation in
SANDBOX.md. These tests render the policy the way ``deploy.sh manifests``
applies it and the Job the way ``submit-sandbox-job.sh`` renders it, and fail if
the policy stops selecting the runs or allows more than DNS, the stack's own api
and public HTTPS. ``scripts/test-sandbox-egress.sh`` checks the same rules
against a real cluster.
"""

import ipaddress
import subprocess
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

OPENSHIFT_DIR = Path(__file__).resolve().parents[1] / "deploy" / "openshift"
DEPLOY = OPENSHIFT_DIR / "deploy.sh"
SUBMIT = OPENSHIFT_DIR / "scripts" / "submit-sandbox-job.sh"
IMAGE = "registry.example.invalid/wizard-v2-poc-runner:test"

# Ranges a run must not reach on 443: cluster and node networks, the cloud
# metadata address, loopback.
BLOCKED = [
    "10.0.0.0/8",
    "172.16.0.0/12",
    "192.168.0.0/16",
    "100.64.0.0/10",
    "169.254.0.0/16",
    "127.0.0.0/8",
]


@pytest.fixture(scope="module", params=["", "s4"], ids=["staging", "second"])
def instance(request) -> str:
    return request.param


@pytest.fixture(scope="module")
def name(instance: str) -> str:
    return "wizard-v2" if instance == "" else f"wizard-v2-{instance}"


@pytest.fixture(scope="module")
def policy(instance: str) -> dict:
    out = subprocess.run(
        ["bash", str(DEPLOY), "render", "networkpolicy-sandbox.yaml"],
        capture_output=True,
        text=True,
        check=True,
        env={"PROJECT": "proj", "INSTANCE": instance, "PATH": "/usr/bin:/bin"},
    )
    return yaml.safe_load(out.stdout)


@pytest.fixture(scope="module")
def run_labels(instance: str) -> dict:
    out = subprocess.run(
        [str(SUBMIT), "7f3a9c21-0000-4000-8000-abc123456789", IMAGE],
        capture_output=True,
        text=True,
        check=True,
        env={"DRY_RUN": "1", "INSTANCE": instance, "PATH": "/usr/bin:/bin"},
    )
    return yaml.safe_load(out.stdout)["spec"]["template"]["metadata"]["labels"]


def test_the_policy_selects_this_stacks_runs(policy: dict, run_labels: dict, name: str) -> None:
    selector = policy["spec"]["podSelector"]["matchLabels"]
    assert selector.items() <= run_labels.items()
    assert selector["wizard-v2/instance"] == name
    assert policy["metadata"]["name"] == f"{name}-poc-run"


def test_nothing_may_connect_to_a_run(policy: dict) -> None:
    assert "Ingress" in policy["spec"]["policyTypes"]
    assert not policy["spec"].get("ingress")


def test_egress_is_limited_to_dns_the_api_and_public_https(policy: dict, name: str) -> None:
    assert "Egress" in policy["spec"]["policyTypes"]
    rules = policy["spec"]["egress"]
    assert len(rules) == 3
    dns, api, https = rules

    assert {p["port"] for p in dns["ports"]} == {53, 5353}
    for peer in dns["to"]:
        assert "ipBlock" not in peer
        assert peer["namespaceSelector"]["matchLabels"]["kubernetes.io/metadata.name"] in {
            "openshift-dns",
            "kube-system",
        }

    assert api["to"] == [{"podSelector": {"matchLabels": {"app": f"{name}-api"}}}]
    assert api["ports"] == [{"protocol": "TCP", "port": 8100}]

    assert https["ports"] == [{"protocol": "TCP", "port": 443}]
    (peer,) = https["to"]
    assert peer["ipBlock"]["cidr"] == "0.0.0.0/0"
    assert set(peer["ipBlock"]["except"]) >= set(BLOCKED)


def test_every_egress_rule_names_its_ports(policy: dict) -> None:
    """A rule without ports allows every port to its peers."""
    for rule in policy["spec"]["egress"]:
        assert rule.get("ports"), rule


def test_the_metadata_address_is_not_reachable(policy: dict) -> None:
    metadata = ipaddress.ip_address("169.254.169.254")
    for rule in policy["spec"]["egress"]:
        for peer in rule["to"]:
            block = peer.get("ipBlock")
            if not block or metadata not in ipaddress.ip_network(block["cidr"]):
                continue
            assert any(metadata in ipaddress.ip_network(e) for e in block.get("except", []))
