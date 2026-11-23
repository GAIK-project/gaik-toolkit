#!/bin/sh
# Applies the sandbox egress baseline to the local k3s cluster and checks allowed and denied connections.
# Usage: test.sh [--keep]   (default removes the test namespaces afterwards)
set -u
here=$(dirname "$0")
ctx=${KUBE_CONTEXT:-colima-k8s}
k() { kubectl --context "$ctx" "$@"; }

k apply -f "$here/00-namespaces.yaml" -f "$here/10-app-fixture.yaml" \
  -f "$here/20-sandbox-policies.yaml" -f "$here/30-app-policies.yaml" -f "$here/40-probe.yaml" >/dev/null || exit 1
k -n gaik-app rollout status deploy/api deploy/db --timeout=120s >/dev/null || exit 1
k -n gaik-sandbox wait --for=condition=Ready pod/probe --timeout=120s >/dev/null || exit 1

fail=0
# expect <allow|deny> <description> <url>
expect() {
  if k -n gaik-sandbox exec probe -- curl -s -o /dev/null --connect-timeout 4 --max-time 8 "$3" 2>/dev/null; then got=allow; else got=deny; fi
  if [ "$got" = "$1" ]; then echo "ok    $1  $2"; else echo "FAIL  expected $1, got $got: $2"; fail=1; fi
}

expect allow "API service in the app namespace (DNS + port 8080)" http://api.gaik-app.svc.cluster.local:8080/
expect deny  "database service in the app namespace"              http://db.gaik-app.svc.cluster.local:8080/
expect deny  "Kubernetes API server"                              https://kubernetes.default.svc.cluster.local/
expect deny  "cloud metadata address"                             http://169.254.169.254/
expect deny  "public HTTP (port 80)"                              http://example.com/
expect allow "public HTTPS (port 443)"                            https://example.com/

# A pod in another namespace must not reach the API either (only the sandbox namespace is allowed in).
if k run netcheck --rm -i --restart=Never -n default --image=curlimages/curl:8.11.1 --quiet \
     --overrides='{"spec":{"securityContext":{"runAsNonRoot":true,"runAsUser":10001,"seccompProfile":{"type":"RuntimeDefault"}},"containers":[{"name":"netcheck","image":"curlimages/curl:8.11.1","args":["-s","-o","/dev/null","--connect-timeout","4","http://api.gaik-app.svc.cluster.local:8080/"],"securityContext":{"allowPrivilegeEscalation":false,"capabilities":{"drop":["ALL"]}}}]}}' \
     >/dev/null 2>&1; then
  echo "FAIL  expected deny, got allow: API from another namespace"; fail=1
else
  echo "ok    deny   API from another namespace"
fi

[ "${1:-}" = "--keep" ] || k delete namespace gaik-sandbox gaik-app --wait=false >/dev/null
exit $fail
