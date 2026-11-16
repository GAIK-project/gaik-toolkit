# The stack on Kubernetes / OpenShift

Kustomize manifests for the collection and observability stack: Postgres, the collection sink, MLflow,
the OpenTelemetry Collector (with an init container that creates one MLflow experiment per
application), Prometheus, Alertmanager and Grafana. The collector, Prometheus, Grafana and SQL
configuration is read from `deploy/compose` and `shared/collection`, so compose and Kubernetes run the
same configuration.

| Path | What |
|---|---|
| `base/` | Workloads, Services, PVCs and NetworkPolicies, environment-neutral (no namespace, no secrets) |
| `overlays/local/` | Local k3s: namespace, locally built images, local-only secrets, an OpenShift-like UID |
| `overlays/rahti/` | Rahti: its own project, images built on Rahti, Routes for Grafana and MLflow (behind basic auth), secrets created on Rahti ([README](overlays/rahti/README.md)) |
| `test.sh` | Deploys to k3s, checks the network policies, runs the stack tests through port-forwards |

## Run locally (k3s)

The local k3s profile is described in `deploy/k8s/README.md`. Stop the compose stack first, because the
port-forwards use the same local ports, then:

```bash
deploy/k8s/stack/test.sh
```

It builds the sink and MLflow images inside the k3s VM, applies `overlays/local`, waits for every
workload, probes the network policies from an allowed and a disallowed namespace, and runs the stack
tests. `--keep` leaves the stack running.

Render without applying:

```bash
kubectl kustomize --load-restrictor LoadRestrictionsNone deploy/k8s/stack/overlays/local
```

The load restrictor is needed because the configuration files live outside the kustomization root.
Always pass `--context` explicitly; never apply with whatever context happens to be current.

## Built for OpenShift

- **Arbitrary UID:** every container runs under any UID in group 0. The local overlay sets UID
  1000680000 and group 0, as OpenShift's restricted SCC does. Postgres uses the Software Collections
  image, which is made for this; the MLflow image prepares its writable directories for group 0.
- **Locked-down containers:** `runAsNonRoot`, no privilege escalation, all capabilities dropped,
  `RuntimeDefault` seccomp, and requests and limits on every container.
- **Network policies:** ingress is denied unless allowed. Pods in the namespace talk to each other.
  Other namespaces reach only the collector's OTLP ports (4317, 4318), and only when labelled
  `gaik-aiops/producer=true`.
- **No public endpoints in the base:** MLflow has no sign-in of its own and gets no Route there.
  Routes, TLS and the sign-in in front of MLflow belong in the environment overlay (`overlays/rahti`).

## Not yet covered

- The collector's OTLP Route for producers in other projects (M2; designed in `overlays/rahti/README.md`)
- OpenBao on Kubernetes; the pseudonymisation key comes from a Secret here
- A purge CronJob for `collection.purge_expired()`
- MLflow runs two workers within a 2 GiB limit; size it against real use before the hackathon
