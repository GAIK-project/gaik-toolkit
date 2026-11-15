# GAIK Demo - OpenShift Deployment

Templates for deploying GAIK Demo to CSC Rahti 2 (OpenShift).

## Architecture

```
┌─────────────────────┐      ┌─────────────────────┐
│   gaik-demo         │      │   gaik-demo-api     │
│   (Frontend)        │─────▶│   (Backend API)     │
│   Port: 3000        │      │   Port: 8000        │
│   PUBLIC ROUTE      │      │   INTERNAL ONLY     │
└─────────────────────┘      └─────────────────────┘
        │
        ▼
  gaik-demo.2.rahtiapp.fi
```

## Staging

A copy of the app for trying changes before production: `https://gaik-demo-staging.2.rahtiapp.fi`.
Push any branch to `deploy/demo-staging` to build and roll it out:

```bash
git push origin <branch>:deploy/demo-staging   # add --force-with-lease after a rebase
```

`staging.yaml` holds the image streams, builds, services and route. The two
`-staging` deployments were created once from the production ones (the live env vars are
not committed) with `BACKEND_URL` pointing at `gaik-demo-api-staging`, the ops and
Langfuse reporting off and a smaller API request. Staging shares Supabase (accounts and
approvals), the database and the model keys with production; sign-in works as in
production and the app's own-key path works without an account. The branch is only a
build trigger, so force-pushing it is fine.

## Deploy on push

Push to the `deploy/demo-app` branch to release both services:

```bash
git push origin main:deploy/demo-app
```

A GitHub webhook starts the two BuildConfigs in `buildconfigs.yaml`, which build the API
and frontend images in Rahti and push them to the `gaik-demo-api` and `gaik-demo`
ImageStreams. The deployments carry image triggers, so they roll out when a build
finishes. Follow a release with `oc get builds -n gaik -w`; roll back with
`oc rollout undo deployment/<name> -n gaik`.

One-time setup, already done for namespace `gaik`: create the `gaik-demo-webhook` secret
(a random `WebHookSecretKey`), `oc apply -f buildconfigs.yaml`, set the triggers with
`oc set triggers deployment/<name> --from-image=<name>:latest -c <name>`, and add each
BuildConfig's GitHub webhook URL (`oc describe bc/<name>`) to the repository.

## Quick Deploy (first install only)

The live deployments carry env vars set with `oc set env` that these manifests lack;
re-applying `deployment-*.yaml` to a running environment drops them.

```bash
# 1. Login to Rahti
oc login --token=<token> --server=https://api.2.rahti.csc.fi:6443

# 2. Switch to project
oc project gaik

# 3. Create secrets (copy and edit first!)
cp secrets.yaml.example secrets.yaml
# Edit secrets.yaml with your values
oc apply -f secrets.yaml

# 4. Deploy
oc apply -f services.yaml
oc apply -f deployment-api.yaml
oc apply -f deployment-frontend.yaml
oc apply -f route.yaml
oc apply -f networkpolicy-api.yaml
```

## Network policy and pod hardening

`networkpolicy-api.yaml` states the intended rule: only the frontend pods reach the API
on port 8000 (`gaik-demo` to `gaik-demo-api`, and `gaik-demo-staging` to
`gaik-demo-api-staging`). `proxy.ts` is the only sign-in, approval and trial gate in
front of the API, so no other pod in the project should reach the API directly. The
kubelet's health probes are not affected, and the API has no route of its own. The
selectors match the live pod labels.

**The policy takes effect only when the shared namespace policy is changed.**
NetworkPolicies add up, and the `gaik` project has `deny-other-namespaces-access`,
which selects every pod (`podSelector: {}`) and admits every pod in the namespace
(`from: [{podSelector: {}}]`), next to `allow-from-router` for the router. While that
policy admits every pod, any pod in the project can still reach the API, with or
without this file. Changing the shared policy is the project owner's decision; until
then this file only states the rule.

When that policy is narrowed, it would keep the other pods and leave the API pods out,
for example:

```yaml
spec:
  podSelector:
    matchExpressions:
      - key: app
        operator: NotIn
        values: [gaik-demo-api, gaik-demo-api-staging]
```

Apply the policy file on its own. Never `oc apply` the deployment manifests to a
running environment: the live deployments carry env vars these files lack.

```bash
oc get networkpolicy -n gaik -o yaml        # what is there now
oc apply -f networkpolicy-api.yaml -n gaik

# Check: each frontend still reaches its API ...
oc exec -n gaik deployment/gaik-demo -- \
  bun -e "fetch('http://gaik-demo-api:8000/health').then(r => console.log(r.status))"
oc exec -n gaik deployment/gaik-demo-staging -- \
  bun -e "fetch('http://gaik-demo-api-staging:8000/health').then(r => console.log(r.status))"
# ... and, once the shared policy no longer admits every pod, another pod does not
# (this times out then):
oc run np-check -n gaik --rm -i --restart=Never --image=curlimages/curl:8.11.1 -- \
  curl -s -m 5 -o /dev/null -w '%{http_code}\n' http://gaik-demo-api:8000/health
```

