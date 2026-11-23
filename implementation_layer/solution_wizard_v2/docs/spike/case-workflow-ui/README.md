# Spike: a working UI for the generated solution, built from the BPMN

Status: prototype for discussion. Not wired into the app, no tests, no data.

## Why

The wizard's output today is a PoC package: `run_poc.py`, run from the command line or
in our sandbox. The GAIK use cases on gaik.ai are presented as applications instead: one
person gives the input, the AI fills in a record, another person checks, corrects and
approves it, and the result is exported. At the kickoff the V2 scope included "a simple
user interface" for the generated solution (V2 item 4; sprint plan T6-4, a light form UI
for the input and output artifacts).

This spike checks how much of that UI can be derived from what the wizard already
produces, instead of being written per use case.

## What it does

`build_workflow.py` reads a session's artifacts and writes one self-contained HTML page:

| UI part | Comes from |
|---|---|
| Roles (role switcher, "your turn" badge) | BPMN lanes that hold a user task |
| One screen per role | BPMN user tasks |
| AI steps in the stepper | BPMN service tasks, in sequence-flow order |
| Input widgets on the first screen | data objects the first user task writes (audio → record / upload) |
| Approve / reject | the exclusive gateway after the review task |
| Review form: fields, required, allowed values, formats | blueprint `target_output_spec` |
| AI result, transcript, grounding check | the sandbox run's output (between the `POC OUTPUT` markers) |

The AI steps are simulated with one real run's output, so the page shows the flow, not
a live run. State is in memory: both roles work in one browser window.

```bash
python build_workflow.py use_case.blueprint.json workflow.bpmn sandbox-run.log input.wav out.html
```

Pass `-` instead of the audio file when the input is not audio.

## What it showed

Tried with UC01 (Finnish voice fault report → maintenance ticket → supervisor review):

1. **Roles, screens and order come from the BPMN without per-case code.** Lanes Field
   Technician / GenAI / Maintenance Supervisor became two role screens and four AI steps.
2. **The form comes from `target_output_spec` without per-case code.** Nine fields,
   urgency as a select, DD/MM/YYYY and HH:MM checked from the field descriptions.
3. **The BPMN alone is not enough.** The case says the supervisor *returns* the ticket to
   the technician for correction and resubmission. The BPMN models rejection as an end
   event (our BPMN convention: `Approved?` + Rejected end), so the loop back is missing,
   and the prototype has to add it as a rule of its own.
4. **The blueprint's `business_process` was empty** (`participants`, `manual_steps`,
   `decision_points` all `[]`), although the answers to the requirement questions named
   who records, who reviews and what happens on return.

## Proposal

Build the UI and the roles from **both the BPMN and the requirement questions**:

- the BPMN gives the order, lanes and tasks;
- the questions must collect, and the blueprint must carry, what the BPMN cannot hold:
  - who the roles are, and which inputs each role gives (several people may give
    parts of the input before the AI runs);
  - what the reviewer may do: approve, return for correction (to whom), reject;
  - what is exported, in which formats, and where it goes.

That means filling `business_process` (participants, manual steps, decision points)
from the answers, and letting the BPMN generator draw the return loop when a decision
point says so.

A working version on Rahti would add a case model (inputs, state, result, events per
case), a sandbox run per case with that case's own inputs, and role-to-user mapping.
