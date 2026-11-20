# Wizard API (S1-1 + S1-3 + S1-2 + S1-12)

FastAPI service for Solution Wizard V2 session persistence.

**Issues:** #5 S1-1 · #7 S1-3 · #6 S1-2 · #8 S1-12 · #9 S1-5 · #10 UI wire · #11 tests

## Quick start — Docker Compose (Sprint 1 demo)

```bash
cd implementation_layer/wizard_api
export NEXT_SERVER_ACTIONS_ENCRYPTION_KEY=dev-compose-encryption-key-32chars!!
docker compose up --build
```

| Service | URL |
|---------|-----|
| UI | http://localhost:3000 |
| API | http://localhost:8100/health |
| Postgres | localhost:5432 (`wizard` / `wizard`) |

Set `NEXT_PUBLIC_DEV_AUTH=true` in the UI container for dev login (`dev@gaik.local`).

## Local API only (without Docker UI)

```bash
cd implementation_layer/wizard_api
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
docker compose up -d postgres   # or use existing Postgres
alembic upgrade head
uvicorn wizard_api.main:app --reload --port 8100
```

Wire the UI:

```bash
# solution_wizard_v2/.env.local
WIZARD_API_URL=http://localhost:8100
NEXT_PUBLIC_DEV_AUTH=true
```

