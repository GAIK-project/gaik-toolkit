# GAIK Toolkit API — OpenShift deployment

Standalone FastAPI deployment of `implementation_layer/api` to CSC Rahti 2.
Exposes `/transcribe`, `/parse`, `/pipeline/*`, **`/extract/form`**,
**`/form/understand`**, and `/health`. Authentication is `X-API-Key` header.

Namespace: `gaik`
Route host: `https://gaik-toolkit-api.2.rahtiapp.fi`

## Files

| File | Purpose |
|---|---|
| `deployment.yaml` | K8s Deployment. 1 replica, 0.5-2 CPU, 1-4 Gi RAM, slow-LLM probe tuning. |
| `service.yaml` | ClusterIP Service on port 8000. |
| `route.yaml` | Edge-TLS Route, 2 min HAProxy timeout for long LLM calls. |
| `secrets.yaml.example` | Template for `API_KEY`, Azure OpenAI creds. |
| `deploy.sh` | Build + push image, apply manifests, rollout. |

## First-time setup

```bash
# One-off: log in, pick project, registry login
oc login https://api.2.rahti.csc.fi:6443
oc project gaik
oc registry login

# Create the secret (fill in values first)
cp secrets.yaml.example secrets.yaml
openssl rand -hex 32  # paste into secrets.yaml as API_KEY
# also fill AZURE_API_KEY, AZURE_ENDPOINT, AZURE_API_VERSION, AZURE_DEPLOYMENT
oc apply -f secrets.yaml -n gaik

# Build + deploy in one go
cd implementation_layer/api/openshift
chmod +x deploy.sh
./deploy.sh all
```

## Smoke test after deploy

```bash
KEY=$(oc get secret gaik-toolkit-api-keys -n gaik -o jsonpath='{.data.API_KEY}' | base64 -d)

curl -H "X-API-Key: $KEY" https://gaik-toolkit-api.2.rahtiapp.fi/health
# → {"status":"healthy","service":"gaik-api","version":"1.0.0"}

curl -X POST https://gaik-toolkit-api.2.rahtiapp.fi/extract/form/ \
  -H "X-API-Key: $KEY" -H "content-type: application/json" \
  -d '{
    "fields": [
      {"id":"name","label":"Full name","type":"text"},
      {"id":"email","label":"Email","type":"text","htmlType":"email"}
    ],
    "sourceText": "My name is Matti Meikäläinen and my email is matti@example.com."
  }'
# → {"values":{"name":"Matti Meikäläinen","email":"matti@example.com"}}
```

## Subsequent updates

After changes under `implementation_layer/api/` or `implementation_layer/src/`:

```bash
./deploy.sh all   # rebuild, push, restart pods
```

## Troubleshooting

- `oc logs deployment/gaik-toolkit-api -n gaik --tail=100` — runtime logs.
- `oc describe pod -n gaik -l app=gaik-toolkit-api` — pod events and status.
- 401 from curl: `API_KEY` env var on the pod doesn't match what you sent.
  Update the Secret and `oc rollout restart deployment/gaik-toolkit-api -n gaik`.
- 502 from the Route: pod is crashing — check logs.
- Slow first call: Azure OpenAI cold start; second call is fast.
