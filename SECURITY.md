# Security policy

## Reporting a weakness

Report a security weakness privately: on this repository's **Security** tab choose
**Report a vulnerability**, or open
<https://github.com/GAIK-project/gaik-toolkit/security/advisories/new>. Do not open a
public issue, pull request or discussion about it.

Say what is affected (the gaik library and its version, or the demo app), how to
reproduce it and what someone could do with it. The maintainers answer in the advisory,
and the fix and its disclosure are agreed there.

## Supported versions

Security fixes go into `main` and the next gaik release on PyPI. Use the latest
release; earlier releases do not get separate fixes.

## Scope

- In scope: the gaik library (`implementation_layer/src/gaik/`), the demo app
  (`implementation_layer/toolkit_demo_app/`) and its public deployment, and the
  Solution Wizard (`implementation_layer/solution_wizard/`).
- Out of scope: weaknesses in the model providers and other services that gaik calls.
  Report those to the provider.
