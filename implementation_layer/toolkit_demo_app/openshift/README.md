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

## Quick Deploy

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
| `NEXT_PUBLIC_SUPABASE_URL`             | Supabase project URL | Secret: `gaik-demo-supabase`           |
| `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` | Supabase anon key    | Secret: `gaik-demo-supabase`           |
| `SUPABASE_SECRET_KEY`                  | Supabase service key | Secret: `gaik-demo-supabase`           |
| `WIZARD_ACCESS_SECRET`                 | Unlocks the gated Solution Wizard (`/solution-wizard?key=<secret>`) | Secret: `gaik-demo-admin` |

### Backend (gaik-demo-api)

| Variable                    | Description              | Source                       |
| --------------------------- | ------------------------ | ---------------------------- |
| `AZURE_API_KEY`             | Azure OpenAI API key     | Secret: `gaik-demo-api-keys` |
| `AZURE_ENDPOINT`            | Azure OpenAI endpoint    | Secret: `gaik-demo-api-keys` |
| `AZURE_API_VERSION`         | Azure API version        | Secret: `gaik-demo-api-keys` |
| `DOCLING_API_BASE`          | Docling parser API URL   | Secret: `gaik-demo-api-keys` |
| `DOCLING_API_PASSWORD`      | Docling parser API key   | Secret: `gaik-demo-api-keys` |
| `CLAUDE_CODE_USE_FOUNDRY`   | Solution Wizard: route Claude Agent SDK via Azure Foundry (`1`) | Secret: `gaik-demo-api-keys` |
| `ANTHROPIC_FOUNDRY_API_KEY` | Solution Wizard: Azure Foundry API key | Secret: `gaik-demo-api-keys` |
| `ANTHROPIC_FOUNDRY_RESOURCE`| Solution Wizard: Azure Foundry resource name | Secret: `gaik-demo-api-keys` |
| `ANTHROPIC_DEFAULT_SONNET_MODEL` | Solution Wizard: model id (e.g. `claude-sonnet-4-6`) | Secret: `gaik-demo-api-keys` |

## Route Annotations

The public route (`gaik-demo.2.rahtiapp.fi`) has these HAProxy annotations:

| Annotation | Value | Purpose |
|---|---|---|
| `haproxy.router.openshift.io/timeout` | `15m` | Allow long-running RAG indexing |
| `haproxy.router.openshift.io/proxy-body-size` | `50m` | Allow large PDF uploads (up to 20MB app limit) |
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
| `secrets.yaml.example`     | Example secrets template         |
