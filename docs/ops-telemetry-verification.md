# Demo operational telemetry verification (2026-09-28)

Source change on main: `7d09468`. Deployment branch: `deploy/demo-app` at `32878cf`
(the telemetry change cherry-picked onto the existing production base, plus an exact
`gaik==0.8.0` pin to retain the already certified production library). Other pending
main-branch demo changes were not part of this rollout. No library API, published
package or customer application was changed.

The applicable demo API suite passed on both main and the deployment base. The
final deployment base passed all 96 API tests, including 12 optional-telemetry tests.
These verify disabled behavior without either setting, failed delivery, bounded
attempts/concurrency, unchanged streaming, error handling, metadata filtering and
the LLM Judge usage adapter. Ruff passed for the changed Python files.

Builds `gaik-demo-api-git-9` and `gaik-demo-git-8` completed and both deployments
rolled out. Live deployment environment values were preserved; deployment manifests
were not applied. The API image is
`sha256:5da8bab76b9f8ca6d14fb5eeb0357ea84fdc4e7790871e2c2092550c488fcd3e`.
The frontend image is
`sha256:523e3fb44d6c46b7cef94d7ce8211457b424760eeba17b594428856c9e6eadb9`.
API rollback image:
`sha256:50f3cc7733a300b23a6a9f81a7d7a89f712f162b891fa6b6b77b61e198331051`.

A real synthetic `/llm-judge/text-pair` request returned HTTP 200 and correctly judged
two equivalent short sentences. Reported model: `gpt-6-luna`; input tokens: 393;
output tokens: 57. GAIK Ops received one LLM event and one operation log with the
same trace ID and two spans. Only metadata was inspected in the event store.
The ready API pod had zero restarts and confirmed gaik 0.8.0 with reporting enabled.

This adds model accounting only where the demo exposes actual usage records (the
LLM Judge endpoints). Other demo operations report request traces and server failures.
Reporting remains optional and is deliberately best effort, including event loss
under load or at process shutdown. See the demo README for limits and configuration.