## Session API

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/sessions` | Create (`user_id`, optional `title`, `metadata`) — seeds blueprint v1 |
| `GET` | `/sessions?user_id=` | List sessions |
| `GET` | `/sessions/{id}` | Full session detail (blueprint, versions, messages) |
| `PATCH` | `/sessions/{id}` | Update `step`, `gate_statuses`, `metadata` |
| `POST` | `/sessions/{id}/messages` | Append chat messages (Sprint 1 stub) |
| `POST` | `/sessions/{id}/versions` | New blueprint version |
| `GET` | `/sessions/{id}/poc/file?path=` | One file of the package as UTF-8 text (up to 256 KB), with the digest a save names |
| `PUT` | `/sessions/{id}/poc/file?path=` | Save `{content, base_digest}` over that file |

Steps are **1–13** (matches V2 UI phase stepper). Gate keys: `gate_1` … `gate_4`.

### One package file (the PoC tab's editor)

`path` is relative to the session's `poc/`. Only the session's own regular files are
read or written: no absolute path, no `..`, no backslash, no symlink on the way
(`poc_service.package_file_path`, `regular_file`). A save needs an existing file with
one of the suffixes in `poc_service.EDITABLE_SUFFIXES` (or `.env.example`); the AI
marker, everything under `sample_input/` and `output/`, files in a hidden folder or
`__pycache__`, and the package's test page (`app.py` at the root and everything under
`ui/`, the scaffolder's templates) are read-only (`file_read_only`, 403), other types
`file_type_not_editable` (422). The package's code (every `.py` file and
`requirements.txt`) and `config.yaml`, which names the model endpoints a run calls
(`poc_service.is_package_code`), are saved only when the test runs use
a runner key of their own (`WIZARD_POC_RUNNER_SECRET` names a Secret other than the
shared `gaik-demo-api-keys`, `sandbox_runner.runs_use_shared_key`): user-written code
runs only with a separate runner key. With the shared key those files are read-only
with `read_only_reason` `code_edit_needs_own_runner_key` and a save answers 403 with that
code; the prompts, the schema's JSON files, `.env.example` and the package's other
files stay editable. `.env` and every `.env*` name except `.env.example` is
refused for reading and writing with 422 `secrets_not_stored`: the server keeps no keys
for a user, the web app adds `poc/.env` to the downloaded package in the browser. For
the same reason a save of `.env.example` that gives a credential a value answers 422
`key_value_not_stored` with the `variables` it names (rule below). A save whose
`base_digest` is not the file's answers 409 `file_changed`, and one sent while the
wizard is replying 409 `wizard_responding`.

A save and the start of a chat turn exclude each other (`agent_service.editor_save`, a
lock per session): the save checks for a running turn and records the edit under the
lock, and a turn registered meanwhile waits for it before it reads the edits it tells
the agent of, so the agent never writes over an edit it has not heard of. A turn that
waits more than 30 seconds answers 409 `file_being_saved`.

A saved edit is a package change like one of the agent's. The package digest
(`package_digest` in `GET /poc/files`) covers every file of the package but its README
files, so an edit to any other file (code, settings, prompts, `.env.example`, a data
file such as a `labels.json` the run reads) makes the earlier run a run of another
package, closes `/poc/deployable` until a new run has passed, and where Gate 3 was
approved it reopens that gate. An edit to a `README.md` (outside `prompts/`) does
neither: no run reads it, while the prompts are Markdown too and a run reads them.

The digest (`poc_service._version_files`, `_in_version`; scheme 3) covers every file of
`poc/` but README files, the test page's `ui/` folder (the page runs where the package
is taken; no sandbox run reads it), the AI marker, the wizard's own records,
environment files with keys, the editor's temporary files, compiled Python,
`sample_input/`, `output/`, hidden folders and `__pycache__`. It is the preflight's version too, so the PoC tab
checks the package again after any such change. Scheme 2 covered Python files,
`schemas/` and `prompts/` only; a session approved under it is re-based on the package
as it is, and a run recorded under it is asked for again before Gate 3 or the
download. The editor says by a file's name whether saving it changes the digest
(`counts_for_package_digest`, held to the digest by a test). Before a save the approved
content is compared once, so that an approval recorded under an older digest scheme is
re-based on the package as it was before the edit, not after it.

`.env.example` lists the variables a package needs, without values. A save is refused
when a credential has a value there, also on a commented-out line: a variable whose
name has a part (between underscores) ending in `KEY`, `SECRET`, `TOKEN` or `PASSWORD`
(`AZURE_API_KEY`, `HF_TOKEN`, `OPENAI_APIKEY`; not `MAX_TOKENS`), or
`GOOGLE_SERVICE_ACCOUNT_JSON`. Empty, `<…>`, a value starting with `your`
(`your-key-here`) and `xxxx`-style values are placeholders and stay allowed, and other
variables keep their example values (`poc_service.env_example_key_values`; the web app
applies the same rule before it sends the text, `lib/env-file.ts`).

Environment files that would hold keys (`.env` in any spelling but `.env.example`) are
left out of the package's listing and of both zips (`poc_service.package_files`), and
so never reach the sandbox either. The session export still carries every file held. Each save is recorded in the session's metadata
(`user_edits`, server-owned) and the agent is told once, with the next chat message.

`GET /sessions/{id}/poc/deployable` hands the package over only when the run recorded as
successful tested it as it is now: the digest kept with that run against the package's
digest, the comparison Gate 3 makes. After a change to a file in the digest it answers
409 `package_changed_since_run` until a new run has succeeded. Once Gate 3 is approved
the approval holds the package instead (a change reopens the gate and takes the run
away), so a run recorded under an older digest scheme does not lock an approved
session's download.

### Errors

Every error answers in one shape (`wizard_api/errors.py`):

```json
{"detail": {"error": "sandbox_busy", "message": "the sandbox is busy: 3 runs are going; try again in a minute", "trace_id": "…"}}
```

`error` is a stable code the web branches on (`gate_not_ready`, `sandbox_busy`,
`poc_package_incomplete`, …), `message` is a short line for the person, and any
extra keys (`gate`, `missing`, `problems`) are what they need to act. `trace_id`
is the caller's `x-trace-id` (or a fresh one), echoed as a response header. A
failure's cause (an exception's text, a path, a traceback, a Kubernetes message)
is logged under that trace id and never put in the answer. SSE streams report an
error as `{"error": true, "code": "...", "message": "...", "trace_id": "..."}`.
The web relays pass on only the codes listed in `solution_wizard_v2/lib/safe-error.ts`;
anything else becomes a generic message carrying the trace id.

## Service authentication (#132)

Every endpoint except `/health` requires the shared secret
`WIZARD_API_TOKEN`, presented as an `X-Wizard-Service-Token` header. The web
app's server-side proxy is the only legitimate caller and sends it
automatically.

| `WIZARD_API_TOKEN` | Behaviour |
|--------------------|-----------|
| unset / whitespace | Auth **off**. Any caller is accepted. Startup logs a warning. Intended for local dev and the docker stack. |
| set | Requests without a matching header get `401`. `/health` stays open for liveness/readiness probes. |

Set it to the **same value** on both the web and the api pod:

```bash
oc set env deploy/wizard-v2-api WIZARD_API_TOKEN=<secret> -n gaik
oc set env deploy/wizard-v2-web WIZARD_API_TOKEN=<secret> -n gaik
```

**This is inert until that env var exists.** Shipping the code alone changes
nothing — an unset token means the API stays open exactly as before.

What this does *not* do: `user_id` is still self-asserted, so a caller holding
the token can act as any user. Real per-user authentication is #134.

### The wizard agent never sees the API's secrets

The chat endpoint spawns the V1 wizard agent (Claude Agent SDK) from this
process, and the SDK merges its `env` option *over* the inherited environment
rather than replacing it. The agent has a Bash tool, so anything left in the
environment is one `env` away from a prompt injection — and with the service
token the agent could call this API as any user. `config.py` therefore reads
`WIZARD_API_TOKEN` and `WIZARD_DATABASE_URL` once, at import, and removes them
from the process environment; the agent, its Bash tool and the V1 scripts it
runs never inherit them. Provider variables the scripts need (Foundry, Azure,
OpenAI) are left untouched.

This is defence in depth, not isolation: a same-UID process can still read the
initial environment through `/proc/<pid>/environ`. Real isolation means running
the agent in its own pod, or restricting its Bash tool.
## Who a call acts for (#134)

Every call the web app makes carries `X-Wizard-User-Id`, the signed-in user.
A `/sessions/{id}/...` route is served only when that session belongs to the
named user; another user's session answers `404`, the same as a session that
does not exist. `GET /sessions?user_id=` and `POST /sessions` must name the
same user as the header (`403` otherwise). This is a router-level dependency
(`wizard_api/ownership.py`), so a route added later is covered without
remembering anything.

| `WIZARD_REQUIRE_USER_HEADER` | Behaviour |
|---|---|
| unset | A call **without** the header is served (the sandbox Job's init container and the stack E2E helpers still call with the token alone). Ownership is enforced whenever the header is present. |
| `1` | A call without the header gets `400`. Set it once every caller sends the header (#203 / B3). |

The user is named by an owner id, `o_` + 32 hex characters, not by the e-mail
address: the web app computes it (`solution_wizard_v2/lib/owner-id.ts`), so the
session rows, the session folders and the sandbox Jobs never hold the address.
Sessions made before owner ids are saved under the address; on a user's first
request the web app moves theirs with `POST /owners/claim`, and
`session_admin move-owners` moves the rest. The id is keyed with the web app's
`WIZARD_PSEUDONYM_KEY` (else `NEXT_SERVER_ACTIONS_ENCRYPTION_KEY`): changing
that key gives every user a new owner id and hides their sessions from them. A
session made before owner ids keeps its folder path until it is removed.

`output_dir` is no longer accepted on `POST /sessions`; the server derives it.
`PATCH /sessions/{id}` refuses the metadata keys the server records itself
(`messages`, `refinements`, `last_successful_run`) with `422
server_owned_metadata`, so a successful run cannot be forged into existence.

## Case limits

A case holds at most 20 input files and 200 MB. A session's cases share one
volume with every other session, so the session is bounded as a whole too:

| Variable | Default | Bounds |
|---|---|---|
| `WIZARD_MAX_CASES_PER_SESSION` | `100` | cases a session may open |
| `WIZARD_MAX_SESSION_INPUT_MB` | `1024` | input of all the session's cases together |

Size them to the sessions volume (5 GiB on Rahti). Both are checked under a
session-wide lock, so requests at the same time cannot pass them together.

## Agent and chat limits

Each live chat session holds a wizard agent (a CLI process) in the API pod, and
every chat message is a billed model call. Limits on them:

| Variable | Default | Bounds |
|---|---|---|
| `WIZARD_MAX_LIVE_AGENTS` | `20` | agent processes in this API process |
| `WIZARD_MAX_LIVE_AGENTS_PER_USER` | `2` | agent processes one user may hold |
| `WIZARD_MAX_CHAT_TURNS_PER_MINUTE` | `0` (off) | chat messages one user may send in a sliding minute |
| `WIZARD_MAX_CHAT_MESSAGE_CHARS` | `20000` | characters in one chat message |
| `WIZARD_AGENT_MAX_TURNS` | `100` | model calls the agent may make for one message |
| `WIZARD_MAX_METERED_CALLS_PER_TURN` | `10` | metered tool calls (below) the agent may make for one message |
| `WIZARD_MAX_METERED_CALLS_PER_USER_PER_HOUR` | `60` (`0` turns it off) | metered tool calls one user's agents may make in a sliding hour, across all their sessions |
| `WIZARD_AGENT_MAX_BUDGET_USD` | off (unset or `0`) | estimated USD one agent may spend from its start or resume (below) |
| `WIZARD_AGENT_FALLBACK_MODEL` | off (unset) | the model the agent switches to when its own fails or is unavailable |
| `WIZARD_POC_MODEL_TIMEOUT_SECONDS` | `120` | seconds a PoC waits for one model call in its extraction and judge stages, unless the package names its own limit |

A user is the session's owner (the user named in `X-Wizard-User-Id`).

- **At the global cap** the longest idle agent of any user is ended (it resumes
  from its transcript later). When every agent is mid-turn or was just handed to
  a request, `POST /sessions/{id}/chat` answers `503`.
- **At their own cap** a user's own longest idle agent is ended to make room for
  their new one. When all of their agents are mid-turn, just used or still
  starting, the chat answers `429` with `{"error": "agent_busy", "message": ...}`
  and `Retry-After: 30`. Another user's agent is never ended for them, so a
  second user still gets a slot while the first is at their cap.
- **Over the chat turn rate** the chat answers `429` with
  `{"error": "chat_rate_limited", "message": ...}` and a `Retry-After` of the
  seconds until the oldest counted message leaves the minute. It is checked
  before an agent is woken, and only accepted turns are counted (a `409` while
  the agent is still replying does not use one up).

**Metered tool calls.** `WIZARD_AGENT_MAX_TURNS` counts the agent's own model
calls, not the ones its tools make. The tool guard (`services/agent_tool_guard.py`)
counts every call that reaches a model or the web another way: a run of a wizard
script that calls a model itself (`generate_schema.py`, through gaik's
`SchemaGenerator`; no other script the agent may run does), `WebSearch`,
`WebFetch`, and the tools of any MCP server other than the wizard's own
`mcp__wizard__*`. The web tools and outside MCP servers are refused today; they
are counted by name, so they fall under both limits the moment they are allowed.
Only calls the guard lets run are counted, per message (with its quiet "Please
continue." nudges) and per user in a sliding hour. Over a limit the call is
refused with a message the agent passes on in plain words (it carries on without
the tool, or asks the user to wait or to send another message), a warning is
logged and `wizard.agent.tool_calls` counts it with reason `turn_limit` or
`user_limit`. One run of `generate_schema.py` is one metered call: the model
calls inside it (two for a flat schema, one more for each kind of repeated
record in a nested one, each tried at most four times) are bounded by gaik's own
code, which has no setting for them.

**Cost limit.** `WIZARD_AGENT_MAX_BUDGET_USD` is the agent SDK's `max_budget_usd`.
Its CLI counts the cost for the whole agent process, across messages, from its
start or its resume, not for one message: the wizard keeps one agent per session
for many messages, and the CLI has no way to start the count again per message.
The cost is the CLI's estimate from its own price table, not what the provider
bills (Foundry prices need not match), and it is checked between steps, so the
step that crosses the limit is still paid. When the agent reaches it, the CLI
stops the message; the chat says so in the session's language ("stopped because it
reached its cost limit … send a message and it goes on"), with no "Please
continue." after it. The agent is then ended: the next message resumes it from
its transcript with its context, and the count starts from zero there. A warning
is logged and `wizard.agent.budget_stops` counts it. It is off by default:
`WIZARD_AGENT_MAX_TURNS` and the metered-call limits already bound one message,
and a default would stop ordinary long sessions at whatever point their spend
reached it. Set it as a ceiling for a runaway agent, a few times what a whole
session costs (the `gaik.cost.usd` of the `wizard.turn` spans shows that).

**Usage caps.** Spend is capped per session, per user and per deployment month,
and the number of sessions per user, so one participant cannot use up what
others share (`services/usage_caps.py`). They are on by default; set one to `0`
to turn it off. A negative or unreadable value gives the default, not off.
Amounts are estimated USD, from the same CLI estimate as above,
not the provider's bill, which keeps its own cap as the hard limit.

| Variable | Default | What it limits |
|---|---|---|
| `WIZARD_SESSION_MAX_COST_USD` | `5.4` (about 5 €) | what one session may spend in all, across agent restarts |
| `WIZARD_USER_MAX_COST_USD` | `10.8` (about 10 €) | what one user may spend across all their sessions |
| `WIZARD_DEPLOYMENT_MAX_COST_USD` | `2000` | what the deployment may spend in one calendar month (UTC) |
| `WIZARD_MAX_SESSIONS_PER_USER` | `3` | sessions one user may have at a time |
| `WIZARD_COST_WARN_RATIO` | `0.8` | share of a session's or user's cap after which the chat says so, once; kept between 0 and 1, so `0` gives the default |

- After each chat turn its cost is added to the session (`metadata.usage_cost_usd`,
  which only the server writes), to the user's and to the month's row of
  `usage_totals`. Removing a session gives back its place, not its spend. The
  user's spend never resets; the month's starts again each calendar month. To
  start a user or the deployment again (between two events, say), delete their
  rows from `usage_totals`, by `scope` and `key`.
- Counting starts when revision 003 is applied: spend before it is not known,
  and the sessions users already have count against their limit.
- Before an agent is woken, a reached cap, or one that leaves less than
  `MIN_TURN_BUDGET_USD` (0.1), refuses the message with `402` and
  `{"error": "usage_cap", "scope": "session" | "user" | "deployment"}`. The agent
  is started with the smallest amount any cap has left as its `max_budget_usd`.
  That budget is held against the user's cap until the reply is charged, so
  replies in several sessions at once cannot each spend what is left; a message
  that finds the rest held by the user's running replies gets `429 agent_busy`
  (or `WIZARD_AGENT_MAX_BUDGET_USD`, if smaller), so a long reply stops at the
  cap; the chat then says the usage limit is reached, without "continue", and
  `wizard.agent.budget_stops` counts it with `limit=usage_cap`. An idle live agent
  started when the caps left more (the user spent in another session since) is
  ended first and resumed with the smaller budget, once it could pass them by more
  than about 1 USD (`FIT_BUDGET_MARGIN_USD`), so switching sessions does not
  restart it each time.
- A new session past `WIZARD_MAX_SESSIONS_PER_USER` is refused with `429`
  `session_limit`, claimed in one statement so two at once cannot both get the last place.
- Once a session or a user has used the warning share of its cap, a line is added
  to that reply, once, in the session's language; a turn that did not complete
  leaves it for the next one. The deployment's is logged as a
  warning. `wizard.usage.cost_usd` and `wizard.usage.warnings` count both.
- A query whose cost never arrives (the turn timed out, or the agent crashed or
  was ended mid-reply) is charged an estimate of 1 USD, or what its agent's
  budget had left if less (`telemetry.UNREPORTED_QUERY_COST_USD`), and counted
  in `wizard.usage.unreported_queries`.
- Gauges for the dashboards: `wizard.usage.cap_usd` (by `scope`),
  `wizard.usage.deployment_spent_usd` (this month) and `wizard.usage.users`
  (`state` near: past the warning share and below the cap; reached: at it).
  The "Hackathon live" Grafana view shows the month's
  spend of its cap and the users near or at theirs.
- Not counted: the model calls of PoC test runs in the sandbox and of
  `generate_schema.py`, which the run and metered-call limits bound.
- The values are read when a message or a session comes in, so a changed variable
  applies once the process has it (a restart, on Kubernetes and Azure).

**Fallback model.** With `WIZARD_AGENT_FALLBACK_MODEL` set to a model other than
the agent's own (see Model below), the SDK's `fallback_model` lets the CLI
switch to it when the agent's model is not found, not permitted, overloaded or
failing. The CLI reports the switch, and it is logged at `INFO` with both models
and the trigger. The deployment must offer that model (on Foundry, a deployment
of that name).

Every tool call the guard decides is one line on the logger
`wizard_api.services.agent_tool_guard`, for example
`tool call tool=Bash kind=model_script script=generate_schema.py decision=allowed reason=ok`:
the tool's name, its kind, the wizard script it runs, the decision and a reason
code, never the command, a path, an input, a URL or who the user is. Allowed
calls and refusals by the rules are `INFO`, refusals at a limit `WARNING`, a call
the guard could not decide `ERROR`. The pod prints them at `WIZARD_LOG_LEVEL`
(below).

The counts, metered calls included, live in the API process, as the agents do:
the API runs as one replica, and with more than one each would count its own. A
restart of the API starts them again from zero, so the hourly window of metered
calls and the chat turn minute begin anew with it.
The sandbox's run limits (`WIZARD_MAX_ACTIVE_RUNS`,
`WIZARD_MAX_ACTIVE_RUNS_PER_USER`, `429 sandbox_busy`) follow the same pattern.

### Stopping a reply

`POST /sessions/{id}/chat/stop` stops the reply that is being written for a
session of the caller. The agent is interrupted (`ClaudeSDKClient.interrupt()`),
the turn's stream ends with `{"stopped": true, "tool": <kind or null>}`, and
what was written so far is stored as the reply with `stopped: true` and a
short note at the end of its text (`stoppedNote`, "(Pysäytetty)"). It answers
`202 {"stopping": true}`, or `409 no_reply_running` when no reply is being
written. A stopped turn is counted as `stopped` in `wizard.turns`, not as
failed, and is not nudged to continue. The agent keeps its place and takes the
next message, which tells it in a server line that its previous reply was
stopped, and whether a tool call was running. An agent that does not take the
interrupt within 10 seconds, or whose turn has not ended 20 seconds after it,
is ended instead; the next message starts it again.

## Telemetry for the WP5 stack

With `OTEL_EXPORTER_OTLP_ENDPOINT` set (for example `http://<collector>:4318`), the API
sends three things to that OpenTelemetry Collector and nowhere else; without it,
nothing is sent:

