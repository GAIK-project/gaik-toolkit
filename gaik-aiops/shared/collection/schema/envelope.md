# Event envelope (DRAFT)

Status: draft for the joint schema agreement in weeks 1–2. This file covers only the transport, storage,
retention and privacy side. The content of LLM call and evaluation events is defined by the WP5
instrumentation owner and is not part of this draft.

Events are OpenTelemetry log records sent over OTLP (gRPC 4317 or HTTP 4318). Standard OpenTelemetry
semantic convention names are used where they exist; `gaik.*` is used for the rest.

## Common envelope

| Attribute | Where | Required | Meaning |
|---|---|---|---|
| `service.name` | resource | yes | Producing service or component |
| `traceId` / `spanId` | log record | when available | W3C trace context; the correlation key across all stores |
| `timeUnixNano` | log record | yes | When the event happened (receive time is used if missing) |
| `gaik.event.class` | attribute | yes | `audit`, `log`, or a class owned by another schema (e.g. `llm_call`, `evaluation`) |
| `event.name` | attribute | audit: yes | Dotted event name, e.g. `auth.login` |
| `enduser.id` | attribute | no | Raw user identity. **Never stored**: replaced by `enduser.pseudo.id` at the collector |
| `client.address` | attribute | no | Client IP. Masked at the collector (IPv4 /24, IPv6 /48) |

Retention is derived from the class: `audit` uses the audit retention period, everything else the log
retention period. The periods are configuration, and their values are a customer decision
(defaults 365 and 30 days are placeholders).

## Audit events (WP4 S4)

| Attribute | Required | Meaning |
|---|---|---|
| `event.name` | yes | What happened; an audit event without a name is rejected |
| `gaik.audit.outcome` | recommended | `success`, `denied` or `error` |
| `gaik.audit.resource.type` / `.id` | no | What was acted on |

Producers must not put secrets, tokens, cookies, message content or document bodies in any attribute.
Collector processing is a backstop, not the primary control.

## Storage guarantees

- Audit events are append-only: updates and truncation are refused, and a row can be deleted only after
  its retention period (`collection.purge_expired()`).
- The writing role can only insert; reading is a separate role.
- `collection.correlated_events` gives one timeline per trace across audit and log events.

## Open points for the joint agreement

- Name of the class attribute and the list of classes
- Run and configuration identifiers (owned by the WP5 instrumentation side)
- Privacy class per attribute, and whether body content is allowed per class
- Pseudonymisation method: keyed SHA-256 in the collector, before any destination, for logs and spans;
  the key from `PSEUDONYM_KEY` by default, from the vault with the OpenBao overlay (WP4 S3,
  `wp4/secrets/`)
