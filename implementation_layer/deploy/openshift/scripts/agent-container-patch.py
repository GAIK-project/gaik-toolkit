#!/usr/bin/env python3
"""Print a strategic-merge patch that gives a running api Deployment its agent container.

    INSTANCE=s4 PROJECT=<project> python3 agent-container-patch.py > patch.json
    oc patch deployment/wizard-v2-s4-api -n <project> --type=strategic --patch-file patch.json

The live Deployments carry variables set with `oc set env` that the manifest
lacks, so the manifest is never applied to them (README, "Deploy"). A strategic
merge patch adds what deployment-api.yaml now has for the agent (the agent
container, the socket and token volumes, the api's socket variable and mounts,
the token not mounted by default) and merges containers, variables, mounts and
volumes by name: everything else on the live Deployment stays as it is.
"""

import json
import os
import sys
from pathlib import Path

import yaml

MANIFEST = Path(__file__).resolve().parents[1] / "deployment-api.yaml"

name = "wizard-v2" + (f"-{os.environ['INSTANCE']}" if os.environ.get("INSTANCE") else "")
project = os.environ.get("PROJECT", "")
if not project:
    sys.exit("set PROJECT to the OpenShift project")
text = (
    MANIFEST.read_text().replace("NAME_PLACEHOLDER", name).replace("PROJECT_PLACEHOLDER", project)
)
pod = yaml.safe_load(text)["spec"]["template"]["spec"]
api, agent = pod["containers"]

patch = {
    "spec": {
        "template": {
            "spec": {
                "automountServiceAccountToken": False,
                "containers": [
                    {
                        "name": api["name"],
                        "env": [e for e in api["env"] if e["name"] == "WIZARD_AGENT_BRIDGE_SOCKET"],
                        "volumeMounts": [
                            m
                            for m in api["volumeMounts"]
                            if m["name"] in ("agent-socket", "cluster-token")
                        ],
                        "resources": api["resources"],
                    },
                    agent,
                ],
                "volumes": [
                    v for v in pod["volumes"] if v["name"] in ("agent-socket", "cluster-token")
                ],
            }
        }
    }
}
json.dump(patch, sys.stdout, indent=2)
print()
