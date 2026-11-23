# The stack on Rahti

The collection and observability stack in its own Rahti project, `gaik-aiops`, apart from the `gaik`
project that runs the wizard and the demo apps. Both projects belong to the same CSC project and share
its quota.

| File | What |
|---|---|
| `kustomization.yaml` | The base, plus Rahti's images, Routes and sign-in |
| `buildconfigs.yaml` | Builds the MLflow and sink images on Rahti from this repository |
| `mlflow-signin.yaml` | Sign-in in front of MLflow (oauth2-proxy, the GAIK Keycloak); MLflow has none of its own |
| `mlflow-auth.yaml`, `mlflow-auth-nginx.conf` | Between the sign-in and MLflow: keeps deleting closed |
| `patch-grafana-oidc.yaml` | Grafana signs in at the GAIK Keycloak; its groups give the organisations and roles |
| `routes.yaml` | `https://grafana-gaik-aiops.2.rahtiapp.fi` and `https://mlflow-gaik-aiops.2.rahtiapp.fi`, the only place the host names are written |
| `patch-rahti-seccomp.yaml` | Drops the base's `RuntimeDefault` seccomp request; Rahti's SCC gives every pod its own profile anyway |
| `patch-rahti-cpu-requests.yaml` | Raises CPU requests to Rahti's limit range: at least 50m, limit at most five times the request |
| `patch-grafana-public-url.yaml`, `patch-mlflow-public-host.yaml` | Tell Grafana and MLflow their public addresses, copied from the Routes' `spec.host` |
| `patch-image-triggers.yaml` | Pins the MLflow and sink Deployments to the digest of the last build and rolls them out after a build |
| `networkpolicy-router.yaml` | Lets the OpenShift router reach Grafana and the MLflow sign-in, nothing else |
| `create-secrets.sh` | Generates the Secrets on Rahti, once; nothing goes to git |
| `send-test-event.sh` | Sends one test event and prints its trace id |
| `otlp-ingress.yaml`, `otlp-ingress-collector.yaml`, `patch-otlp-ingress.yaml` | The token-checked OTLP way in for producers in other projects (M2) |

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

A finished build is a rollout: OpenShift writes the new image's digest into every Deployment that uses
it (`patch-image-triggers.yaml`; MLflow's image also serves `otel-collector`'s init container and
`grafana-setup`) and rolls them out. Between builds, every pod runs the digest it was rolled out with,
also after a reschedule. Start a build only when you mean to roll out what `develop` holds now: the
builds take the `develop` branch (`spec.source.git.ref`). After `oc apply`, the Deployments briefly show
`:latest` until the trigger writes the digest back. To build your last local commit instead, upload the repository:
`oc start-build aiops-mlflow --from-repo=.. --follow` (from `gaik-aiops/`; the BuildConfig's
`contextDir` then finds the Dockerfile inside it).

## Signing in

People sign in with their GAIK account at the Keycloak in the `gaik` project
(`implementation_layer/deploy/keycloak/README.md`); Grafana's sign-in page shows only
*Sign in with GAIK*, not its own username and password form. Two groups there decide what they get:

| Keycloak group | Grafana | MLflow |
|---|---|---|
| `aiops-admin` | Main Org.: Admin, *Security*: Viewer (audit trail) | read and change, not delete |
| `aiops-viewer` | Main Org.: Viewer | read and change, not delete |
| neither | sign-in refused | 403 |

An approver adds people to the groups in the realm console (`/admin/gaik/console/`) or with
`deploy.sh add-users` (`someone@example.org,aiops-viewer`). Only `aiops-admin` joins the *Security*
organisation, because any member can run their own queries on the audit store through its datasource.

Register the two clients once, from the repository root, logged in to both projects:

```bash
SECRET_NAMESPACE=gaik-aiops PROJECT=gaik implementation_layer/deploy/keycloak/deploy.sh \
  add-client aiops-grafana https://grafana-gaik-aiops.2.rahtiapp.fi /login/generic_oauth
SECRET_NAMESPACE=gaik-aiops PROJECT=gaik implementation_layer/deploy/keycloak/deploy.sh \
  add-client aiops-mlflow https://mlflow-gaik-aiops.2.rahtiapp.fi
```

They make the Secrets `aiops-grafana-signin` and `aiops-mlflow-signin` here; apply the overlay after.
On a new stack, restart Grafana once after `grafana-setup` has created the *Security* organisation
(`oc rollout restart deployment/grafana`): Grafana looks the organisation up by name when it starts,
and until then `aiops-admin` gets no *Security* membership.

- **No local Grafana users for people.** Grafana does not link a local user to a GAIK sign-in with the
  same address (insecure email lookup is off); that person's sign-in would fail. Add people in Keycloak.
