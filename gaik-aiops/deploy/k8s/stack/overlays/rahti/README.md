# The stack on Rahti

The collection and observability stack in its own Rahti project, `gaik-aiops`, apart from the `gaik`
project that runs the wizard and the demo apps. Both projects belong to the same CSC project and share
its quota.

| File | What |
|---|---|
| `kustomization.yaml` | The base, plus Rahti's images, Routes and sign-in |
| `buildconfigs.yaml` | Builds the MLflow and sink images on Rahti from this repository |
| `mlflow-auth.yaml`, `mlflow-auth-nginx.conf` | Basic auth in front of MLflow, which has no sign-in of its own |
| `routes.yaml` | `https://grafana-gaik-aiops.2.rahtiapp.fi` and `https://mlflow-gaik-aiops.2.rahtiapp.fi` |
| `networkpolicy-router.yaml` | Lets the OpenShift router reach Grafana and the MLflow sign-in, nothing else |
| `create-secrets.sh` | Generates the Secrets on Rahti, once; nothing goes to git |
| `send-test-event.sh` | Sends one test event and prints its trace id |

## Deploy

Log in first: in the Rahti console, your name, *Copy login command*, *Display Token*, and run the
`oc login` line in a terminal. Run everything from `gaik-aiops/`.

```bash
oc new-project gaik-aiops --display-name="GAIK AIOps" --description="csc_project: <CSC project number>"   # once
oc project gaik-aiops
deploy/k8s/stack/overlays/rahti/create-secrets.sh                                                          # once
oc kustomize --load-restrictor LoadRestrictionsNone deploy/k8s/stack/overlays/rahti | oc apply -f -
oc start-build aiops-mlflow --follow
oc start-build aiops-sink --follow
oc get pods -w        # until every pod is Running and ready
```

`oc apply -k` cannot be used: it has no load restrictor option, and the configuration lives in
`deploy/compose`. Apply the rendered output as above. To preview a change, add `--dry-run=server` to
`oc apply`.

After a new build, restart what uses the image: `oc rollout restart deployment/mlflow deployment/otel-collector deployment/grafana-setup`
for MLflow, `oc rollout restart deployment/sink` for the sink. The builds take the `develop` branch
(`spec.source.git.ref`); `--from-dir=<folder>` builds from your working tree instead.

## Signing in

- **Grafana:** user `admin`, password from `oc extract secret/aiops-grafana --keys=admin-password --to=-`.
  Give reviewers their own users (Administration, Users and access, Users, New user) with the Viewer
  role, and add them to the *Security* organisation too, which holds the audit trail.
- **MLflow:** one shared reviewer sign-in, from `oc extract secret/aiops-mlflow-auth --keys=username,password --to=-`.
  To add a user, add a line made with `htpasswd -nB <user>` to the Secret's `htpasswd` key and restart
  `deployment/mlflow-auth`. OIDC (WP4) replaces this.

Hand passwords to reviewers outside git and outside public channels.

## Test event

```bash
oc port-forward svc/otel-collector 4318:4318          # second terminal; needs access to the project
deploy/k8s/stack/overlays/rahti/send-test-event.sh
```

The script prints a trace id. It sends a trace (a run span and one LLM-call span) and an audit log
record on the same trace, all with a user id, a client IP and prompt and response text.

- **MLflow:** *Experiments*, *Default*, *Traces*: the trace with that id. On the spans,
  `enduser.pseudo.id` is a 64-character hash and `enduser.id` is gone, `client.address` is
  `192.0.2.0`, and the LLM-call span has no `gen_ai.input.messages` or `gen_ai.output.messages`.
- **Grafana:** switch to the *Security* organisation, *Audit trail* dashboard, *Latest events*: the
  row with the same `trace_id`, its actor a hash and its client address `192.0.2.0`.

## The wizard's way in (M2, not deployed)

The staging wizard runs in `gaik`, so its events must cross projects. The design:

- A Route `otlp` with edge TLS to the collector's OTLP/HTTP port, and a router NetworkPolicy for that
  port, the same as `networkpolicy-router.yaml`.
- A second OTLP receiver on its own port with the collector's `bearertokenauth` extension, so only
  callers with the token get in; the in-project receiver stays as it is. It goes in as a third
  `--config` file in this overlay, which the collector merges with the shared configuration. Pipelines'
  receiver lists are replaced, not merged, so that file repeats them.
- The token in a Secret here (`create-secrets.sh`) and in the wizard's Secret in `gaik`, set with
  `oc create secret` by hand. `send-test-event.sh` already sends `OTLP_TOKEN` when set.

The base's `allow-otlp-from-producers` policy (namespace label `gaik-aiops/producer=true`) needs a
label on `gaik` that this project cannot set, so the Route is the way in.

## Changing Secrets

`create-secrets.sh` never replaces a Secret. The database passwords are set when Postgres first
starts, so changing `aiops-db` afterwards also needs `ALTER ROLE` in Postgres. A new pseudonym key
gives every user a new pseudonym and cuts the link to earlier events; change it only on purpose.
`aiops-grafana` sets the admin password only on Grafana's first start; afterwards change it in
Grafana. `aiops-mlflow-auth` can change at any time, followed by a restart of `deployment/mlflow-auth`.

## Quota

The project shares CSC project quota with `gaik`. The stack takes four volumes (26Gi: Postgres 10,
Prometheus 10, MLflow 5, Grafana 1), two image streams, and about 6 CPU and 6Gi of memory in limits.
Check with `oc describe appliedclusterresourcequota`.

## Not yet covered

- Grafana and the Python base image of the two builds still come from Docker Hub, which limits
  anonymous pulls.
- The Route addresses are written into `patch-grafana-public-url.yaml` and
  `patch-mlflow-public-host.yaml`; a project with another name needs both changed.
- Alertmanager has no receiver on Rahti yet, so alerts show in Grafana only (M2).
