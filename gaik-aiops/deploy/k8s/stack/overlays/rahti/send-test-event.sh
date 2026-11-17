#!/usr/bin/env bash
# Sends one test event through the collector: a trace (a run span with one LLM-call span) and an audit
# log record on the same trace. Both carry a user id, a client IP, and the LLM call carries prompt and
# response text. The collector must pseudonymise the user id, mask the IP and drop the text before
# anything is stored. Prints the trace id to look up in MLflow and Grafana (README.md, "Test event").
#
#   oc port-forward -n gaik-aiops svc/otel-collector 4318:4318     # in a second terminal
#   deploy/k8s/stack/overlays/rahti/send-test-event.sh
#
# OTLP_ENDPOINT (default http://127.0.0.1:4318) and, for a protected endpoint, OTLP_TOKEN.
set -euo pipefail

ENDPOINT="${OTLP_ENDPOINT:-http://127.0.0.1:4318}"
TRACE_ID="$(openssl rand -hex 16)"
RUN_SPAN="$(openssl rand -hex 8)"
CALL_SPAN="$(openssl rand -hex 8)"
NOW="$(date +%s)"
T0="${NOW}000000000"
T1="$((NOW + 1))000000000"
USER_ID="test-user@example.com"
CLIENT_IP="192.0.2.123"   # a documentation address (RFC 5737), never a real client

post() { # path, JSON on stdin. The token goes to curl as a header file, never on its command line.
  if [ -n "${OTLP_TOKEN:-}" ]; then
    curl -fsS -o /dev/null -X POST -H "Content-Type: application/json" \
      -H @<(printf 'Authorization: Bearer %s\n' "$OTLP_TOKEN") --data-binary @- "$ENDPOINT$1"
  else
    curl -fsS -o /dev/null -X POST -H "Content-Type: application/json" --data-binary @- "$ENDPOINT$1"
  fi
}

str() { printf '{"key":"%s","value":{"stringValue":"%s"}}' "$1" "$2"; }
int() { printf '{"key":"%s","value":{"intValue":"%s"}}' "$1" "$2"; }

RESOURCE="{\"attributes\":[$(str service.name aiops-test-event)]}"

post /v1/traces <<EOF
{"resourceSpans":[{"resource":$RESOURCE,"scopeSpans":[{"scope":{"name":"gaik.test-event"},"spans":[
 {"traceId":"$TRACE_ID","spanId":"$RUN_SPAN","name":"test-event.run","kind":1,
  "startTimeUnixNano":"$T0","endTimeUnixNano":"$T1",
  "attributes":[$(str enduser.id "$USER_ID"),$(str client.address "$CLIENT_IP"),$(str gaik.session.id test-session-1)]},
 {"traceId":"$TRACE_ID","spanId":"$CALL_SPAN","parentSpanId":"$RUN_SPAN","name":"chat test-model","kind":3,
  "startTimeUnixNano":"$T0","endTimeUnixNano":"$T1",
  "attributes":[$(str gaik.event.class llm_call),$(str gen_ai.operation.name chat),
   $(str gen_ai.request.model test-model),$(int gen_ai.usage.input_tokens 12),$(int gen_ai.usage.output_tokens 5),
   $(str enduser.id "$USER_ID"),$(str client.address "$CLIENT_IP"),
   $(str gen_ai.input.messages "TEST PROMPT - must not be stored"),
   $(str gen_ai.output.messages "TEST RESPONSE - must not be stored")]}
]}]}]}
EOF

post /v1/logs <<EOF
{"resourceLogs":[{"resource":$RESOURCE,"scopeLogs":[{"scope":{"name":"gaik.test-event"},"logRecords":[
 {"timeUnixNano":"$T0","severityNumber":9,"severityText":"INFO","traceId":"$TRACE_ID","spanId":"$RUN_SPAN",
  "body":{"stringValue":"aiops test event"},
  "attributes":[$(str gaik.event.class audit),$(str event.name aiops.test_event),$(str gaik.audit.outcome success),
   $(str enduser.id "$USER_ID"),$(str client.address "$CLIENT_IP")]}
]}]}]}
EOF

cat <<EOF
Sent to $ENDPOINT
trace id: $TRACE_ID

Expect, in MLflow (Default experiment, Traces) and in Grafana (Security org, Audit trail):
  enduser.pseudo.id / actor  a 64-character hash, and no enduser.id
  client.address             192.0.2.0
  gen_ai.input/output        absent from the LLM-call span
EOF
