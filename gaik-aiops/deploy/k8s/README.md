# Local Kubernetes

For work that needs Kubernetes objects (NetworkPolicy, Jobs, ServiceAccounts, Roles, mounted secrets),
run k3s in a separate Colima profile so the default Docker profile is not disturbed (needs `kubectl`):

```bash
colima start -p k8s --kubernetes --cpu 4 --memory 6
```

```bash
kubectl config use-context colima-k8s
```

k3s enforces NetworkPolicy out of the box, which is enough to test egress restrictions for sandbox jobs.

`colima start -p k8s` switches the Docker context to `colima-k8s`. Switch back before running the
compose stack, otherwise it starts inside the Kubernetes VM:

```bash
docker context use colima
```

Policies and tests:

- `sandbox-egress/`: egress baseline for code-executing jobs
- `stack/`: the collection and observability stack, with network policies and an arbitrary-UID test run

Not covered locally (needs the target OpenShift environment during the contract period):
Routes and TLS termination, SCC random UIDs (approximate by running containers with an arbitrary UID),
and provider-level egress firewalls.

Stop the profile when not in use:

```bash
colima stop -p k8s
```
