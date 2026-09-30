# Solution Wizard Langfuse pilot

An optional pilot for `/solution-wizard`. Other demos and GAIK Ops keep their existing
behavior. Infrastructure lives beside the demo so its setup and instrumentation can
be reviewed together; credentials belong in private env files and Kubernetes Secrets.

## Try it

1. Open Solution Wizard with your existing wizard access.
2. Before the first message, enable **Save this session for diagnostics**. It defaults
   to off, applies to the whole session, and resets when you restart the wizard.
3. Use a synthetic example and open the login-protected Langfuse dashboard.
4. In project **Solution Wizard pilot**, open **Tracing** or **Sessions**. A session
   groups user turns; each turn contains streamed model generations and tool activity.

The CSC pilot dashboard is <https://langfuse-pilot.2.rahtiapp.fi>. Account signup is
disabled. The administrator credentials are provisioned privately, independently of
the demo login; no credentials or SDK keys belong in the browser or this repository.

## Recorded information and limits

- Turn input, including the first-turn wizard instructions and extracted attachment
  text; visible answers; tool inputs/results; model name, duration and errors.
- Provider-reported input/output tokens and separate cache-read/cache-write buckets
  for each streamed model generation. The SDK's aggregate turn usage and cost are
  metadata only, avoiding duplicate token/cost totals. Langfuse may infer generation
  cost from its model prices; Azure Foundry invoices remain the billing authority.
- The Claude CLI does **not** expose every internal model call's complete request
  prompt. Generations refer to their parent turn and preceding tools for context;
  an exact HTTP request/response audit is outside this pilot's scope.
- Parsed attachment text can be recorded; original uploads, thinking/signature deltas
  and binary payloads are not exported by this adapter. Known runtime credentials
  and common secret fields are masked. Masking is not personal-data anonymization.
- Exported text is capped at 32,000 characters per field and 200 child observations
  per turn. Long sessions can therefore have incomplete diagnostic content.
- No email/user account identifier is exported, only a random wizard session ID.
  Export errors must not stop the wizard. Background export means delivery is best
  effort; a process killed before its batch is sent can lose recent observations.

Use synthetic data. The privacy notice explains optional recording and deletion
requests. Restart without the checkbox to stop recording future turns; this does not
delete already stored observations. No automatic retention policy is configured in
this pilot; review and remove pilot data explicitly when the experiment ends.

## Rahti layout

`pilot.yaml` pins container digests for Langfuse v4 web/worker, ClickHouse and Valkey.
It runs with Rahti's arbitrary UID policy without a cluster-wide operator or privileged
containers. Only the TLS dashboard Route is public; data services are internal.

- PostgreSQL: a dedicated `langfuse_pilot` database and login role on the existing
  `pgvector-demo` service. Langfuse migrations run only against this database.
- ClickHouse and Valkey: separate subdirectories on a 10 GiB PVC, one replica with a
  Recreate strategy. This conserves PVC quota but couples their restart/storage.
- ClickHouse's `system.query_log` is enabled for Langfuse v4's legacy API usage
  background job, with a bounded memory buffer and a one-day TTL. This retention
  applies to SQL diagnostics, not the recorded wizard traces.
- CSC Allas: a private S3 bucket, separate `events/` and `media/` prefixes, `regionOne`
  and path-style addressing. Create the bucket before deployment; do not enable
  public access. S3 credentials must remain valid for the pilot's whole lifetime.
- Web and worker: one replica each. This is a pilot, with no high availability or
  backup/restore guarantee. Take database/PVC/Allas backups before a wider rollout.

Configured requests total approximately 1.05 CPU and 4.125 GiB RAM, roughly 7.8 Rahti
BU/hour under the CPU/memory formula, plus storage. Limits total 5.25 CPU and 8.25 GiB
RAM; reserve additional quota for demo build pods and rolling deployments.

## Reproduce the deployment

Prerequisites: `oc` login, permission in your Rahti namespace, the existing PostgreSQL
service, a private Allas bucket, and an isolated PostgreSQL database/login that owns
only that database. Create the database and role with your database administrator;
do not point `DATABASE_URL` at the demo's database or use its superuser for Langfuse.

Copy `secrets.env.example` **outside the checkout**, replace every `CHANGE_ME`, and
generate separate random credentials. `ENCRYPTION_KEY` must be 64 hexadecimal
characters. Keep the authentication, encryption and database keys stable after setup.
Use your actual Route host in `NEXTAUTH_URL` and `pilot.yaml`.

```powershell
# Run from this directory; the env file is private and never committed.
./deploy.ps1 -Namespace gaik -SecretEnvFile /private/pilot.env -EnableWizard
```

The script applies only this folder's Langfuse resources. With `-EnableWizard`, it
creates a separate server-side SDK secret and uses targeted `oc set env` on
`gaik-demo-api`, preserving all existing demo environment variables. Deploy the
instrumented demo code through the normal `deploy/demo-app` branch workflow.

After editing existing Secrets, restart the affected deployments to load new values;
the database password must match the role. Initialization variables bootstrap the
account/project once; rotating API keys or account passwords afterwards requires
Langfuse's account/project settings, not merely changing initialization variables.

Verify web `/api/public/health`, worker readiness, a synthetic wizard trace with
generation usage, and an opt-out session before calling the pilot successful.

## Disable and expand

Disable new recording without touching data:

```bash
oc -n gaik set env deployment/gaik-demo-api WIZARD_LANGFUSE_ENABLED=false
oc -n gaik rollout status deployment/gaik-demo-api
```

Keep the database, PVC and Allas bucket until their retention/deletion is agreed.
To expand later, add explicit adapters for other demos and a link/summary in GAIK Ops.
Review consent, retention, model pricing, resource usage and backup/restore first.

References: [Langfuse self-hosting](https://langfuse.com/self-hosting),
[token and cost tracking](https://langfuse.com/docs/observability/features/token-and-cost-tracking).