- **Spans**: one per request (FastAPI's own, named by route template), plus
  `wizard.turn`, `wizard.gate` and `wizard.sandbox.*` (`wizard_api/telemetry.py`).
- **Metrics** (`wizard_api/ops_metrics.py`): live agents and their limit, turns in
  progress and the oldest one's age, sandbox runs active and their limit, refusals by
  error code, ownership denials, sessions created (by owner id), deletions by reason and
  outcome, turns by outcome and their duration, agent failures by kind (rate limit,
  overload, server error, timeout), agent tool calls by kind, decision and reason (metered
  calls refused at a limit among them), gate changes, the components of solutions at Gate 2,
  sandbox runs by phase, the sessions volume's use and size, the database size, the api
  container's memory and its limit, sessions by state (total, active, overdue for
  removal), session rows and folders without each other, and whether sandbox runs still
  use the shared model key.
- **Log records** at `WIZARD_OTEL_LOG_LEVEL` (`WARNING` unless set) and above, because
  a shared project gives no way to collect the pod's own output.

### The pod's own log

The API's loggers (`wizard_api.*`) print to stderr at `WIZARD_LOG_LEVEL` (`INFO`
unless set; `DEBUG`, `INFO`, `WARNING` or `ERROR`), each line as
`<time> <LEVEL> <logger>: <message>`. Uvicorn configures only its own loggers, so
without this the API's `INFO` lines, such as each tool call the agent's guard
decides, were dropped. The level is set when the app is imported
(`telemetry.configure_logging`). No handler is added when one that prints is
already on the root (a `basicConfig`, a uvicorn `--log-config`), so no line is
printed twice. The collector's handler keeps its own level: an `INFO` line
reaches the collector only with `WIZARD_OTEL_LOG_LEVEL=INFO`, which now works for
the API's lines even where the pod prints warnings only.

