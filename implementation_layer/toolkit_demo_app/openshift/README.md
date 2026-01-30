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

```bash
# Backend API (runs from repo root)
docker build -t gaik-demo-api -f implementation_layer/api/Dockerfile .
docker tag gaik-demo-api image-registry.apps.2.rahti.csc.fi/gaik/gaik-demo-api:latest
docker push image-registry.apps.2.rahti.csc.fi/gaik/gaik-demo-api:latest

# Frontend (runs from demo directory)
cd implementation_layer/toolkit_demo_app
docker build -t gaik-demo .
docker tag gaik-demo image-registry.apps.2.rahti.csc.fi/gaik/gaik-demo:latest
docker push image-registry.apps.2.rahti.csc.fi/gaik/gaik-demo:latest
cd ../..
```

## Environment Variables

### Frontend (gaik-demo)

| Variable                               | Description          | Source                                 |
| -------------------------------------- | -------------------- | -------------------------------------- |
| `BACKEND_URL`                          | Internal API URL     | Hardcoded: `http://gaik-demo-api:8000` |
| `ADMIN_PASSWORD`                       | Admin dashboard auth | Secret: `gaik-demo-admin`              |
| `NEXT_PUBLIC_SUPABASE_URL`             | Supabase project URL | Secret: `gaik-demo-supabase`           |
| `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` | Supabase anon key    | Secret: `gaik-demo-supabase`           |
| `SUPABASE_SECRET_KEY`                  | Supabase service key | Secret: `gaik-demo-supabase`           |

### Backend (gaik-demo-api)

| Variable            | Description           | Source                       |
| ------------------- | --------------------- | ---------------------------- |
| `AZURE_API_KEY`     | Azure OpenAI API key  | Secret: `gaik-demo-api-keys` |
| `AZURE_ENDPOINT`    | Azure OpenAI endpoint | Secret: `gaik-demo-api-keys` |
| `AZURE_API_VERSION` | Azure API version     | Secret: `gaik-demo-api-keys` |

## Files

| File                       | Description                      |
| -------------------------- | -------------------------------- |
| `deployment-frontend.yaml` | Frontend deployment (Next.js)    |
| `deployment-api.yaml`      | Backend API deployment (FastAPI) |
| `services.yaml`            | ClusterIP services for both      |
| `route.yaml`               | Public HTTPS route for frontend  |
| `secrets.yaml.example`     | Example secrets template         |