Roll back with `oc delete networkpolicy gaik-demo-api-from-frontend gaik-demo-api-staging-from-frontend -n gaik`.

The deployment manifests state the container hardening: no privilege escalation, all
Linux capabilities dropped and a non-root user. On Rahti the project's SCC already
applies these to every pod, with Rahti's own seccomp profile, so nothing needs to be
patched on the live deployments, and the manifests name no seccomp profile that could
replace Rahti's. The settings are written down for other clusters. Check what a pod
runs with:

```bash
oc get pods -n gaik -o custom-columns=NAME:.metadata.name,SCC:.metadata.annotations.openshift\.io/scc
```

The root filesystem stays writable: the API writes model caches, uploads and generated
files, and Next.js writes its cache under `/app/.next/cache`.

## Build & Push Images

Use `deploy.sh` — **both** the API and frontend build with a `docker-container`
buildx builder and push single-arch Docker schema2 manifests (Rahti's registry
rejects Docker 29's default OCI/manifest-list output). The API image builds from
the **repository root** so it can bundle the Solution Wizard assets
(`implementation_layer/solution_wizard`); gaik itself comes from the published
PyPI wheel pinned in `api/requirements.txt`:

```bash
cd implementation_layer/toolkit_demo_app/openshift
./deploy.sh api       # build + push + rollout API
./deploy.sh frontend  # build + push + rollout frontend
```

## Restore and Verify Video Search

```bash
cd implementation_layer/toolkit_demo_app/openshift

# Reseed dental demo videos into Allas + pgvector
./deploy.sh seed

# Verify route, env, logs, DB state, Allas prefixes, and media probes
./deploy.sh verify
```

Verification uses `api/scripts/verify_video_search_deployment.py` and fails if:

- live `video-search` has zero indexed videos
- Allas is missing any `dental-demo/<video_id>/video.mp4`, `thumbnail.jpg`, or `subtitles.srt`
- sample playback or thumbnail endpoints fail

## Report runs only from the web app

The report run routes keep their per-user quota in the web app. To make the API
accept those runs only from the web app's route handlers, give both deployments the
same token:

```bash
oc create secret generic gaik-demo-report-run -n gaik \
  --from-literal=REPORT_RUN_TOKEN="$(openssl rand -base64 32)"
oc set env deployment/gaik-demo --from=secret/gaik-demo-report-run -n gaik
oc set env deployment/gaik-demo-api --from=secret/gaik-demo-report-run -n gaik
```

Set it on the frontend first, or both in one go: an API with the token refuses runs
from a frontend without it. Until it is set the API logs a warning once and accepts
runs as before.

## Environment Variables

### Frontend (gaik-demo)

| Variable                               | Description          | Source                                 |
| -------------------------------------- | -------------------- | -------------------------------------- |
| `BACKEND_URL`                          | Internal API URL     | Hardcoded: `http://gaik-demo-api:8000` |
| `ADMIN_PASSWORD`                       | Admin dashboard auth | Secret: `gaik-demo-admin`              |
| `ADMIN_SESSION_SECRET`                 | Signs the admin session cookie; without it the key is derived from `ADMIN_PASSWORD` | Secret: `gaik-demo-admin` |
| `ADMIN_SIGN_IN_ATTEMPTS`, `ADMIN_SIGN_IN_ATTEMPTS_TOTAL` | Optional. Admin sign-in attempts per address per 15 minutes (5) and in all per hour (30) | `oc set env` |
| `REPORT_RUN_TOKEN`                     | Optional. Sent by the report route handlers; the API refuses report runs without it once it is set there too | Secret: `gaik-demo-report-run` |
| `NEXT_PUBLIC_SUPABASE_URL`             | Supabase project URL | Secret: `gaik-demo-supabase`           |
| `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` | Supabase anon key    | Secret: `gaik-demo-supabase`           |
| `SUPABASE_SECRET_KEY`                  | Supabase service key | Secret: `gaik-demo-supabase`           |
| `WIZARD_V2_URL`                        | Optional. Wizard V2 address the `/solution-wizard` notice links to, read at run time | `oc set env` |

`WIZARD_ACCESS_SECRET` is no longer read: the frontend answers 404 on `/api/wizard`.
Remove it from both frontend deployments first, then from the secret if it is there
(the patch fails harmlessly when the key is absent):

```bash
for d in gaik-demo gaik-demo-staging; do
  oc set env deployment/$d WIZARD_ACCESS_SECRET- -n gaik
done
oc get secret/gaik-demo-admin -n gaik -o jsonpath='{.data}' | grep -q WIZARD_ACCESS_SECRET &&
  oc patch secret/gaik-demo-admin -n gaik --type=json \
    -p '[{"op":"remove","path":"/data/WIZARD_ACCESS_SECRET"}]'
```

### Backend (gaik-demo-api)

| Variable                    | Description              | Source                       |
| --------------------------- | ------------------------ | ---------------------------- |
| `AZURE_API_KEY`             | Azure OpenAI API key     | Secret: `gaik-demo-api-keys` |
| `AZURE_ENDPOINT`            | Azure OpenAI endpoint    | Secret: `gaik-demo-api-keys` |
| `AZURE_API_VERSION`         | Azure API version        | Secret: `gaik-demo-api-keys` |
| `DOCLING_API_BASE`          | Docling parser API URL   | Secret: `gaik-demo-api-keys` |
| `DOCLING_API_PASSWORD`      | Docling parser API key   | Secret: `gaik-demo-api-keys` |
| `REPORT_RUN_TOKEN`          | Optional. The same value as on the frontend: report runs (Report Writer, v2, Source Normalizer, Knowledge Curator, Knowledge Synthesis) are accepted only with it | Secret: `gaik-demo-report-run` |
| `ANTHROPIC_FOUNDRY_API_KEY` | Claude server models and the Vision Extractor's Claude path: Azure Foundry API key | Secret: `gaik-demo-api-keys` |
| `ANTHROPIC_FOUNDRY_RESOURCE`| Claude server models and the Vision Extractor's Claude path: Azure Foundry resource name | Secret: `gaik-demo-api-keys` |
| `CLAUDE_CODE_USE_FOUNDRY`   | No longer read (the old Solution Wizard) | Secret: `gaik-demo-api-keys` |
| `ANTHROPIC_DEFAULT_SONNET_MODEL` | No longer read (the old Solution Wizard) | Secret: `gaik-demo-api-keys` |

## Route Annotations

The public route (`gaik-demo.2.rahtiapp.fi`) has these HAProxy annotations:

| Annotation | Value | Purpose |
|---|---|---|
| `haproxy.router.openshift.io/timeout` | `15m` | Allow long-running RAG indexing |
| `haproxy.router.openshift.io/proxy-body-size` | `128m` | Upload envelope hint; actual limits are enforced by the application |
| `haproxy.router.openshift.io/response-buffering` | `off` | Enable SSE streaming passthrough |
| `haproxy.router.openshift.io/disable-cookies` | `true` | Not needed for this app |

These are defined in `route.yaml` and applied via `oc apply -f route.yaml`.

## Deploy Script

```bash
cd implementation_layer/toolkit_demo_app/openshift

# Deploy API only
./deploy.sh api

# Deploy frontend only
./deploy.sh frontend

# Deploy both (skips DB if POSTGRESQL_PASSWORD not set)
./deploy.sh all

# Seed dental demo videos
./deploy.sh seed

# Verify deployment
./deploy.sh verify
```

## Files

| File                       | Description                      |
| -------------------------- | -------------------------------- |
| `deployment-frontend.yaml` | Frontend deployment (Next.js)    |
| `deployment-api.yaml`      | Backend API deployment (FastAPI) |
| `services.yaml`            | ClusterIP services for both      |
| `route.yaml`               | Public HTTPS route for frontend  |
| `networkpolicy-api.yaml`   | Only the frontend reaches the API (apply on its own) |
| `secrets.yaml.example`     | Example secrets template         |

## Report Writer upload limits

Both Report Writer versions allow **100 MiB total file content per run**, including
the sample report. `REPORT_WRITER_MAX_UPLOAD_MB` is read at runtime by the
**frontend** route handlers, not by the Python API. Update an existing deployment
without applying its manifest:

```bash
oc set env deployment/gaik-demo REPORT_WRITER_MAX_UPLOAD_MB=100 -n gaik
```

The frontend image sets `experimental.proxyClientMaxBodySize` to **128 MiB** so
multipart boundaries, filenames and configuration fit above the file budget.
Changing that setting requires rebuilding the frontend image. The Route retains
a matching body-size annotation as a hint; do not rely on it as enforcement.
The Report Writer handler enforces the file budget; unrelated demos retain their
own limits. The Route timeout remains 15 minutes.

Verify authenticated uploads through the public Route at exactly 100 MiB and
just over it: the former must parse successfully, the latter must return the
application's HTTP 413. Also complete a real audio report and check streaming,
downloads, frontend memory and pod restarts.
