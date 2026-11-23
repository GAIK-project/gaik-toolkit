# WP4 / WP5 preparatory work

Preparatory work on two GAIK work packages, kept in its own top-level directory of the toolkit
repository:

- **WP4 Security & compliance**: security baseline for the GAIK toolkit (authentication, RBAC, secrets,
  audit logging, data handling, hardening, guidance and compliance framework, baseline testing).
- **WP5 AI Ops, Expert 1 scope only**: the technical foundation for monitoring, logging and observability
  (central logging, metrics, dashboards, alerts, connecting systems to the monitoring infrastructure).

Commands in this directory's documents are run from `gaik-aiops/` unless they say otherwise. Its CI is
`.github/workflows/aiops.yml` at the repository root.

## Ground rules

1. **Separate from applications.** Nothing in this directory depends on an application's code, and
   application work is not done here.
2. **Written to be published.** This directory is public: English only,
   no personal names, no internal paths, no customer text, no credentials, no tool attribution lines.
   The hooks in `.githooks/` check commit messages and staged files for these
   (`git config core.hooksPath gaik-aiops/.githooks` to use them).
3. **Technology-neutral until the customer decides.** The customer makes the final technology choices and
   approves the architecture. Prefer open standards (OIDC, OAuth2, OpenTelemetry, Kubernetes
   NetworkPolicy).
4. **Stay inside our scope.** See the boundary below.
5. **No deployments to shared environments.** Test locally with Docker Compose or a local k3s cluster.
   The customer's existing cloud project is not used for this work.

## Scope boundary

| Area | Here | Not here (WP5 Expert 2) |
|---|---|---|
| WP4 S1–S6, O1, T1, S7 | Everything | – |
| Collection, storage and correlation layer (shared by the WP4 audit log and WP5 central logging) | Yes | – |
| Central logging deployment (compose, Kubernetes) | Yes | – |
| Metrics pipeline: usage, latency, errors, cost (transport and storage) | Yes | LLM-specific metric definitions |
| Dashboard platform and alerting | Yes | Content of evaluation and comparison views |
| Event schema | Transport, storage, retention side, marked **draft** | LLM and evaluation content; schema is agreed jointly in weeks 1–2 |
| Configuration layer (shared with WP4 secrets) | Infrastructure side | Configuration version tracking (which component, provider, model, setting per run) |
| Instrumentation hooks in GAIK components | Review only | Yes |
| Evaluation workflows, regression runs, qualitative review | Runtime environment (CI / Job) only | Yes |
| Configuration variant comparison | – | Yes |

## Layout

```
wp4/                 WP4 security baseline: sign-in, roles, secrets
wp5-a1/              WP5 Expert 1: logging, metrics, dashboards, alerting
shared/collection/   Collection, storage and correlation layer used by both
deploy/compose/      Local Docker Compose stack
deploy/k8s/          Local Kubernetes (k3s) manifests and instructions
```

## Running locally

Docker Compose (Colima):

```bash
docker compose -f deploy/compose/docker-compose.yml up -d
```

Sending traces from your own code: see `wp5-a1/quickstart-producers.md`.

Local Kubernetes for NetworkPolicy, Job and RBAC work: see `deploy/k8s/README.md`.
