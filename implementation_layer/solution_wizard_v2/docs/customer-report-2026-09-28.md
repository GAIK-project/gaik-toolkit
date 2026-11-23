# Customer test report, 28 September 2026 — what is fixed

Customer test report of the Rahti staging deployment, 28 September 2026. Findings are referenced by the report's own numbering: 1–22 from the manual session, R1–R9 from the independent AI retest, T1–T9 from the technical section.

Verified against `sync-v1`. Status is what the evidence shows, not what was intended. 'fixed' means at least one named test fails if the finding returns. 'open' means no fix has shipped. Sprint 4 work is listed separately and is not late.

**16 fixed · 11 open · 5 out of scope by agreement · 2 Sprint 4**

## Test levels

| Level | What it runs | When |
|---|---|---|
| Unit (vitest) | `npm run test` | pr |
| wizard_api (pytest + Postgres) | `docker-test.sh --step api` | pr |
| solution_wizard (pytest) | `cd ../solution_wizard && pytest -q` | pr |
| Stack E2E (UI + wizard_api + Postgres) | `docker-test.sh --step stack-e2e` | push to dev |
| Hand-run observation | `—` | on demand |

## Gates and progression

| Finding | Status | Shipped in | Verified by |
|---|---|---|---|
| **T4** — Approval gates are not enforced by the server; the status is only computed in the browser | **fixed** | #187 | `test_stepping_past_a_pending_gate_is_refused`<br>`test_patch_cannot_step_past_a_pending_gate`<br>`the API refuses a step that would pass an unapproved gate` |
| **18, R3** — Typing "yes" in the chat passes Gate 1 while the screen still waits for the approval button | **fixed** | #187 | `test_stepping_past_a_pending_gate_is_refused`<br>`the API refuses a step that would pass an unapproved gate` |
| **18, R1** — The chat runs through Gates 2 and 3 while the screen stays at step 3 of 13 | **fixed** | #187 | `test_jumping_over_several_gates_at_once_is_refused`<br>`a single jump cannot skip several gates at once` |
| **22, R8** — Going back cancels the Gate 1 approval already given | **fixed** | #187 | `test_going_back_and_forward_again_does_not_need_re_approval`<br>`test_going_back_keeps_the_approval_and_the_way_forward`<br>`keeps an approval the user already gave when they step back below it`<br>`going back keeps the approval and the way forward` |
| **22 (second half)** — After going back in a finished session, "Next step" is blocked with "Answer the wizard's questions in the chat first" | open | — | — |

> **22 (second half).** A different mechanism from the gates — the chat-driven advance in the early steps. Needs its own investigation.

## Language

| Finding | Status | Shipped in | Verified by |
|---|---|---|---|
| **T5** — The UI language is never sent to the AI agent | **fixed** | #190 | `passes the UI locale to the agent`<br>`test_the_bootstrap_pins_the_language_for_a_known_locale` |
| **11, 14** — Finnish and English are mixed in Gate 1, the blueprint and Gate 2 | **fixed** | #190 | `test_the_bootstrap_prompt_carries_the_pin` |
| **17** — The bot answered in Italian | **fixed** | #190 | `test_the_instruction_overrides_the_language_the_user_writes_in`<br>`passes the UI locale to the agent` |
| **R9** — The English UI shows Finnish-only labels on the field list | **fixed** | #190 | `test_switching_the_ui_language_re_pins_the_agent` |

## The PoC package

| Finding | Status | Shipped in | Verified by |
|---|---|---|---|
| **19, T8** — The download is offered as soon as any file exists; the package has no README and no requirements.txt | **fixed** | #191 | `test_a_package_with_only_some_files_is_not_ready`<br>`test_an_incomplete_package_is_not_offered_as_a_download`<br>`an incomplete package is listed but not downloadable` |
| **R6** — The package can be generated at Gate 2, before anything is approved | **fixed** | #191 | `test_the_package_cannot_be_generated_before_gate_2_is_approved`<br>`generation is refused until Gate 2 is approved` |
| **19 (button)** — "Run PoC again" does not run anything, it only regenerates the same package | **fixed** | #191 | `the button says what it does, and it is not 'run'` |
| **R7** — Invoice lines are stored as one text field; dates and amounts as plain text | **fixed** | #192 | `test_many_rows_survive_where_one_text_field_used_to_be`<br>`test_the_row_fields_are_not_flattened_into_the_parent`<br>`test_gaik_validates_the_generated_requirements` |

