# GAIK Solution Wizard V2 — Rahti 2 deployment (staging)

OpenShift/Rahti 2 manifests + deploy script for the V2 stack:

- **wizard-v2-web** — `solution_wizard_v2` (Next.js), public HTTPS route.
- **wizard-v2-api** — `wizard_api` (FastAPI) + live V1 agent, ClusterIP only.
- **wizard-v2-db** — Postgres (`pgvector/pgvector:pg17`) with a PVC.
- PVCs for the DB and for generated session output.

Modelled on `implementation_layer/toolkit_demo_app/openshift/` (same registry,
buildx schema2 requirement, SSE route annotations).

> **Target: a separate staging project.** The manifests omit `namespace:` on
> purpose — `oc project` / `oc apply -n <project>` decides placement, and
> `deploy.sh` substitutes the project into the image references. The staging
> project must be created and access granted (CSC / infra) before deploying.

## Architecture

```
Internet ──HTTPS──▶ Route (wizard-v2-web)
                       │
                       ▼
                  wizard-v2-web (Next.js :3000)
                       │  server-side proxy, WIZARD_API_URL
                       ▼
                  wizard-v2-api (FastAPI :8100) ──▶ wizard-v2-db (:5432, PVC)
                       │                          └▶ /data/sessions (PVC)
                       ▼
              Claude Agent SDK → Azure Foundry (secret gaik-demo-api-keys)
```

## One-time setup

```bash
oc login https://api.2.rahti.csc.fi:6443
export PROJECT=<your-staging-project>
oc project "$PROJECT"
```

Fill in secrets (all real values live here, never in tracked YAML):

```bash
cd implementation_layer/deploy/openshift
cp secrets.yaml.example secrets.yaml     # secrets.yaml is gitignored
# edit secrets.yaml: DB creds/url, service token, NEXT_SERVER_ACTIONS_ENCRYPTION_KEY
./deploy.sh secrets                      # apply BEFORE the manifests
```

> **No secrets in git.** Only `secrets.yaml.example` (placeholders) is tracked.
> `postgres.yaml` contains no password field — the `wizard-v2-db` Secret comes
> from `secrets.yaml`. The DB pod stays pending until that Secret is applied.
>
> Model-provider keys (Foundry for the agent, Azure OpenAI for sandbox runs)
> come from the **project-wide** Secret `gaik-demo-api-keys`, shared with the
> demo app. It is not part of `secrets.yaml`; `deployment-api.yaml` and
> `sandbox-job.yaml` read it as `optional: true`. Sandbox runs can read their
> Azure settings from another Secret with the same keys, for example one with a
> spending cap: set `WIZARD_POC_RUNNER_SECRET=<secret name>` on the api
> Deployment. The api and the agent keep the shared Secret. Setting it to a
> Secret with its own capped key also turns on code editing in the PoC tab's
> editor: user-written code (`.py`, `requirements.txt`) and `config.yaml` run
> only with a separate runner key, so with the shared Secret those files stay
> read-only.

## Deploy

```bash
export NEXT_PUBLIC_SUPABASE_URL=...        # baked into the web build
export NEXT_PUBLIC_SUPABASE_ANON_KEY=...
export NEXT_PUBLIC_DEV_AUTH=false          # true = built-in dev login only

./deploy.sh all        # manifests → api → web → poc-runner
# or step by step:
./deploy.sh manifests
./deploy.sh api
./deploy.sh web
./deploy.sh poc-runner
./deploy.sh verify
```

