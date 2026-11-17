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
| `patch-rahti-seccomp.yaml` | Drops the base's `RuntimeDefault` seccomp profile, which Rahti refuses since 10 Nov 2026; Rahti applies its own |
| `patch-rahti-cpu-requests.yaml` | Raises CPU requests to Rahti's limit range: at least 50m, limit at most five times the request |
| `patch-grafana-public-url.yaml`, `patch-mlflow-public-host.yaml` | Tell Grafana and MLflow their public addresses |
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
(`spec.source.git.ref`). To build your last local commit instead, upload the repository:
`oc start-build aiops-mlflow --from-repo=.. --follow` (from `gaik-aiops/`; the BuildConfig's
`contextDir` then finds the Dockerfile inside it).

## Signing in

Read passwords in your own terminal: `oc extract` prints them there. Hand them to reviewers outside
git and outside public channels.

- **Grafana:** user `admin`, password from `oc extract secret/aiops-grafana --keys=admin-password --to=-`.
  Give reviewers their own users (Administration, Users and access, Users, New user) with the Viewer
  role in the main organisation, for the monitoring dashboards. Do not add them to the *Security*
  organisation: by design only the admin joins it, because any member can run their own queries on
  the audit store through its datasource. Show the audit trail as admin.
- **MLflow:** one shared sign-in, from `oc extract secret/aiops-mlflow-auth --keys=username,password --to=-`.
  It can change and delete as well as read: MLflow's own pages need write requests, so nginx cannot
  make it read-only. To add a user, add a line made with `htpasswd -nB -C 4 <user>` to the Secret's
  `htpasswd` key and restart `deployment/mlflow-auth`. OIDC (WP4) replaces this.

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
- **Grafana** (as admin): switch to the *Security* organisation, *Audit trail* dashboard, *Latest events*: the
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
`aiops-grafana` sets the admin password only on Grafana's first start, but `grafana-setup` keeps
signing in with it. To change it, change it in Grafana (your profile, *Change password*), then put the
same value in the Secret and run `oc rollout restart deployment/grafana-setup`; otherwise
`grafana-setup` fails and stops maintaining the *Security* organisation. `aiops-mlflow-auth` can
change at any time (password and its hash together), followed by a restart of `deployment/mlflow-auth`.

## Quota

The project shares CSC project quota with `gaik`. The stack takes four volumes (26Gi: Postgres 10,
Prometheus 10, MLflow 5, Grafana 1), two image streams, and about 6 CPU and 6Gi of memory in limits.
Check with `oc describe appliedclusterresourcequota`.

## Not yet covered

- Grafana and the Python base image of the two builds still come from Docker Hub, which limits
  anonymous pulls. The base and the compose stack still run Grafana 11.5.2; only this overlay runs
  the patched release.
- The project name `gaik-aiops` is written into `kustomization.yaml` (the namespace and both image
  paths), the Route addresses in `patch-grafana-public-url.yaml` and `patch-mlflow-public-host.yaml`,
  and the default in `create-secrets.sh` (`NAMESPACE`). A project with another name needs all of them
  changed.
- The shared MLflow sign-in can delete experiments. The collector's routes hold experiment ids from
  its start, so a deleted experiment's traces fail until `deployment/otel-collector` restarts.
- Alertmanager has no receiver on Rahti yet, so alerts show in Grafana only (M2).