> **R7.** The wizard now generates and consumes the nested shape. Whether the agent produces it in a live session depends on the SKILL.md instruction added with it, which cannot be verified without the live agent.

## Errors and visibility

| Finding | Status | Shipped in | Verified by |
|---|---|---|---|
| **T3** — Errors are hidden and not logged; the agent service has no logging at all | **fixed** | #189 | chat route logs warn on non-ok and error on throw; agent service error paths log |
| **T3, R2** — When the agent fails, the chat presents a canned mock reply as the assistant's answer | open | — | — |
| **12, 2** — The bot freezes for up to 2–3 minutes with no sign that it is working | open | — | — |

> **T3.** Logging is in place. The chat still substitutes a canned reply when the agent fails, so the user is shown an answer the assistant never wrote — see the open row below.

> **T3, R2.** Removing the fallback changes a contract that two passing tests assert. It is a decision, not a defect fix.

## Traceability and testing

| Finding | Status | Shipped in | Verified by |
|---|---|---|---|
| **T1** — The code running on Rahti is not in the repository; web and api ran different versions | **fixed** | #193 | deploy.sh refuses a dirty tree and a HEAD on no remote branch; verified in all three states |
| **T9** — Automated end-to-end tests are skipped by default, and the nightly acceptance run is on a branch where it never fires | **fixed** | #193 | wizard-v2-acceptance.yml now also triggers on push to dev, which is evaluated from the branch the file is on |

> **T1.** The version is also shown in the login footer, and both halves of the current deployment now resolve to commits in this repository.

> **T9.** The first run of these specs found a regression that had been merged unnoticed, which is the point of the change.

## Internal terms shown to the user

| Finding | Status | Shipped in | Verified by |
|---|---|---|---|
| **R5** — "Export to Excel" is marked as an AI step in the workflow | **fixed** | #188 | `test_an_automated_step_without_a_component_is_not_an_ai_step`<br>`test_an_unknown_type_is_not_assumed_to_be_ai` |
| **T6** — The agent's instructions tell it to show internal module names, Python types and raw JSON | open | — | — |
| **4, 15** — Component names, Python types and diagram code appear in the chat | open | — | — |
| **R4** — Internal values such as accounts_payable are shown on the review screen, and four assumptions cannot be confirmed anywhere | open | — | — |
| **21** — Developer and placeholder texts are shown to users | open | — | — |

## Security

| Finding | Status | Shipped in | Verified by |
|---|---|---|---|
| **T2** — Production uses the developer login; two accounts with hard-coded passwords are in the repository | open | — | — |
| **T7** — The agent runs with full permissions including shell commands, driven directly by user chat input | open | — | — |

## Chat and workspace sync

| Finding | Status | Shipped in | Verified by |
|---|---|---|---|
| **R1** — The screen does not follow the conversation; the requirements counter stays at 0 / 0 | open | — | — |
| **13, R2** — A change agreed in the chat does not reach the review screen | open | — | — |

> **R1.** The agent writes nothing to disk before Phase 3, so there is nothing for the workspace to follow during gathering. Closing it is a design decision, not a defect fix.

> **13, R2.** The sync runs every turn and reads the draft live, so the evidence points at the agent not rewriting its artifact. Needs a live session to confirm.

## Out of scope by agreement (7 September)

| Finding | Status | Shipped in | Verified by |
|---|---|---|---|
| **3** — Options offered by the bot are not clickable | descoped | — | — |
| **5** — Too many questions; the conversation is too heavy | descoped | — | — |
| **7, 8, 10, 20** — Icons, filler text, layout shifts, gate timeline width | descoped | — | — |
| **9** — The chat panel should be resizable | descoped | — | — |
| **T3 (tooling)** — Error tracking integration | descoped | — | — |

## Sprint 4 work, on plan

| Finding | Status | Shipped in | Verified by |
|---|---|---|---|
| **R7 (Excel)** — The generated PoC has no Excel output | Sprint 4 | — | — |
| **—** — Running the PoC, providing its input, following the logs, refining after a run, downloading a deployable package | Sprint 4 | — | — |

---

Generated by `scripts/customer-report.mjs` from the JSON beside this file.
Every test named above is resolved against the working tree when this runs, so a
renamed or deleted test fails the check rather than leaving a finding that looks
covered and is not.