No metric or log label carries an e-mail address or what anyone wrote. Checks that read
the database or walk the sessions volume run at most every `WIZARD_OPS_CHECK_SECONDS`
(600 unless set). The alert rules and dashboards that read these live in the WP5 stack's
repository.

## Output directory (S1-5)

On create, the API sets and creates:

`$WIZARD_SESSION_OUTPUT_ROOT/<user_id>/<session_id>/`

## Tests

```bash
# Postgres required (docker compose up -d postgres)
pytest

# Full stack in Docker (API + UI + E2E)
./scripts/docker-test.sh
```

Persistence tests skip automatically if Postgres is unavailable.  
`test_persistence_restart.py` simulates a new API process (fresh app instance, same Postgres) per #11 / US-S1-01.

### Upgrading the agent SDK

`claude-agent-sdk` is pinned to one exact version in `pyproject.toml`, and with
it the Claude Code CLI the SDK bundles (the image installs no separate CLI).
The agent runs with `bypassPermissions`; the only thing limiting its tools,
files and commands is the PreToolUse hook in
`wizard_api/services/agent_tool_guard.py`. An SDK or CLI release that changes
how hooks are registered, what a hook call carries or what a hook must return
could turn that guard off without an error.

So an SDK upgrade is a change of the pin plus a green
`tests/test_agent_sdk_contract.py`, which runs in the wizard-api CI job without
any model API key. It checks that:

