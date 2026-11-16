#!/usr/bin/env bash
# Creates the stack's Secrets in the Rahti project, once. Every value is generated here and goes to
# Rahti on stdin: nothing is printed, written to disk or put on a command line.
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

# create NAME: reads the Secret's stringData lines (key: value) on stdin.
create() {
  local name="$1" data
  data="$(cat)"
  if oc get secret "$name" -n "$NAMESPACE" >/dev/null 2>&1; then
    echo "kept    $name (it exists)"
    return
  fi
  oc create -n "$NAMESPACE" -f - >/dev/null <<EOF
apiVersion: v1
kind: Secret
metadata:
  name: $name
  labels: {app.kubernetes.io/part-of: gaik-aiops}
type: Opaque
stringData:
$data
EOF
  echo "created $name"
}

create aiops-db <<EOF
  owner-password: "$(rand)"
  admin-password: "$(rand)"
  writer-password: "$(rand)"
  reader-password: "$(rand)"
  mlflow-password: "$(rand)"
EOF

create aiops-pseudonym <<EOF
  key: "$(openssl rand -hex 32)"
EOF

create aiops-grafana <<EOF
  admin-password: "$(rand)"
EOF

# The MLflow sign-in: the password in plain text, so it can be handed to reviewers, and its bcrypt hash
# for nginx.
mlflow_password="$(rand)"
mlflow_htpasswd="$(printf '%s' "$mlflow_password" | htpasswd -niB -C 10 "$MLFLOW_USER" | head -n 1)"
create aiops-mlflow-auth <<EOF
  username: "$MLFLOW_USER"
  password: "$mlflow_password"
  htpasswd: '$mlflow_htpasswd'
EOF
unset mlflow_password mlflow_htpasswd

cat <<EOF

Read a sign-in when you need it (prints to your terminal only):
  oc extract secret/aiops-grafana --keys=admin-password --to=-          # Grafana user: admin
  oc extract secret/aiops-mlflow-auth --keys=username,password --to=-   # MLflow
EOF
