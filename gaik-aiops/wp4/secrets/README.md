# Secrets management spike: OpenBao

Spike for S3. Runs as an overlay on the local compose stack, so the
default stack is unchanged.

```bash
docker compose -f deploy/compose/docker-compose.yml -f deploy/compose/openbao.yml up -d --build --wait
```

```bash
cd wp4/secrets && uv run --python 3.12 --extra dev pytest -q
```

## What it shows

| Point | How |
|---|---|
| Applications read secrets from files, not env vars | OpenBao Agent logs in with AppRole and renders the sink's DB DSN and token to a shared volume; the sink reads `COLLECTION_DSN_FILE` |
| Least privilege per consumer | Policies `api`, `sandbox`, `sink`, `collector`: each reads only its own path |
| Separate key for sandbox jobs | `deployments/local/sandbox` next to `deployments/local/api` |
| One vault-held pseudonymisation key | Random key in KV `gaik/collection/pseudonym`, created once and never overwritten; the collector's agent renders it to a file only the collector reads; logs and spans are hashed with it before any destination |
| Fail closed | The collector does not start until its agent has rendered the key, so nothing is exported unpseudonymised |
| Access is audited without exposing values | Audit device values are HMAC'd by OpenBao; only selected fields are forwarded |
| Vault access lands in the shared audit store | Audit file → collector `filelog` → `collection.audit_events` (service `openbao`), with event names, outcome, pseudonymised caller, masked address |

| File | What |
|---|---|
| `deploy/compose/openbao.yml` | Overlay: OpenBao dev server, init job, agent for the sink, sink and collector overrides |
| `deploy/compose/openbao/init.sh` | Audit device, KV and transit engines, policies, AppRoles (idempotent) |
| `deploy/compose/openbao/policies/` | One policy per consumer |
| `deploy/compose/openbao/agent-sink.hcl` | Sink agent: AppRole auto-auth, token file, DSN template |
| `deploy/compose/openbao/agent-collector.hcl` | Collector agent: AppRole auto-auth, pseudonymisation key template |
| `deploy/compose/openbao/otel-collector.openbao.yaml` | Collector overlay: key from the vault file; OpenBao audit file to audit events |
| `shared/collection/sink/collection_sink/pseudonym.py` | Transit HMAC client (kept as an option, not used by the overlay) |

## Not production setup

- Dev server: in-memory storage, auto-unsealed, root token. Production needs integrated (Raft) storage,
  an unseal procedure (Shamir keys or auto-unseal with a KMS), TLS, backups of the storage, and the root
  token revoked after setup. These go to the operating guide.
- AppRole secret ids are created by the init job. In Kubernetes the agent uses the `kubernetes` auth
  method with the pod's service account instead, so no secret id exists at all.
- Fake provider keys only; real values are written by an operator and never committed.
- The dev server keeps state in memory. When its container is recreated, the agent still holds a token
  from the old server and the sink refuses batches (503) until the agent re-authenticates; restart
  `openbao-agent-sink`. With persistent storage tokens survive a server restart.
- The audit file is not rotated here. In production rotate it and send SIGHUP to OpenBao; the collector
  follows rotated files.

## OpenBao audit events

| Event name | When |
|---|---|
| `secret.accessed` | Any request to a KV mount |
| `key.used` | Transit operations (other than the sink's pseudonymisation) |
| `secret.rotated` | `transit/keys/*/rotate` |
| `auth.login` | `auth/*/login` |
| `auth.token_renewed` | `auth/token/renew*` |
| `credential.issued` | AppRole secret id created |
| `config.changed` | Writes to policies, audit devices, auth methods, mounts, auth roles, transit key config |
| `vault.request` | Anything else |

Outcome is `success`, `denied` (permission denied) or `error`. The caller is the OpenBao entity id (or
display name), pseudonymised like every actor; `vault.auth.role` keeps the non-personal role name.
Request and response data are never forwarded.

The tests check that the agents' periodic reads do not make the event count grow while the stack is idle.

## Design note: where pseudonymisation happens

Once traces went to MLflow as a second backend, pseudonymisation had to happen before the fan-out, so
it moved from the sink (transit HMAC) to the collector. The collector has no
HMAC function, so it hashes with the vault-held key as a secret prefix to SHA-256. The trade-off: the key
now leaves the vault, as a 0400 file in the collector agent's volume, instead of staying inside the
transit engine; in return every store carries the same pseudonym and comparisons across MLflow, the
audit trail and metrics work. Rotating the key changes every pseudonym, so it is done only after a
compromise.
