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

`networkpolicy-api.yaml` lets only the frontend pods reach the API on port 8000
(`gaik-demo` to `gaik-demo-api`, and `gaik-demo-staging` to `gaik-demo-api-staging`).
`proxy.ts` is the only sign-in, approval and trial gate in front of the API, so no other
pod in the project should reach the API directly. The kubelet's health probes are not
affected, and the API has no route of its own.

Apply the policy file on its own. Never `oc apply` the deployment manifests to a
running environment: the live deployments carry env vars these files lack.

```bash
# 1. See what is already there. NetworkPolicies add up: any policy that also selects
#    the API pods and admits more (an empty rule `ingress: [{}]`, a `from` with
#    `podSelector: {}` or `namespaceSelector: {}`) still lets other pods in, and the
#    new policy then changes nothing.
oc get networkpolicy -n gaik -o yaml

# 2. Check the labels the policy selects on.
oc get pods -n gaik -L app
```

If such a policy exists, keep it for the other pods and take the API pods out of its
`podSelector`, for example:

```yaml
spec:
  podSelector:
    matchExpressions:
      - key: app
        operator: NotIn
        values: [gaik-demo-api, gaik-demo-api-staging]
```

```bash
# 3. Apply the policy.
oc apply -f networkpolicy-api.yaml -n gaik

# 4. Check: each frontend still reaches its API, another pod does not.
oc exec -n gaik deployment/gaik-demo -- \
  bun -e "fetch('http://gaik-demo-api:8000/health').then(r => console.log(r.status))"
oc exec -n gaik deployment/gaik-demo-staging -- \
  bun -e "fetch('http://gaik-demo-api-staging:8000/health').then(r => console.log(r.status))"
oc run np-check -n gaik --rm -i --restart=Never --image=curlimages/curl:8.11.1 -- \
  curl -s -m 5 -o /dev/null -w '%{http_code}\n' http://gaik-demo-api:8000/health
# The last command times out once the policy is in force.
```

Roll back with `oc delete networkpolicy gaik-demo-api-from-frontend gaik-demo-api-staging-from-frontend -n gaik`.

The deployment manifests state the pod hardening: no privilege escalation, all Linux
capabilities dropped, a non-root user and the runtime's default seccomp profile.
OpenShift's `restricted-v2` SCC may already enforce these; see which SCC the pods run
under with `oc get pods -n gaik -o custom-columns=NAME:.metadata.name,SCC:.metadata.annotations.openshift\.io/scc`.
The root filesystem stays writable in both: the API writes model caches, uploads and
generated files, and Next.js writes its cache under `/app/.next/cache`. Add the same
settings to a running deployment with `oc patch`, which merges containers by name and
keeps the env vars. The loop reads each deployment's container name, which may differ
from the deployment name on staging:

```bash
for d in gaik-demo-api gaik-demo gaik-demo-api-staging gaik-demo-staging; do
  c=$(oc get deployment/$d -n gaik -o jsonpath='{.spec.template.spec.containers[0].name}')
  oc patch deployment/$d -n gaik --type=strategic -p "{
    \"spec\": {\"template\": {\"spec\": {
      \"securityContext\": {\"runAsNonRoot\": true,
        \"seccompProfile\": {\"type\": \"RuntimeDefault\"}},
      \"containers\": [{\"name\": \"$c\", \"securityContext\": {
        \"allowPrivilegeEscalation\": false,
        \"capabilities\": {\"drop\": [\"ALL\"]}}}]}}}}"
  oc rollout status deployment/$d -n gaik --timeout=240s
done
```

To take the settings off again, remove them with a JSON patch rather than
`oc rollout undo`, which on these image-triggered deployments can bring back an older
image:

```bash
oc patch deployment/<name> -n gaik --type=json -p '[
  {"op": "remove", "path": "/spec/template/spec/securityContext/runAsNonRoot"},
  {"op": "remove", "path": "/spec/template/spec/securityContext/seccompProfile"},
  {"op": "remove", "path": "/spec/template/spec/containers/0/securityContext"}]'
```

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

## Environment Variables

### Frontend (gaik-demo)

| Variable                               | Description          | Source                                 |
| -------------------------------------- | -------------------- | -------------------------------------- |
| `BACKEND_URL`                          | Internal API URL     | Hardcoded: `http://gaik-demo-api:8000` |
| `ADMIN_PASSWORD`                       | Admin dashboard auth | Secret: `gaik-demo-admin`              |
| `ADMIN_SESSION_SECRET`                 | Optional. Signs the admin session cookie; falls back to `ADMIN_PASSWORD` | Secret: `gaik-demo-admin` |
| `NEXT_PUBLIC_SUPABASE_URL`             | Supabase project URL | Secret: `gaik-demo-supabase`           |
| `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` | Supabase anon key    | Secret: `gaik-demo-supabase`           |
| `SUPABASE_SECRET_KEY`                  | Supabase service key | Secret: `gaik-demo-supabase`           |
| `WIZARD_ACCESS_SECRET`                 | Old wizard gate on `/api/wizard`; read until that gate is removed | Secret: `gaik-demo-admin` |
| `WIZARD_V2_URL`                        | Optional. Wizard V2 address the `/solution-wizard` notice links to, read at run time | `oc set env` |

### Backend (gaik-demo-api)

| Variable                    | Description              | Source                       |
| --------------------------- | ------------------------ | ---------------------------- |
| `AZURE_API_KEY`             | Azure OpenAI API key     | Secret: `gaik-demo-api-keys` |
| `AZURE_ENDPOINT`            | Azure OpenAI endpoint    | Secret: `gaik-demo-api-keys` |
| `AZURE_API_VERSION`         | Azure API version        | Secret: `gaik-demo-api-keys` |
| `DOCLING_API_BASE`          | Docling parser API URL   | Secret: `gaik-demo-api-keys` |
| `DOCLING_API_PASSWORD`      | Docling parser API key   | Secret: `gaik-demo-api-keys` |
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
