#!/bin/sh
# Configures the local OpenBao dev server: audit device, KV and transit engines, policies, AppRoles.
# Idempotent. Values written here are local fakes; real ones are written by an operator, never committed.
set -eu
export BAO_ADDR=http://openbao:8200
until bao status >/dev/null 2>&1; do sleep 1; done

# Audit file read by the collector (uid 10001); the collector keeps its read offset in its own volume.
# stdout stays enabled as a second device: OpenBao refuses requests only if every audit device fails.
mkdir -p /bao/audit /otelcol-state
chown 100:1000 /bao/audit && chmod 0755 /bao/audit
chown 10001:10001 /otelcol-state
bao audit list 2>/dev/null | grep -q '^stdout/' || bao audit enable -path=stdout file file_path=stdout
bao audit list 2>/dev/null | grep -q '^file/' || bao audit enable -path=file file file_path=/bao/audit/audit.log mode=0644
bao secrets list | grep -q '^gaik/' || bao secrets enable -path=gaik -version=2 kv
bao secrets list | grep -q '^transit/' || bao secrets enable transit

fake() { echo "local-fake-$(head -c 12 /dev/urandom | od -An -tx1 | tr -d ' \n')"; }
bao kv get -mount=gaik deployments/local/api >/dev/null 2>&1 || bao kv put -mount=gaik deployments/local/api provider_key="$(fake)" >/dev/null
bao kv get -mount=gaik deployments/local/sandbox >/dev/null 2>&1 || bao kv put -mount=gaik deployments/local/sandbox provider_key="$(fake)" >/dev/null
# The collector's pseudonymisation key: random, created once and never overwritten, because a new key
# gives every user a new pseudonym and breaks comparisons over time (rotate only after a compromise).
bao kv get -mount=gaik collection/pseudonym >/dev/null 2>&1 || \
  bao kv put -mount=gaik collection/pseudonym key="$(bao write -field=random_bytes sys/tools/random/32 format=hex)" >/dev/null
bao kv put -mount=gaik collection/sink \
  dsn="postgresql://collection_writer:writer-local-only@postgres:5432/observability" >/dev/null

bao auth list | grep -q '^approle/' || bao auth enable approle
for role in sink collector api sandbox; do
  bao policy write "$role" "/init/policies/$role.hcl" >/dev/null
  bao write "auth/approle/role/$role" token_policies="$role" token_ttl=15m token_max_ttl=1h \
    secret_id_ttl=24h >/dev/null
done

# Credentials for the sink's and the collector's agents. In Kubernetes the agents use the kubernetes
# auth method instead.
mkdir -p /agent-out /agent-collector
for role in sink collector; do
  mkdir -p "/approle/$role"
  bao read -field=role_id "auth/approle/role/$role/role-id" > "/approle/$role/role_id"
  bao write -f -field=secret_id "auth/approle/role/$role/secret-id" > "/approle/$role/secret_id"
  chmod 0700 "/approle/$role"
  chmod 0400 "/approle/$role/role_id" "/approle/$role/secret_id"
done
chown -R 10001:10001 /approle /agent-out /agent-collector
chmod 0700 /agent-out /agent-collector
echo "openbao init done"
