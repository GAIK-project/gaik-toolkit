---
name: wizard-usecase-run
description: Walks a set of different use cases (document extraction, RAG, audio, classification, report writing, questions over tabular data) through a running Solution Wizard v2 with the real agent and checks the result of each - the components chosen, the gates, the generated PoC package and optionally its test run - plus what a tester tries by hand, such as a reload during a reply, reopening a gate, asking for a change after approval, writing in another language and ending the session. Use when asked to test the wizard with several use cases, to check that a change to the wizard API, the agent prompt or the skill still produces working sessions end to end, or for "aja wizardin use caset", "testaa wizard eri use caseilla", "run the use case set". Local and manual; it is not part of CI. For the web app's own behaviour use its Playwright specs.
---

# Wizard use case run

`run_usecases.py` plays the user against `wizard_api`: it creates a session for each case in
`usecases.json`, describes the use case, answers every other question with "make sensible
assumptions and go on" (or with the case's scripted answers, below), approves the gates, and
tries the scenarios the case lists. It needs
Python only, and a running API with a working agent (`implementation_layer/WIZARD-DEV.md`).

## Run it

1. Check the API answers (`GET <base>/health` is 200), and ask which one to use if it is not
   the local stack. `--base` (or `WIZARD_API_URL`) names it; the default is
   `http://localhost:8100`. A deployed test instance is reached as described below.
2. Start the run in the background; a whole case takes 10 to 30 minutes:

   ```bash
   python .claude/skills/wizard-usecase-run/run_usecases.py --out <folder outside the repository>
   ```

   - `--only invoice-extraction,policy-rag` runs some cases, `--list` shows them.
   - `--stop-at-gate 1` is the quick pass (a minute or two a case) after a change to the early
     conversation.
   - `--run` uploads the case's `inputs` and starts the PoC test run at the PoC step. Where
     the API has a sandbox it is needed: Gate 3 is refused there without a successful run.
     Without a sandbox the check is reported as skipped and Gate 3 is approved without a run.
     After a failed run the runner tells the wizard so, and starts one more run once the
     package has changed since the last one (by the `package_digest` that
     `GET /sessions/{id}/poc/files` reports, which Gate 3 compares and which covers
     `prompts/` as well as the code; an older API's `version`; where there is neither, once
     the wizard has replied to the failed run), at most three runs a case. The log has a `RUN n` line for each, the summary the count
     (`poc_runs`), and `<case>.run<n>.output.json` what the run wrote.
   - `--pace quick` or `--pace thorough` starts each case as the web app's pace choice does:
     its line, in the case's language, goes ahead of the description. Without it a case
     uses its own `pace`, or none. The web app always sends one (Quick unless the user picks
     Thorough), after a background line when the user picks one; the runner sends no
     background line, so a case without a pace is not what a web app session starts with.
   - `--parallel 2` runs two sessions at a time. Keep it at 1 unless the user asks: the API
     lets one user have two sessions working at a time, and a third waits (the runner retries
     a `429 agent_busy` for ten minutes). For the same reason do not start a second run beside
     one that is going.
3. When it ends, read `summary.md` in the output folder and report from it.

### A deployed test instance

The API is not exposed: forward its port, and put its service token in the environment
variable `--token-env` names (default `WIZARD_API_TOKEN`) without printing it.

```bash
oc port-forward -n <namespace> svc/<api service> <local port>:8100 &
export WIZARD_API_TOKEN="$(oc get secret <token secret> -n <namespace> -o jsonpath='{.data.<key>}' | base64 -d)"
python .claude/skills/wizard-usecase-run/run_usecases.py --base http://localhost:<local port> --out <folder>
```

The forward drops now and then: the runner repeats a read and rejoins a reply it lost, but
start the forward again if it has exited, and stop it when the run is done.

## Read the result

`summary.md` has one row a case (failed checks, last step, minutes, question rounds and
questions, components, package files, test runs started) and the checks of each case below it. Beside it are `<case>.log` (the whole conversation) and
`<case>.json` (the final blueprint, output definition and gates).

- A failed check is a finding only after its log has been read: quote the lines that show it.
  `expected_component` fails when the wizard chose something else, which can be a fair choice;
  say which and let the user judge.
- `skip` means the walk did not get there or the API lacks the feature (an older branch has no
  gate reopening, `/chat/stream` or `/agent/end`).
- A failure that names a refusal (`last refusal: 429 ...`) or a lost connection comes from the
  environment, not the wizard: run that case again with `--only` into a new `--out` folder.
- `change_in_chat` (after Gate 2) passes only if the agent reopens a gate with its own tool;
  the API compares approved content by itself only after Gate 3 (`change_after_gate3`).
