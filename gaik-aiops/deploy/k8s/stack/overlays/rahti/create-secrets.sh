#!/usr/bin/env bash
# Creates the stack's Secrets in the Rahti project, once. Every value is generated here and goes to
# Rahti through a pipe: nothing is printed, written to disk (no here-documents, which older bash keeps
# in temporary files) or put on a command line (printf is a shell builtin).
#
# An existing Secret is never replaced. Postgres takes its passwords when it first starts, and a new
# pseudonym key would give every user a new pseudonym. To rotate one, see README.md.
#
#   oc project gaik-aiops
#   deploy/k8s/stack/overlays/rahti/create-secrets.sh
set -euo pipefail

NAMESPACE="${NAMESPACE:-gaik-aiops}"
MLFLOW_USER="${MLFLOW_USER:-gaik-reviewer}"

current="$(oc project -q)"
if [ "$current" != "$NAMESPACE" ]; then
  echo "oc is on project '$current', not '$NAMESPACE'. Run: oc project $NAMESPACE" >&2
  exit 1
fi
command -v htpasswd >/dev/null || { echo "htpasswd is missing (on Debian/Ubuntu: apache2-utils)" >&2; exit 1; }

rand() { openssl rand -hex 24; }

# create NAME: reads the Secret's stringData lines (  key: "value") on stdin.
create() {
  local name="$1" data
  data="$(cat)"
  if oc get secret "$name" -n "$NAMESPACE" >/dev/null 2>&1; then
    echo "kept    $name (it exists)"
    return
  fi
  printf 'apiVersion: v1\nkind: Secret\nmetadata:\n  name: %s\n  labels: {app.kubernetes.io/part-of: gaik-aiops}\ntype: Opaque\nstringData:\n%s\n' \
    "$name" "$data" | oc create -n "$NAMESPACE" -f - >/dev/null
  echo "created $name"
}

printf '  owner-password: "%s"\n  admin-password: "%s"\n  writer-password: "%s"\n  reader-password: "%s"\n  mlflow-password: "%s"\n' \
  "$(rand)" "$(rand)" "$(rand)" "$(rand)" "$(rand)" | create aiops-db

printf '  key: "%s"\n' "$(openssl rand -hex 32)" | create aiops-pseudonym

printf '  admin-password: "%s"\n' "$(rand)" | create aiops-grafana

# The MLflow sign-in: the password in plain text, so it can be handed to reviewers, and its bcrypt hash
# for nginx. Cost 4, bcrypt's lowest: nginx checks the hash on every request, and a 192-bit random
# password needs no slow hash.
mlflow_password="$(rand)"
mlflow_htpasswd="$(printf '%s' "$mlflow_password" | htpasswd -niB -C 4 "$MLFLOW_USER" | head -n 1)"
printf '  username: "%s"\n  password: "%s"\n  htpasswd: '"'"'%s'"'"'\n' "$MLFLOW_USER" "$mlflow_password" "$mlflow_htpasswd" |
  create aiops-mlflow-auth
unset mlflow_password mlflow_htpasswd

echo
echo "Read a sign-in when you need it, in your own terminal (it prints the password there):"
echo "  oc extract secret/aiops-grafana --keys=admin-password --to=-          # Grafana user: admin"
echo "  oc extract secret/aiops-mlflow-auth --keys=username,password --to=-   # MLflow"
