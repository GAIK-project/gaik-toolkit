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

current="$(oc project -q)"
if [ "$current" != "$NAMESPACE" ]; then
  echo "oc is on project '$current', not '$NAMESPACE'. Run: oc project $NAMESPACE" >&2
  exit 1
fi

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

# The bearer token for the OTLP way in from other projects (otlp-ingress.yaml). The producer's own
# project gets the same value in a Secret of its own (README.md, "The wizard's way in").
printf '  token: "%s"\n' "$(openssl rand -hex 32)" | create aiops-otlp-ingress

# Sign-in for people goes through the GAIK Keycloak: its deploy.sh add-client makes the Secrets
# aiops-grafana-signin and aiops-mlflow-signin here (README.md, Signing in).
for s in aiops-grafana-signin aiops-mlflow-signin; do
  oc get secret "$s" -n "$NAMESPACE" >/dev/null 2>&1 || echo "missing $s: register the client in Keycloak (README.md)"
done

echo
echo "Grafana's local admin, for grafana-setup's API calls; read it in your own terminal:"
echo "  oc extract secret/aiops-grafana --keys=admin-password --to=-          # Grafana user: admin"
echo "The sign-in page has no form for it; README.md (Signing in) says how to get in when Keycloak is down."
