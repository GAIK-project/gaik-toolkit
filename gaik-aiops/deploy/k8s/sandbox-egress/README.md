# Sandbox egress baseline

NetworkPolicies for workloads that run generated code, with a test
against a local k3s cluster.

| File | What |
|---|---|
| `00-namespaces.yaml` | `gaik-app` and `gaik-sandbox`, both at Pod Security "restricted" |
| `10-app-fixture.yaml` | Stand-ins for the API and a database |
| `20-sandbox-policies.yaml` | Sandbox: default deny; allow DNS, the API on 8080, TCP 443 to public addresses |
| `30-app-policies.yaml` | App: default deny ingress; API from the sandbox namespace, database from the API only |
| `40-probe.yaml` | Probe pod with the sandbox job security context |
| `test.sh` | Applies everything and checks allowed and denied connections |

```bash
deploy/k8s/sandbox-egress/test.sh
```

Expected result (all `ok`): API allowed; database, Kubernetes API server, cloud metadata address, public
HTTP and other namespaces denied; public HTTPS allowed. Removing the policies makes the denied cases
succeed, so the test depends on the policies and not on the fixture.

Limits:

- NetworkPolicy works on addresses, not names: any public host on 443 is reachable. Limiting to model
  provider domains needs an egress firewall on the platform or an egress proxy.
- The excluded ranges assume the cluster, service and node networks are private (RFC 1918 / 6598). Check
  this on the target platform.
- The API selector and port are fixture values; in a real deployment they come from the solution's chart.
