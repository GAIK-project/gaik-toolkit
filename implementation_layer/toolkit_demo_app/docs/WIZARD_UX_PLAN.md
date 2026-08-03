# Solution Wizard: UX work plan

Written 2026-08-03 after an audit of the deployed demo app on CSC Rahti.
Items marked **DONE** shipped in branch `wizard-start-screen`; the rest are
ordered by value per unit of risk.

## Context that shapes the plan

- The repo is **public**. Anything committed here is disclosed, so security
  defects are live disclosures and go first, ahead of polish.
- The wizard is a **guided multi-step tool**, not a landing page. Restraint
  beats visual ambition: the user is doing work, not being sold to.
- Production is deployed from `:latest` images that are only rebuilt by
  `openshift/deploy.sh`. Pod age says nothing about what is live; check the
  ImageStream push date.

---

## DONE

### 1. The start screen is a start screen
The welcome was injected into the chat log as a fake assistant message, so it
was indistinguishable from the wizard talking, and the backend's own opening
question arrived right underneath it saying much the same thing.

`components/demo/wizard-start-screen.tsx` now owns the introduction and lives
outside the conversation. The bootstrap turn's visible text is suppressed, so
an empty chat log means "nothing has been said yet" and every bubble is real.
Four one-click starting points replace the bulleted example list.

### 2. Progress is visible
"Round 1" buried in prose was the only signal of how far along a run was.
`components/demo/wizard-progress.tsx` shows five user-facing stages
(Requirements, Specification, Blueprint, Proof of concept, Documentation),
derived from the artifacts the wizard writes rather than from parsing chat
text, so it advances on real work and cannot be fooled by wording.

### 3. Loading and failure are honest
Loading now says "Preparing your workspace" with skeletons in the shape of
what is coming. A failed bootstrap renders an error with a **Try again**
button instead of leaving the user on a skeleton that never resolves.

### 4. Question rounds are scannable
`SKILL.md` Phase 2 now specifies the presentation contract: max 3 questions per
turn, one short lead-in, questions as a numbered list, and a horizontal rule
before the closing instruction. `MessageResponse` gives `hr` and `ol` real
spacing so the structure survives rendering.

---

## NEXT (highest value first)

### 5. Verify the round-formatting contract against a live run
**Why:** items 4 is a prompt instruction. The model can ignore it, and nothing
in CI catches that.
**Do:** run one full wizard session on production, capture three consecutive
turns, and check the contract holds (≤3 questions, numbered, rule before the
closing line). If the model drifts, move the contract from prose into the
bootstrap prompt in `api/routers/solution_wizard.py`, which is re-sent every
turn and therefore harder to forget.
**Risk:** low. **Cost:** one session.

### 6. Persist the session across a page reload
**Why:** `sessionId` lives in React state only. A refresh, an accidental
back-navigation, or a laptop sleep loses a long-running session with no way
back, and the workspace is then reaped 30 minutes later.
**Do:** put `sessionId` in `sessionStorage`, and on mount try
`GET /wizard/files/{id}` first: 200 means resume, 404 means start fresh. The
conversation history is not recoverable from the backend today, so either
(a) also persist `messages` in `sessionStorage`, or (b) add a
`GET /wizard/history/{id}` endpoint. Prefer (a) first; it is client-only.
**Risk:** low. **Cost:** half a day.

### 7. Explain what the wizard is doing during long silences
**Why:** phases 5 to 11 run for minutes with only "Thinking…" or a single
tool-activity line. Users cannot tell a working wizard from a hung one.
**Do:** the activity line already receives tool names. Add elapsed time after
15 seconds, and surface the last written filename ("Wrote blueprint.json") as
a completed step rather than a transient label. The file browser already knows
this; the chat column does not use it.
**Risk:** low. **Cost:** half a day.

### 8. Make the generated-files panel the reward it should be
**Why:** the panel is the actual output of the run and currently reads as an
empty grey box for the first several minutes.
**Do:** show the five expected artifacts up front as a dimmed checklist that
fills in as files land. This turns dead space into an explanation of what the
user is waiting for, and reuses the same stage derivation as item 2.
**Risk:** low. **Cost:** half a day.

### 9. Mobile
**Why:** the layout is `lg:grid-cols-[1fr_320px]` with a fixed
`h-[calc(100dvh-220px)]`. On a phone the file panel drops below a chat that is
already viewport-height, so it is effectively invisible, and the header eats a
large share of a small screen.
**Do:** below `lg`, move the file browser into a sheet triggered by a button
that shows the file count; shrink the page header to a single line.
**Risk:** medium (touches shared layout). **Cost:** one day.

### 10. An end-of-run summary
**Why:** a run currently just stops. There is no "here is what you got".
**Do:** when stage reaches Documentation and the turn ends, render a summary
card: what was built, the component chain, and a prominent "Download
everything" (`/wizard/download/{id}` already returns the zip).
**Risk:** low. **Cost:** half a day.

---

## SEPARATE FROM UX, BUT OUTSTANDING

### 11. Non-reproducing 404 on `/wizard/files/{id}`
Seen once on 2026-08-03 09:14. The endpoint behaves correctly when probed
directly, the frontend swallows the error, and a later session on the same
build returned 200 for the same call. Leave it; if it recurs, log the session
id at creation and at each lookup so the two can be compared.

### 12. `audit_registry.py --strict` is permanently red
Nine `parity` findings and one `new` finding are deliberate design decisions
(module-internal building blocks; a provider layer), but there is no way to
acknowledge them, so `--strict` always exits 1 and cannot gate anything.
**Do:** add an `acknowledged.json` next to the registries listing
`{category, component, reason}`, and have `--strict` ignore matching findings.
Then wire it into CI.

### 13. Pre-existing lint errors — DONE
The 15 `react/no-unescaped-entities` errors across 8 demo pages are escaped, so
`bun run lint` is green apart from one `<img>` LCP warning in
`video-search/page.tsx` (a dynamic thumbnail URL; converting that to
`next/image` is a real change, not a lint fix). Rendered output is unchanged.

### 14. Dev environment installs without extras — DONE
`AGENTS.md` now states `uv sync --all-extras` as the required setup step and
explains why: a missing extra makes a component silently absent, so the audit
reports false `removed` drift and the wizard tests skip assertions they look
like they are running.
