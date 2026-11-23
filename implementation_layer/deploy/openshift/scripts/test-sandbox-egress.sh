#!/usr/bin/env bash
# Checks networkpolicy-sandbox.yaml against a local Kubernetes cluster.
#
#   KUBE_CONTEXT=colima-k8s ./test-sandbox-egress.sh [--keep]
#
# Creates a throwaway namespace with stand-ins for this stack's api and
# database and for a second stack's api, applies the policy as deploy.sh
# renders it, and probes from a pod that carries the labels of a rendered
# sandbox Job. Every check must pass; removing the policy makes the denied ones
# succeed, so the result depends on the policy and not on the stand-ins.
#
# The context is required and must not be a shared cluster: the script creates
# and deletes a namespace.
set -euo pipefail

CTX="${KUBE_CONTEXT:?set KUBE_CONTEXT to a local cluster, e.g. colima-k8s}"
NS="${NAMESPACE:-wizard-egress-test}"
HERE="$(cd "$(dirname "$0")/.." && pwd)"
STANDIN=busybox:1.36
PROBE=curlimages/curl:8.11.1

k() { kubectl --context "$CTX" -n "$NS" "$@"; }

# The run pod's labels, taken from the rendered Job rather than repeated here.
labels="$(DRY_RUN=1 INSTANCE= "$HERE/scripts/submit-sandbox-job.sh" egress-test-session "$PROBE" |
  sed -n '/^  template:/,/^    spec:/p' | grep -E '^        [a-z]' | sed -e 's/^ *//' -e 's/: /=/' | paste -sd, -)"
case "$labels" in *wizard-v2/instance=wizard-v2*) ;; *) echo "could not read the run labels: $labels" >&2; exit 1 ;; esac

kubectl --context "$CTX" create namespace "$NS" >/dev/null
kubectl --context "$CTX" label namespace "$NS" pod-security.kubernetes.io/enforce=restricted >/dev/null
KEEP="${1:-}"
trap '[ "$KEEP" = "--keep" ] || kubectl --context "$CTX" delete namespace "$NS" --wait=false >/dev/null' EXIT

standin() {  # standin <name> <port>
  k apply -f - >/dev/null <<EOF
apiVersion: apps/v1
kind: Deployment
metadata: {name: $1}
spec:
  replicas: 1
  selector: {matchLabels: {app: $1}}
  template:
    metadata: {labels: {app: $1}}
    spec:
      automountServiceAccountToken: false
      securityContext: {runAsNonRoot: true, runAsUser: 10001, seccompProfile: {type: RuntimeDefault}}
      containers:
        - name: web
          image: $STANDIN
          # Listens on the real port: a policy matches the pod port, not the Service port.
          command: [httpd, -f, -p, "$2", -h, /tmp]
          securityContext: {allowPrivilegeEscalation: false, capabilities: {drop: [ALL]}}
---
apiVersion: v1
kind: Service
metadata: {name: $1}
spec:
  selector: {app: $1}
  ports: [{port: $2, targetPort: $2}]
EOF
}
standin wizard-v2-api 8100
standin wizard-v2-db 5432
standin wizard-v2-s4-api 8100

PROJECT=test INSTANCE= bash "$HERE/deploy.sh" render networkpolicy-sandbox.yaml | k apply -f - >/dev/null

k run probe --image="$PROBE" --labels="$labels" --restart=Never --command \
  --overrides='{"spec":{"automountServiceAccountToken":false,"securityContext":{"runAsNonRoot":true,"runAsUser":10001,"seccompProfile":{"type":"RuntimeDefault"}},"containers":[{"name":"probe","image":"'"$PROBE"'","command":["sleep","600"],"securityContext":{"allowPrivilegeEscalation":false,"readOnlyRootFilesystem":true,"capabilities":{"drop":["ALL"]}}}]}}' \
  -- sleep 600 >/dev/null
k rollout status deploy/wizard-v2-api deploy/wizard-v2-db deploy/wizard-v2-s4-api --timeout=120s >/dev/null
k wait --for=condition=Ready pod/probe --timeout=120s >/dev/null

fail=0
# The network plugin programs the rules for a new pod a few seconds after it is
# Ready, so each check is retried until it settles.
expect() {  # expect <allow|deny> <description> <url>
  for _ in 1 2 3 4 5; do
    if k exec probe -- curl -s -o /dev/null --connect-timeout 4 --max-time 8 "$3" 2>/dev/null; then got=allow; else got=deny; fi
    [ "$got" = "$1" ] && break
    sleep 2
  done
  if [ "$got" = "$1" ]; then echo "ok    $1  $2"; else echo "FAIL  expected $1, got $got: $2"; fail=1; fi
}

expect allow "this stack's api (DNS + 8100)"   "http://wizard-v2-api:8100/"
expect deny  "this stack's database"            "http://wizard-v2-db:5432/"
expect deny  "the other stack's api"            "http://wizard-v2-s4-api:8100/"
expect deny  "Kubernetes API server"            "https://kubernetes.default.svc.cluster.local/"
expect deny  "cloud metadata address"           "http://169.254.169.254/"
expect deny  "public HTTP (port 80)"            "http://example.com/"
expect allow "public HTTPS (port 443)"          "https://example.com/"

exit $fail