- the installed SDK is the pinned version;
- the options `agent_service._build_options` builds register the guard for
  every tool call (`PreToolUse`, no matcher) under `bypassPermissions`;
- the SDK's hook types (`HookEvent`, `PreToolUseHookInput`,
  `PreToolUseHookSpecificOutput`, `HookCallback`, `SDKHookCallbackRequest`)
  still have the fields the guard reads and answers with;
- driven through the SDK's own control protocol by a fake CLI, with hook inputs
  built from those types, the guard refuses a disallowed tool, a path outside
  the session and a shell operator, and lets an allowed call through.

To upgrade: change the pin, reinstall, run the test, and read the SDK's
changelog for hook changes the test cannot see (for example a new hook event
that runs tools). Do not loosen the test to make a new version pass; fix the
guard or its wiring first.

```bash
uv run --with-editable ../solution_wizard pytest -q tests/test_agent_sdk_contract.py
```

## Model

- `wizard_sessions` — step, gates, metadata (title, messages, status), `active_version`, `output_dir`
- `blueprint_versions` — versioned blueprint JSON per session

## Deleting a session

A user deletes their own session from the session list. An operator does it for them from the api pod:

```bash
python -m wizard_api.session_admin list <e-mail or owner id>
python -m wizard_api.session_admin delete <session id> --reason data-subject-request
python -m wizard_api.session_admin protect <session id>        # kept until --off
python -m wizard_api.session_admin export <e-mail or owner id> --out <folder>
```