With Supabase auth (`NEXT_PUBLIC_DEV_AUTH=false`), go through the
[Supabase sign-in checklist](#supabase-sign-in-checklist) before rolling out a release.

`deploy.sh` builds single-arch `linux/amd64` Docker schema2 images straight to
the registry (`--output type=registry,oci-mediatypes=false`) via a
`docker-container` buildx builder — the same dance the demo app needs because
Rahti's registry rejects Docker's default OCI manifest output.

The public URL is auto-assigned (`route.yaml` omits `spec.host`):

```bash
oc get route wizard-v2-web -n "$PROJECT" -o jsonpath='{.spec.host}'
```

## What the api may do in the cluster (rbac.yaml)

`rbac.yaml` gives each instance's api its own ServiceAccount (`wizard-v2[-s4]-api`)
and a Role limited to what the sandbox runner does: create and read Jobs, read
pods and pod logs. No `secrets`. `deploy.sh manifests` applies it first. Before
this the api ran as the namespace's default account, which either could not
create Jobs at all or, where that account had been given `edit`, could read every
Secret in the project.

## The agent's own container (deployment-api.yaml)

The api pod has two containers. The api keeps the database address, the service
token and the cluster token. The `agent` container runs the wizard's agent CLI
and every command the agent runs; it has the model settings and the sessions
volume, and nothing else. The api's SDK starts `wizard-agent-cli`, which asks
`wizard-agent-bridge` in the agent container over a socket on a shared
in-memory volume to start the CLI there, and relays its pipes
(`wizard_api/agent_bridge.py`). The tool hook and the wizard's own tools still
run in the api. Without `WIZARD_AGENT_BRIDGE_SOCKET` the api starts the CLI
itself, as before, which is how local development runs.

The ServiceAccount token is no longer mounted into every container
(`automountServiceAccountToken: false`); the api container gets it through the
`cluster-token` volume at the path the Kubernetes client reads.

A live Deployment is not given the manifest (see Deploy). Patch it instead:
`scripts/agent-container-patch.py` prints a strategic-merge patch that adds the
agent container, the two volumes, the api's socket variable and mounts and the
new memory split, and leaves every other variable on the Deployment alone:

```bash
INSTANCE=s4 PROJECT="$PROJECT" python3 scripts/agent-container-patch.py > agent-patch.json
oc patch deployment/wizard-v2-s4-api -n "$PROJECT" --type=strategic --patch-file agent-patch.json
```

Memory moves with the agent: the api container is limited to 1.5 GiB and the
agent container to 3 GiB, where each live session's CLI now runs. Check both on
s4 with several sessions open before staging.

## What a sandbox run may reach (networkpolicy-sandbox.yaml)

A sandbox run executes code the agent generated, so its pod gets only DNS, its
own stack's api on 8100 (the package fetch) and TCP 443 to public addresses
(the model provider). Private, link-local (cloud metadata) and loopback ranges
are excluded, and nothing may connect to a run. The policy selects runs by the
`wizard-v2/instance` label `sandbox-job.yaml` sets, so runs created by an api
image older than that label are not covered: roll out the api after applying
the policy.

Check it against a local cluster before applying it to a shared project:

```bash
KUBE_CONTEXT=colima-k8s ./scripts/test-sandbox-egress.sh
```

NetworkPolicy works on addresses: any public host on 443 stays reachable.
Limiting runs to the provider's domain needs an egress firewall or a proxy.

Roll back: delete the policy and runs reach what they did before. The api does
not need a rollout; the instance label does nothing without the policy.

```bash
oc -n "$PROJECT" delete networkpolicy "$NAME-poc-run"   # e.g. wizard-v2-poc-run
```

## Two instances in one project

Every resource name is built from `NAME_PLACEHOLDER`, which `deploy.sh`
substitutes with `wizard-v2` (the staging stack) or `wizard-v2-<INSTANCE>`.
That covers the Deployments, Services, Route, PVCs, the db/web/token Secrets,
the container names and the **image repositories** — two stacks sharing one
`:latest` tag would otherwise pull each other's build on the next restart.
What stays shared is the project-wide `gaik-demo-api-keys` Secret and the
Supabase project.

To run a second code line (say sprint4) next to staging, with its own database,
session storage, images and URL:

```bash
export PROJECT=<the same project>
export INSTANCE=s4                         # lowercase letters, digits, dashes

# once: its own secrets (fresh password + token; the same secrets.yaml copy
# works, deploy.sh substitutes the instance into the names and the DB host)
./deploy.sh secrets

# from the branch to deploy (deploy.sh refuses an unpushed commit):
./deploy.sh all
./deploy.sh verify                         # route: wizard-v2-s4-web-<project>.2.rahtiapp.fi
```

`./deploy.sh render <manifest>` prints any manifest exactly as it would be
applied, without a cluster; `implementation_layer/unit_tests/test_deploy_instances.py`
renders every manifest for both instances and fails on any name that is not
instance-scoped.

Before the first second instance: add its route host to the Supabase project's
redirect URLs, and check the project quota has room for another Postgres, api
and web pod plus sandbox Jobs (`oc describe quota -n "$PROJECT"`).

**Known gap (#91 follow-up):** `sandbox-job.yaml` is rendered by the api at run
time, not by `deploy.sh`, and still names `wizard-v2-api` and `wizard-v2-token`
outright. A second instance's sandbox Jobs would fetch the PoC package from the
staging api. The api now exports `WIZARD_INSTANCE_NAME` so the sandbox runner
can render its own prefix into the Job.

From CI (`.github/workflows/wizard-v2-deploy.yml`): *Run workflow* from the branch
to deploy, with the `instance` input set. A `wizard-v2*` tag deploys nothing. The
live deployments carry settings the manifests lack, so a release reaches staging
target by target: build the api and web images from the tag, then restart each
deployment. Do not run `deploy.sh all` against a live stack.

## Sign-in through Keycloak (signin-proxy.yaml)

Instead of the dev accounts, a stack can sign its users in at the GAIK Keycloak
(`../keycloak`, its README says how to bring it up, add accounts and add
Google). `PROJECT=<project> INSTANCE=<name> ./deploy.sh signin` runs an
oauth2-proxy in front of the web app, points the stack's Route at it and sets
the web app's `WIZARD_AUTH_MODE=proxy` and `WIZARD_OIDC_*`; `signin-off` undoes
it. The web app does not take the proxy's word for who the user is: it checks the
forwarded access token itself (`lib/proxy-auth.ts`).

## Environment variables

**wizard-v2-api** (runtime):

| Var | Source | Notes |
|-----|--------|-------|
| `WIZARD_INSTANCE_NAME` | deployment | resource-name prefix of this stack (`wizard-v2` or `wizard-v2-<instance>`) |
| `WIZARD_DATABASE_URL` | secret `wizard-v2-db` / `database-url` | `postgresql+psycopg://…@wizard-v2-db:5432/wizard_v2` |
| `WIZARD_SESSION_OUTPUT_ROOT` | deployment | `/data/sessions` (PVC) |
| `WIZARD_MAX_CASES_PER_SESSION` | deployment | cases one session may open; default `100` |
| `WIZARD_MAX_SESSION_INPUT_MB` | deployment | input of all of one session's cases together; default `1024`. Size it to the sessions PVC, which every session shares |
| `WIZARD_SESSION_MAX_COST_USD`, `WIZARD_USER_MAX_COST_USD`, `WIZARD_DEPLOYMENT_MAX_COST_USD`, `WIZARD_MAX_SESSIONS_PER_USER`, `WIZARD_COST_WARN_RATIO` | deployment (`oc set env`) | usage caps, on by default (5.4 / 10.8 / 2000 USD, 3 sessions, 0.8); `0` turns a cap off. See the API README, "Usage caps" |
| `WIZARD_API_TOKEN` | secret `wizard-v2-token` | service token, same value on web (#135) |
| `CLAUDE_CODE_USE_FOUNDRY` | secret `gaik-demo-api-keys` | `1` in prod |
| `ANTHROPIC_FOUNDRY_API_KEY` | secret `gaik-demo-api-keys` | Azure Foundry key |
| `ANTHROPIC_FOUNDRY_RESOURCE` | secret `gaik-demo-api-keys` | `haagahelia-poc-gaik` |
| `ANTHROPIC_DEFAULT_SONNET_MODEL` | secret `gaik-demo-api-keys` | e.g. `claude-sonnet-4-6` |
| `AZURE_API_KEY` | secret `gaik-demo-api-keys` | Azure OpenAI key for the agent's own tool calls (Phase 4 `generate_schema.py` → GAIK SchemaGenerator) |
| `AZURE_ENDPOINT` | secret `gaik-demo-api-keys` | `https://<resource>.openai.azure.com/` |
| `AZURE_API_VERSION` | secret `gaik-demo-api-keys` | optional, gaik default otherwise |
| `AZURE_DEPLOYMENT` | secret `gaik-demo-api-keys` | optional, gaik default deployment otherwise |

Without the Foundry secret the pod still starts (`optional: true`), but the
agent chat endpoint won't work. Without the `AZURE_*` values the chat works but
the agent stops at Phase 4: `generate_schema.py` needs them (and the `gaik`
package the api image installs) to generate the extraction schema.

**wizard-v2-web**: `WIZARD_API_URL` (runtime, → `http://wizard-v2-api:8100`),
`WIZARD_AGENT_CHAT=true` (live agent, not mock), `WIZARD_API_TOKEN` and
`NEXT_SERVER_ACTIONS_ENCRYPTION_KEY` (runtime secrets). `NEXT_PUBLIC_SUPABASE_URL`
/ `NEXT_PUBLIC_SUPABASE_ANON_KEY` / `NEXT_PUBLIC_DEV_AUTH` are **build-time**
args (baked into the bundle). With Supabase auth, set `WIZARD_ALLOWED_EMAILS`
(runtime, comma-separated): only the listed accounts get in, and nobody without
it, since anyone can create an account in the Supabase project with its public key.
`GAIK_DEMO_URL` (runtime, optional) is where the sign-in page and the account
menu link back to the GAIK demos; it defaults to `https://gaik-demo.2.rahtiapp.fi`,
and an empty value hides the link.

### Supabase sign-in checklist

Go through this before rolling out a release that contains #43, and when a new
stack or a new Supabase project is set up.

Since #43 the web app lets a Supabase user in only when their address is listed
in `WIZARD_ALLOWED_EMAILS` **and** Supabase has confirmed that address. An unset
or empty `WIZARD_ALLOWED_EMAILS` means nobody gets in.

1. **Set `WIZARD_ALLOWED_EMAILS` on the live web Deployment first.** It is in no
   manifest. Set it with `oc set env` before the rollout, so the new pods start
   with it:

   ```bash
   oc set env deployment/wizard-v2-web -n "$PROJECT" \
     WIZARD_ALLOWED_EMAILS='<comma-separated addresses>'
   ```

   For a second instance, the Deployment is `wizard-v2-<instance>-web`. Never
   `oc apply` the deployment manifests to do this. The live Deployments carry
   env vars the manifests lack, and applying them drops those. On a live stack,
   roll out with `./deploy.sh web` (and `api`, `poc-runner`), which builds the
   image and restarts the Deployment. Do not use `./deploy.sh manifests` or
   `all`, which apply `deployment-*.yaml`.
2. **In the Supabase project:**
   - Turn off public sign-up: *Authentication → Sign In / Providers → Allow new
     users to sign up* off.
   - Keep *Confirm email* on.
   - Keep *Secure email change* on.
   - Create accounts by invitation, or create them by hand with *Auto Confirm
     User*.

   Without these settings, someone can register a listed address that has no
   account yet, and then get in as that user.
3. **After the rollout**, check with a listed account that sign-in works. Check
   with an unlisted one that it is refused.

## Notes / open items

- **Health**: api uses `GET /health`; web has no `/api/health` route yet, so its
  probes are `tcpSocket:3000`. Add a real health route later for deeper checks.
- **Single replica**: `wizard-v2-api` is `Recreate` + RWO PVC + per-session live
  agent state — do not scale beyond 1 replica without moving session output to
  RWX/S3 (Allas) and externalising agent state.
- **Migrations** run on api startup (`alembic upgrade head`); the pod restarts
  until the DB is reachable.
- **Test gate on deploy** — the workflow's `require-green-ci` job refuses a
  commit whose four Solution Wizard V2 checks (`wizard-api`,
  `solution-wizard`, `solution-wizard-v2`, `deploy-manifests`) are not all
  green, or that CI never ran. `deploy-manifests` is the job that runs the
  sandbox Job manifest and deploy-script tests, so a manifest change cannot be
  deployed past a red test. Push the branch and let CI finish before tagging or dispatching.
  `deploy.sh` run by hand has no such gate.
- **RAHTI_TOKEN expiry** — the Rahti `oc login` / registry token (CSC
  service-account token, not stored in this repo) is **~1 year** long. Record
  its expiry date here and renew before then, or deploys silently stop working:
  - RAHTI_TOKEN expires: `TODO — fill from CSC` (created ~09/2026).
