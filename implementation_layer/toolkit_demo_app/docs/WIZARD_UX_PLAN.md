# Solution Wizard: open UX work

Started 2026-08-03 after an audit of the deployed demo app on CSC Rahti.
**This file lists what is still open.** What already shipped is in the git log
(`git log --oneline -- implementation_layer/toolkit_demo_app`), not repeated here.

## Context that shapes the plan

- The repo is **public**. Anything committed here is disclosed, so security
  defects are live disclosures and go first, ahead of polish.
- The wizard is a **guided multi-step tool**, not a landing page. Restraint
  beats visual ambition: the user is doing work, not being sold to.
- Production is deployed from `:latest` images that are only rebuilt by
  `openshift/deploy.sh`. Pod age says nothing about what is live; check the
  ImageStream push date.
- Two things worth not relearning:
  - **The wizard's own instructions must live in the bootstrap prompt, not in
    SKILL.md**, when they govern how every turn is *formatted*. A live run
    showed the model ignoring a formatting rule buried in a 13k-token file it
    reads once via a tool; the same rule in the prompt itself took immediately.
  - **Caching was the wrong instinct** for the slow session start. The cost was
    generation, not prefill, and the output was being discarded — there was
    nothing worth caching. The fix was to delete the work, not memoize it.

---

## NEXT (highest value first)

### 1. Persist the session across a page reload
**Why:** `sessionId` lives in React state only. A refresh, an accidental
back-navigation, or a laptop sleep loses a long-running session with no way
back, and the workspace is then reaped 30 minutes later. This is currently the
worst failure mode in the whole flow.
**Do:** put `sessionId` in `sessionStorage`, and on mount try
`GET /wizard/files/{id}` first: 200 means resume, 404 means start fresh. The
conversation history is not recoverable from the backend today, so either
(a) also persist `messages` in `sessionStorage`, or (b) add a
`GET /wizard/history/{id}` endpoint. Prefer (a) first; it is client-only.
**Risk:** low. **Cost:** half a day.

### 2. Explain what the wizard is doing during long silences
**Why:** phases 5 to 11 run for minutes with only "Thinking…" or a single
tool-activity line. Users cannot tell a working wizard from a hung one.
**Do:** the activity line already receives tool names. Add elapsed time after
15 seconds, and surface the last written filename ("Wrote blueprint.json") as
a completed step rather than a transient label. The file browser already knows
this; the chat column does not use it.
**Risk:** low. **Cost:** half a day.

### 3. Tick off the generated-files checklist as files land
**Why:** the panel already lists the five artifacts a run produces, but the
list is static — it previews the output instead of tracking it.
**Do:** reuse `deriveWizardStage` to mark each item done as its file appears.
**Risk:** low. **Cost:** an hour.

### 4. Mobile
**Why:** the layout is `lg:grid-cols-[1fr_320px]` with a fixed
`h-[calc(100dvh-220px)]`. On a phone the file panel drops below a chat that is
already viewport-height, so it is effectively invisible, and the header eats a
large share of a small screen.
**Do:** below `lg`, move the file browser into a sheet triggered by a button
that shows the file count; shrink the page header to a single line.
**Risk:** medium (touches shared layout). **Cost:** one day.

### 5. An end-of-run summary
**Why:** a run currently just stops. There is no "here is what you got".
**Do:** when stage reaches Documentation and the turn ends, render a summary
card: what was built, the component chain, and a prominent "Download
everything" (`/wizard/download/{id}` already returns the zip).
**Risk:** low. **Cost:** half a day.

### 6. Inline answers for closed-vocabulary questions — DEFERRED
Proposed and **explicitly deferred** on 2026-08-03 to avoid changing too much
at once. Recorded so the reasoning is not lost.

**Why it would help:** several Phase 2 fields are genuinely enumerable
(`language`, `model_provider`, `human_review`, `runtime_interface`, whether the
output needs a PDF). Free text there costs the user time and produces values the
validator has to normalise.
**Why only those:** do **not** do this for current process, pain points or
success criteria. Their value is the user's own wording; a select would flatten
exactly the nuance Phase 2 exists to capture.
**How:** have the wizard append a fenced `wizard-choices` block (field +
options) alongside the question; the frontend renders it as chips. **A chip
fills the composer, it does not send** — so the user can pick "Finnish" and keep
typing "…but some technicians speak Swedish". Degrades to a plain text question
when the model omits the block.
**Risk:** low. **Cost:** half a day.

---

## SEPARATE FROM UX, BUT OUTSTANDING

### 7. Local dev on Windows cannot run the wizard
`ClaudeSDKClient.connect()` spawns the bundled CLI via
`asyncio.create_subprocess_exec`, which raises `NotImplementedError` under the
event loop uvicorn selects on Windows. Production (Linux) is unaffected, so this
is a developer-experience gap, not a product bug — but it means the wizard can
only be exercised against a deployed API, which is slow and costs tokens.
**Do:** select a Proactor-based loop for the API process on Windows (a no-op on
Linux) and confirm `/wizard/start` succeeds locally.

### 8. Non-reproducing 404 on `/wizard/files/{id}`
Seen once on 2026-08-03 09:14. The endpoint behaves correctly when probed
directly, the frontend swallows the error, and later sessions on the same build
returned 200 for the same call. Leave it; if it recurs, log the session id at
creation and at each lookup so the two can be compared.

### 9. `audit_registry.py --strict` is permanently red
Nine `parity` findings and one `new` finding are deliberate design decisions
(module-internal building blocks; a provider layer), but there is no way to
acknowledge them, so `--strict` always exits 1 and cannot gate anything.
**Do:** add an `acknowledged.json` next to the registries listing
`{category, component, reason}`, and have `--strict` ignore matching findings.
Then wire it into CI.

### 10. Sonnet 5 upgrade has a hidden gotcha
The wizard runs `claude-sonnet-4-6` (set via `ANTHROPIC_DEFAULT_SONNET_MODEL` in
the Rahti secret; Claude Agent SDK on Microsoft Foundry). Moving to
`claude-sonnet-5` is a one-env-var change, **but** Sonnet 5 defaults
`thinking.display` to `"omitted"` where 4.6 defaults to `"summarized"` — the
Reasoning panel would silently go blank. Fix that in the same change, confirm
the model is deployed in the Foundry resource, and expect ~30% more tokens per
run from the new tokenizer at the same sticker price.
