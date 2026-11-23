#!/bin/sh
# Deploys the stack to the local k3s cluster with an OpenShift-like arbitrary UID, checks the network
# policies, and runs the stack tests against it through port-forwards.
# Usage: test.sh [--keep]   (default deletes the namespaces afterwards)
# The compose stack must be stopped first: the port-forwards use the same local ports.
set -u
here=$(cd "$(dirname "$0")" && pwd)
root=$(cd "$here/../../.." && pwd)
ctx=${KUBE_CONTEXT:-colima-k8s}
k() { kubectl --context "$ctx" "$@"; }
fail=0

echo "== images (built inside the k3s VM)"
docker --context "$ctx" build -q -t gaik-aiops/collection-sink:local "$root/shared/collection/sink" >/dev/null || exit 1
docker --context "$ctx" build -q -t gaik-aiops/mlflow:local "$root/deploy/compose/mlflow" >/dev/null || exit 1

echo "== apply"
kubectl kustomize --load-restrictor LoadRestrictionsNone "$here/overlays/local" | k apply -f - >/dev/null || exit 1
k apply -f "$here/overlays/local/test-namespaces.yaml" >/dev/null || exit 1
k -n gaik-aiops rollout status statefulset/postgres --timeout=300s >/dev/null || exit 1
for d in sink mlflow otel-collector prometheus alertmanager grafana grafana-setup; do
  k -n gaik-aiops rollout status "deploy/$d" --timeout=300s >/dev/null || { echo "FAIL  $d did not become ready"; exit 1; }
done
echo "ok    all workloads ready as UID $(k -n gaik-aiops get pod postgres-0 -o jsonpath='{.spec.securityContext.runAsUser}')"

echo "== network policies"
# New pods reach the policy rules a few seconds after they start, hence the sleep.
probe() {  # namespace url expected
  code=$(k -n "$1" run "np-$(date +%s)-$$" --rm -i --restart=Never --image=curlimages/curl:8.11.1 \
    --image-pull-policy=IfNotPresent --quiet --command -- \
    sh -c "sleep 10; curl -s -o /dev/null -m 5 -w '%{http_code}' $2" 2>/dev/null | head -c 3)
  if { [ "$3" = allow ] && [ "$code" != 000 ]; } || { [ "$3" = deny ] && [ "$code" = 000 ]; }; then
    echo "ok    $3  $1 -> ${2##*//}"
  else
    echo "FAIL  expected $3, got ${code:-nothing}: $1 -> ${2##*//}"; fail=1
  fi
}
otlp="-X POST -H 'Content-Type: application/json' -d '{}' http://otel-collector.gaik-aiops.svc:4318/v1/traces"
probe aiops-producer-test "$otlp" allow
probe aiops-producer-test "http://mlflow.gaik-aiops.svc:5000/health" deny
probe aiops-producer-test "http://sink.gaik-aiops.svc:4319/healthz" deny
probe aiops-outsider-test "$otlp" deny
probe gaik-aiops "http://sink:4319/healthz" allow

echo "== stack tests through port-forwards"
pids=""
for m in postgres:55432:5432 otel-collector:4318:4318 mlflow:5000:5000 prometheus:9090:9090 \
         alertmanager:9093:9093 grafana:3000:3000; do
  svc=${m%%:*}; ports=${m#*:}
  k -n gaik-aiops port-forward "svc/$svc" "$ports" >/dev/null 2>&1 &
  pids="$pids $!"
done
for url in http://127.0.0.1:5000/health http://127.0.0.1:3000/api/health http://127.0.0.1:9090/-/ready; do
  i=0; until curl -sf -o /dev/null "$url"; do i=$((i+1)); [ "$i" -gt 30 ] && break; sleep 2; done
done
out=$(mktemp)
if (cd "$root/shared/collection/sink" && uv run --quiet --python 3.12 --extra dev pytest -q -rs) >"$out" 2>&1; then
  if grep -q SKIPPED "$out"; then cat "$out"; echo "FAIL  stack tests were skipped"; fail=1; else echo "ok    $(tail -1 "$out")"; fi
else
  cat "$out"; echo "FAIL  stack tests"; fail=1
fi
rm -f "$out"
kill $pids 2>/dev/null

if [ "${1:-}" != --keep ]; then
  k delete -f "$here/overlays/local/test-namespaces.yaml" --wait=false >/dev/null
  k delete namespace gaik-aiops --wait=false >/dev/null
fi
[ "$fail" = 0 ] && echo "all checks passed" || echo "some checks failed"
exit "$fail"