- **Grafana's local admin** (`admin`, `oc extract secret/aiops-grafana --keys=admin-password --to=-`)
  stays for `grafana-setup`'s API calls with basic auth. The sign-in page shows only *Sign in with
  GAIK*, so the local admin cannot sign in there: when Keycloak is down, use the API with basic auth,
  or switch the form back on with
  `oc set env deploy/grafana -c grafana GF_AUTH_DISABLE_LOGIN_FORM=false` and set it back to `true`
  when done.
- **MLflow** cannot delete through the Route: `mlflow-auth` answers 403 to the `DELETE` method and to
  MLflow's `…/delete` and `…/delete-<what>` endpoints. MLflow's own pages need other write requests, so
  it cannot be made read-only. Delete as a project member instead, through
  `oc port-forward svc/mlflow 5000:5000`.
- The Secret `aiops-mlflow-auth` of the earlier shared sign-in is no longer used; delete it after the
  switch (`oc delete secret aiops-mlflow-auth`).

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

## The wizard's way in (M2)

The wizard runs in `gaik`, so its events cross projects. The base's `allow-otlp-from-producers` policy
(namespace label `gaik-aiops/producer=true`) needs a label on `gaik` that this project cannot set, so
the way in is a Route:

- `otlp-ingress.yaml`: the Route `otlp` (`https://otlp-gaik-aiops.2.rahtiapp.fi`, edge TLS) to the
  collector's port 4320, and a router NetworkPolicy for that port only. Ports 4317 and 4318 stay
  inside the project.
- `otlp-ingress-collector.yaml`: a second OTLP/HTTP receiver on 4320 behind the collector's
  `bearertokenauth` extension, read as a third `--config` file. Each pipeline's receiver list is given
  in full there (lists are replaced, not merged), so data from both receivers goes through the same
  privacy processors. A request without the token gets 401.
- The token is in the Secret `aiops-otlp-ingress` (`create-secrets.sh`).

A producer gets the same token in a Secret of its own project, as `OTEL_EXPORTER_OTLP_HEADERS`
(`Authorization=Bearer%20<token>`), copied without printing it:

```bash
printf 'apiVersion: v1\nkind: Secret\nmetadata:\n  name: <producer>-otlp\ntype: Opaque\nstringData:\n  OTEL_EXPORTER_OTLP_HEADERS: "Authorization=Bearer%%20%s"\n' \
  "$(oc extract secret/aiops-otlp-ingress -n gaik-aiops --keys=token --to=-)" | oc create -n <project> -f -
oc set env deployment/<producer> -n <project> -c <container> --from=secret/<producer>-otlp \
  OTEL_EXPORTER_OTLP_ENDPOINT=https://otlp-gaik-aiops.2.rahtiapp.fi
```

Set it on the wizard's api container only, not on its agent container. The wizard's dashboards read
`service_name="wizard-v2-api"`, the API's default `OTEL_SERVICE_NAME`, so leave that unset. To test the
way in: `OTLP_ENDPOINT=https://otlp-gaik-aiops.2.rahtiapp.fi OTLP_TOKEN=... send-test-event.sh`.

## Changing Secrets

`create-secrets.sh` never replaces a Secret. The database passwords are set when Postgres first
starts, so changing `aiops-db` afterwards also needs `ALTER ROLE` in Postgres. A new pseudonym key
gives every user a new pseudonym and cuts the link to earlier events; change it only on purpose.
`aiops-grafana` sets the admin password only on Grafana's first start, but `grafana-setup` keeps
signing in with it. To change it, switch the sign-in form back on (above), sign in as `admin`, change
it in your profile (*Change password*) and switch the form off again, then put the same value in the
Secret and run `oc rollout restart deployment/grafana-setup`; otherwise
`grafana-setup` fails and stops maintaining the *Security* organisation. The sign-in Secrets
`aiops-grafana-signin` and `aiops-mlflow-signin` follow their Keycloak clients: after regenerating a
client's secret in Keycloak, put it in the Secret and restart the Deployment that reads it.

## Quota

The project shares CSC project quota with `gaik`. The stack takes four volumes (26Gi: Postgres 10,
Prometheus 10, MLflow 5, Grafana 1), two image streams, and about 6 CPU and 6Gi of memory in limits.
Check with `oc describe appliedclusterresourcequota`.

## Not yet covered

- Grafana and the Python base image of the two builds still come from Docker Hub, which limits
  anonymous pulls. The base and the compose stack still run Grafana 11.5.2; only this overlay runs
  the patched release.
- The project name `gaik-aiops` is written into `kustomization.yaml` (the namespace and both image
  paths), the Routes' `spec.host` in `routes.yaml`, the image stream names in
  `patch-image-triggers.yaml`, and the default in `create-secrets.sh` (`NAMESPACE`). A project with
  another name needs all of them changed.
- The collector's routes hold experiment ids from its start, so if a project member deletes an
  experiment, its traces fail until `deployment/otel-collector` restarts. The shared sign-in cannot
  delete.
- Alertmanager has no receiver on Rahti yet, so alerts show in Grafana only (M2).
