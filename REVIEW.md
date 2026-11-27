# Review rules

For anyone reviewing a change to this repository, person or agent. `AGENTS.md` says how
the repository is laid out and checked.

## What matters here

- In the library: a change to gaik's public names, parameters, return shapes or extras
  without the matching Solution Wizard registry or agent-skill update; an optional
  dependency whose absence now hides a class silently; a provider or model default
  changed without the release certification in `AGENTS.md`.
- In the demo: a request past `proxy.ts` without its sign-in, approval or trial check; a
  model, transcription or parser call outside the rate limits; an upload that reaches a
  parser or a model before its content and size are checked; personal data kept past its
  cleanup; AI output without its AI notice.
- In the Solution Wizard v2 (`wizard_api`, the web app, the sandbox): a session route
  that skips the ownership check on `X-Wizard-User-Id` or the service token; an upload or
  a package that reaches the agent or the sandbox before its checks; a sandbox Job without
  its resource limits or its network policy; a file's content that the agent reads as
  instructions; an agent, model or sandbox call outside the run and rate limits.
- Anywhere: a secret, real customer document or machine-local path; a test that does not
  check what its name says; a CI or release check made to pass by skipping it.

## Findings

- Give the file and line for each finding and the case where it goes wrong. Report a
  missing check only after naming the code path that lacks it.
- When a change leaves a weakness unfixed, name the area and say the details go to the
  maintainers; never describe how to exploit it in a public issue or comment.
- Skip generated files unless the change is about them: `graphify-out/`, the demo's
  `lib/no-code/catalog.generated.json` and `public/downloads/skills/`, lockfiles and
  `evaluation_layer/**/runs/`.

## Live model checks

CI runs the offline tests on every pull request; the live suite (`-m llm`) runs nightly
and at the release gate. Run live calls in a review only when the change alters what a
model or agent call depends on: the LLM layer, a provider, a prompt or schema sent to a
model, or the wizard's agent runner. Then run only that area's tests (`-k`), and say in
the review what ran live and what did not.

## Severity, and what holds a merge

Mark every finding with one of these:

- **Important**: the change gives a user a wrong result or wrong information, breaks
  something that worked, loses data, or is a security matter. Only these hold a merge,
  until each is fixed or closed with a reason the change's owner agrees to. An agent can
  raise an Important finding but cannot close one.
- **Follow-up**: a real shortcoming that is none of the above. It does not hold the
  merge; it becomes an issue when the change is merged.
- **Nit**: taste or tidiness. At most three, none about formatting (ruff owns it). The
  author may ignore them.
- **Pre-existing**: it was there before this change. It does not hold the merge unless
  the change re-exposes it or builds on it; then it is Important. File an issue if it
  matters.

A review has at most two rounds. After the second, whatever is not Important goes to
issues and stops holding the merge. The merge itself stays the owner's decision, after
reading the diff (`AGENTS.md`, who owns a change), and a change the pull request
template calls high risk also needs a person's review, whatever the findings.

## Summary

Start with the number of findings by severity, or say in one line that there is nothing
to fix.