- Question rounds and questions are what the wizard asked before it presented the
  specification (before the session reached Gate 1's step). A question is a list item,
  bulleted or numbered, with a "?" outside code and web addresses, which is what the web
  app's answer form reads (`questionsIn` in `solution_wizard_v2/lib/chat-questions.ts`): a
  bullet indented under a question is one of its options unless it asks something itself,
  and then it is a question of its own. A reply with none counts as one question if its last
  line of prose ends in "?" (the runner's rule, not the form's). A reply with a question is a round. Questions written into running text or a table
  are missed, numbered questions set in bold on lines of their own count as one, and a
  rhetorical "?" or a quoted example question in a list is counted. A reply whose stream
  was lost is not counted, and the check says so. The numbers are information
  (`question_rounds`); with pace quick more than one round fails `quick_pace_one_round`:
  read the `QUESTIONS` lines in the log before calling that a finding. A lost reply makes
  that check `info`, not `pass`, as the lost reply may have asked a round of its own.
- `sample_input` fails when the API took none of the case's files: it accepts only the file
  types the session's blueprint names as input, so read the refusal in the log. A failed
  `poc_run` is the PoC's own failure: quote the run's reason from the log, do not mend it here.
- The checks do not judge whether the solution is good. When the user wants that, give each
  case to a small-model subagent with one question - does the blueprint in `<case>.json` do
  what the description in `usecases.json` asks, and what is missing - and have it answer with
  the step names it relied on. Check what it reports before passing it on.

Report the cases that failed first, then what was not covered: the web app is not exercised,
and without `--run` no package was executed.

## Scenarios

| Scenario | What the walk does | Passes when |
| --- | --- | --- |
| `reload_mid_reply` | Joins the running reply from a second connection and sends a second message meanwhile | The reply arrives on the second connection and the second message is refused |
| `language_offer` | Writes in the other language after Gate 1 | The reply carries the offer to switch the interface language |
| `reopen_in_panel` | Reopens Gate 1 after Gate 2, as the panel does | Every gate is pending again and the session is back at Gate 1 |
| `change_in_chat` | Asks for the case's `change` after Gate 2 | An approved gate was reopened (skipped if the case has no `change`) |
| `change_after_gate3` | Asks for the same after Gate 3 | An approved gate was reopened |
| `end_session` | Ends the agent when the session is done | The session reports no live agent |

Every case also checks that it reaches the end with all gates approved, that a package exists
at Gate 3, that an expected component is among the blueprint's steps, and that no reply carried
an error frame. A reply that stopped at the turn limit carries one too, but the API counts it as
the agent working as configured: the runner counts it apart (`turn_limits`, information). `test_run_usecases.py` checks the runner's own logic offline
(`python -m unittest test_run_usecases` in this folder).

## Add or change a case

Edit `usecases.json`: an `id`, a `title`, a `locale` (`fi` or `en`), a `description` written
the way a customer would write it, `expect.component` as a regular expression over component
names, the scenarios to try, and optionally a `pace` and `answers` (below). Use invented
organisations and data only.

A case whose PoC reads files lists them in `inputs`, as paths beside `usecases.json`. Those in
`inputs/` are synthetic and built by `make_inputs.py`: the PDF, XLSX and text files with the
standard library, the same bytes each time; the two recordings with `--audio`, as synthetic
Finnish speech (Piper with a CC0 voice, encoded by ffmpeg). Add a new sample there, keep it a
few kilobytes (a recording under a minute), and keep customer documents out of the repository.
`ticket-classification` lists none: its test run has passed without. `policy-rag` has two
one-page policies and a questions file, four questions the policies answer and two they do
not: without them its first run stops at an empty `sample_input`. `sales-questions` has its
sheet and a questions file for the same reason.

### Scripted answers

A case can carry `answers`, so that every run of it tells the wizard the same things (the
output's fields, for one) and the results can be compared:

```json
"answers": [
  { "id": "SA03", "keywords": ["schema", "fields", "types"], "text": "Use the schema ..." },
  { "topic": "privacy_and_retention", "text": "Nothing is kept ...", "repeatable": true }
]
```

- When a reply asks questions before the specification, each question (the same parser as
  the question count) takes the answer whose keywords hit most of its words. The keywords are
  `keywords`, or else the words of `topic`; a keyword hits a word that is the same or begins
  the same (`field` and `fields`); a keyword several answers share counts for less, and a tie
  goes to the answer listed first. A question nothing hits gets the generic line.
- An answer is sent once, unless it is `repeatable`; one in a message the API refused is still to give. The answers no question drew out go in
  one message that starts "Also note:" when the wizard presents the specification, before
  Gate 1 is approved, so the wizard hears all of them in every run.
- The log says which went where (`ANSWERS round 2: SA03 <- "the question" [the keywords]`,
  `ANSWERS before Gate 1 (also note): ...`), and the summary counts them (`scripted_answers`).
  A wrong match is a keyword to change, not a finding about the wizard.

A case without `answers` is walked as before.

### The maintainers' evaluation cases

`--from-evaluation <folder>` writes a cases file from a folder laid out as
`evaluation_layer/eval_methods/Solution wizard evaluation/use cases`: each subfolder's
`initial_prompt.txt` is the description, its `scripted_answers.json` the answers (keywords
from each answer's topic and trigger), and the inputs are the files under
`fixtures/poc_input/` or `fixtures/input/` with the `poc_input_bundle.json` beside it, or
else the files of `fixtures/` that are not `.json`, `.txt` or `.md`. The API takes each
input by its file name alone, so a PoC that reads the bundle's folder paths finds the files
side by side instead. The file holds paths of the machine, so it goes to the temp folder
(or `--write-cases <file>`), never into a repository:

```bash
python .claude/skills/wizard-usecase-run/run_usecases.py --from-evaluation "<the use cases folder>"
python .claude/skills/wizard-usecase-run/run_usecases.py --cases <the file it printed> --run --only uc01-audio-incident --out <folder>
```

The sheets say to answer only what is asked and nothing unasked; this runner sends the
unasked answers before Gate 1 instead, and the generic line where the sheet has its own
fallback. Say so when comparing with a run a person made by the sheet.
