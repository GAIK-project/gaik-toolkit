from pathlib import Path

import pytest

from gaik_authz.policy import Policy, PolicyError

POLICY = Policy.load(Path(__file__).resolve().parents[1] / "policy.yaml")


@pytest.mark.parametrize("role,allowed,denied", [
    ("viewer", {"solution.read", "result.read"}, {"solution.write", "job.run", "result.approve", "audit.read"}),
    ("expert", {"solution.read", "solution.write", "data.upload", "job.run"}, {"result.approve", "audit.read", "config.manage"}),
    ("approver", {"solution.read", "result.approve"}, {"solution.write", "job.run", "audit.read"}),
    ("admin", {"solution.read", "audit.read", "config.manage", "role.manage"}, {"solution.write", "result.approve"}),
])
def test_role_table(role, allowed, denied):
    perms = POLICY.permissions_for([role])
    assert allowed <= perms
    assert not (denied & perms)


def test_unknown_and_empty_roles_grant_nothing():
    assert POLICY.permissions_for([]) == frozenset()
    assert POLICY.permissions_for(["offline_access", "superuser"]) == frozenset()


def test_separation_of_duties_expert_cannot_approve():
    assert not POLICY.allows(["expert"], "result.approve")
    assert not POLICY.allows(["approver"], "solution.write")


def test_roles_combine():
    assert POLICY.permissions_for(["expert", "approver"]) >= {"solution.write", "result.approve"}


def test_include_cycle_rejected():
    with pytest.raises(PolicyError, match="cycle"):
        Policy({"a": {"includes": ["b"]}, "b": {"includes": ["a"]}})


def test_unknown_include_rejected():
    with pytest.raises(PolicyError, match="unknown role"):
        Policy({"a": {"includes": ["nope"]}})