Given an e-mail address, `list` and `export` look under its owner id as well as
the address, which needs the web app's key in the command's environment
(`WIZARD_PSEUDONYM_KEY=… python -m …`). `owner-id <e-mail>` prints the id, and
`move-owners [--apply]` moves the sessions still saved under an address.

`--reason` is one of `data-subject-request`, `owner-left` or `other`, and it goes to the log with the session id. Deleting removes the database row and blueprint versions, the session folder, the session's sandbox Jobs and the agent's conversation files. It does not reach backups or logs already written. A session in mid-turn or a protected session is refused.

### Sessions past the retention period

A session nobody has changed for the retention period is removed: 90 days, or `WIZARD_SESSION_RETENTION_DAYS` when set. A change is a chat turn, a gate decision or an edit; opening a session to read it is not. Protected sessions stay.

```bash
python -m wizard_api.session_admin purge                  # lists the sessions due, deletes nothing
python -m wizard_api.session_admin purge --apply          # deletes them through the API, reason retention
python -m wizard_api.session_admin purge --older-than 30  # another period, for this run only
```

Each session goes through the same API delete as `delete`, so a session in mid-turn is refused, reported and tried again by the next purge; the command then exits 1. The output names only the session id and its last change. Nothing runs it on a schedule yet: users are to be told a week before their session goes, and that notice is not built, so run it with `--apply` only by hand until it is.

### Old test runs

Every test run leaves its log and output files under the session's `runs/` folder, and all sessions share one volume. `prune-runs` keeps the newest runs of each session and the run the session points to as its latest, and removes the older ones:

```bash
python -m wizard_api.session_admin prune-runs              # lists what would go, removes nothing
python -m wizard_api.session_admin prune-runs --apply      # keeps 3 runs per session
python -m wizard_api.session_admin prune-runs --keep 1 --apply
```

The session, its package and its latest result stay; a pruned run's log and files do not, so the agent can no longer read them. Run it by hand when the volume fills; nothing schedules it.

`export` writes one zip per session, the same one the session list's Export link gives: `session.json` with the conversation, gates and blueprint versions, and `files/` with the session folder. The agent's own working files, `.env` files and caches are left out. Take the zips off the pod and delete them there when the request is answered.
