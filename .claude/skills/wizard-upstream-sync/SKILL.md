---
name: wizard-upstream-sync
description: Takes upstream GAIK-project/gaik-toolkit changes (a gaik release, Solution Wizard registry or guidance updates, backend fixes) into the Solution Wizard v2 fork NCF-public/gaik-toolkit-configuration-wizard-v2 as one checked pull request to develop. Lists the upstream commits since the last sync and what each touches, flags gaik public-surface, extras and pin changes and the files the fork would inherit, predicts merge conflicts, runs the gaik-sync audit and the wizard's tests in a separate worktree, and drafts the PR and its review note. Use whenever a new gaik version or other upstream backend change should reach wizard v2, when asked what upstream has that the wizard lacks, or for "tuo gaikin muutokset wizardiin", "synkkaa upstream wizard v2:een", "gaik 0.8.x wizardiin". Keeping the registry in step with gaik inside one repository is the gaik-sync skill; reviewing pull requests is not this skill.
---

# Wizard upstream sync

`GAIK-project/gaik-toolkit` (upstream) owns the gaik library and the v1 Solution Wizard. The
fork `NCF-public/gaik-toolkit-configuration-wizard-v2` shares its history, adds wizard v2,
and takes upstream in by merging a release tag into `develop` through one pull request
(fork PR 61 took v0.8.10, PR 66 took v0.8.11). This skill makes that PR routine: a
read-only plan, then the merge, pins, checks and PR text in a worktree. Nothing is pushed
or posted until the person running the sync has seen it and said go.

## How the two repositories relate

| Paths | Source of truth | How changes move |
|---|---|---|
| `implementation_layer/src/gaik/`, `pyproject.toml` (extras) | upstream | release tag and PyPI; the fork merges the tag; both images install `gaik==ARG GAIK_VERSION` from PyPI |
| `implementation_layer/solution_wizard/` (registry, cards, `SKILL.md`, `gaik_validated_version.txt`, PoC templates and code) | upstream, also edited by the fork | the merge; this is where conflicts land |
| `implementation_layer/solution_wizard_v2/`, `wizard_api/`, `deploy/`, `gaik-aiops/`, the wizard workflows | fork | fork PRs to `develop`; to be delivered upstream later from `release/wizard-v2`, as the fork's open PR 20 describes |
| `AGENTS.md`, `CLAUDE.md`, `.github/` templates and `CODEOWNERS`, `SECURITY.md` | upstream | the merge; the fork inherits them unless it drops them on purpose |
| demo app, docs, evaluation, agent skills | upstream | ride along without effect on the wizard |

Fixes the fork's team sends upstream come back with the next release and sync.

Two facts make the local checks the real gate:

- The fork's CI does not run upstream's `test.yml` on `develop`, and it runs the
  solution_wizard tests without gaik installed, so the reference-card checks against gaik
  skip there (see the comments in the fork's `.github/workflows/solution-wizard-v2.yml`).
- The images run the PyPI release, not the repository's gaik. A library fix reaches the
  sandbox only through a release and a `GAIK_VERSION` bump, and the fork's own edits to
  gaik files (the plan lists them) are not in the images at all.

`SYNC` below stands for `python .claude/skills/wizard-upstream-sync/scripts/upstream_sync.py`,
run from a checkout of either repository (Python 3.11+, standard library). It finds the
wizard clone itself: the current repository when it is the fork, otherwise a folder named
`gaik-toolkit-configuration-wizard-v2` beside this checkout; pass `--repo` or set
`WIZARD_REPO` for another place. Worktrees and reports go to `.worktrees/<clone>/` beside
the clone; to keep them elsewhere, set it once per clone with
`git -C <clone> config upstream-sync.worktrees <dir>`. Nothing is written into the repository.

## 1. Plan (read-only)

```bash
SYNC plan
```

It fetches `origin` and upstream first. The first run adds the remote `upstream` with main
and the `v*` tags only, as the fork's GITFLOW.md says, with pushing to it disabled;
setuptools-scm in the fork needs those tags to give the in-repo gaik a version. Then it reports:

- the last sync point and the fork PR that landed it;
- every upstream change since then (a PR or a direct commit) with the path classes it
  touches and what that means for the wizard; demo and docs changes are summed up as
  riding along;
- hints of gaik public-surface changes (heuristic), extras, registry and card changes, and
  whether the gaik-sync audit is needed;
- pins: the validated pin, both `ARG GAIK_VERSION`, the runner README, whether PyPI has the
  version, and `GAIK_EXTRAS` gaps;
- a `git merge-tree` preview of conflicts and the files both sides changed;
- files the fork would inherit (code owners, templates, security policy, agent instructions);
- the fork's own edits to upstream files, upstream commits not yet in a release, and open
  upstream PRs (with `gh`).

The default target is the newest `v*` tag on upstream main: the images install a PyPI
release, and `test_deploy_instances` requires the image pins to equal the validated pin.
`--target vX.Y.Z` picks a tag. `--target main` takes unreleased commits; use it only when
they touch nothing the images run (no gaik source, extras or wizard assets).
`--base REF --target TAG` replays a past sync, which is how the script was checked.

Say in a few lines what would move and why, from the plan's table and Recommendation. If
nothing moves, stop there.

## 2. Branch and merge (local)

After the go for a target:

```bash
SYNC prepare --target vX.Y.Z
```

This creates a worktree on `chore/gaik-X.Y.Z` from `origin/develop` and merges the tag with
`--no-ff` as "Merge upstream gaik-toolkit vX.Y.Z into develop". The main checkout stays as
it is, so work in progress there is not disturbed.

On conflicts it stops with the merge in progress. Resolve each file as
[references/conflicts.md](references/conflicts.md) describes, then commit with a
"Conflicts:" paragraph that names each file and the side kept. A conflict inside
`implementation_layer/src/gaik/` changes the gaik library: describe it and ask first, since
AGENTS.md requires approval for every library change.

When the plan lists inherited files, decide each one rather than letting it slip in: for
example upstream's `CODEOWNERS` would ask upstream's maintainer to review fork PRs, and its
`SECURITY.md` points to upstream's advisories while the fork's team has its own private channel.

## 3. Image pins

```bash
SYNC bump-pins --worktree <worktree> --commit
```

Sets `ARG GAIK_VERSION` in both Dockerfiles and the runner README to the merged validated
pin and commits "chore(images): install gaik X.Y.Z in the api and runner images". Run it
only when the plan says PyPI has the version. When the plan reports `GAIK_EXTRAS` gaps (an
extra upstream dropped, or a new component whose extra the images lack), decide it with
the fork's team; both Dockerfiles must list the same extras, which a test checks.

## 4. Checks

```bash
SYNC checks --worktree <worktree> --plan <notes>/plan-X.Y.Z.json
```

Takes a few minutes, so run it in the background. In the worktree it runs:
`uv sync --all-extras` on Python 3.11, as CI and the images use (`--python` picks another);
the gaik-sync audit; the solution_wizard tests with gaik installed;
the image pin tests of `test_deploy_instances.py`; the unit tests for the agent plugin, the
no-code catalog, the fork's VisionExtractor edit and each changed component; the wizard_api
tests (its Postgres tests skip without a database); `ruff format --check` on the Python files
the PR changes and `ruff check` on wizard_api (ruff 0.14.10); and a scan of the fork's
commits on the branch for machine-local paths. As in CI, provider keys and tokens are
removed from the tests' environment and tests marked `llm` (paid API calls) are left out.
Results and logs go to `checks-<worktree>.json` in the notes folder.

On Windows two parts can only run in CI, which runs them on every sync PR because the pin
bump touches `implementation_layer/wizard_api/` and `implementation_layer/deploy/`:

- wizard_api imports `fcntl`, which Windows lacks, so the checks skip its tests and say so.
  With Docker running, `bash scripts/docker-test.sh --step api` in the worktree's
  `implementation_layer/wizard_api` runs them; it leaves a Postgres container up.
- The deploy-manifest tests run `bash deploy.sh`, and Python on Windows finds WSL's bash in
  System32 before Git Bash, so only the Dockerfile part of `test_deploy_instances.py` runs locally.

Reading the results:

- `uv sync` failed: the audit and the tests are reported as not run, since without the
  environment they would only show missing components and a missing pytest. Read
  `uv-sync.log`, fix the environment and run the checks again. A build error for one
  package usually means the Python has no wheel for it.
- Audit findings other than `version` (`removed`, `api_drift`, `options`, `parity`, `new`):
  follow the gaik-sync skill (`.claude/skills/gaik-sync/SKILL.md` in the worktree) with its
  approval gate, and commit approved fixes separately in this PR. A `version` finding with
  a dev suffix such as `0.8.11.post2.dev0` is expected in a checkout.
- A failing test: rerun it alone, then on `origin/develop` in a detached worktree
  (`git worktree add --detach <path> origin/develop`, then `SYNC checks --worktree <path>
  --only uv-sync,<step>`). Failing there too makes it pre-existing; say so in the PR.
  Otherwise the sync caused it: fix the fork's code in this PR (fork PR 61 needed a
  `fix(poc)` commit for `RAGWorkflow(parser="text")`), or stop and report it when the fix
  belongs upstream.
- Machine-local paths: remove them before anything is pushed; both repositories are public.

## 5. PR draft, then the go

Read the upstream PR bodies (`gh pr view N --repo GAIK-project/gaik-toolkit`): their Risk
and Environment variables sections feed this PR's. Write one to three "Why" bullets into a
file, saying what each change fixes for the wizard, for example "fixes the KnowledgeCurator
stop that took a UC04 run to 0/11", and the environment variables into another (or "None."). Then:

```bash
SYNC pr-body --plan <notes>/plan-X.Y.Z.json --checks <notes>/checks-gaik-X.Y.Z.json \
  --why <why.md> --env <env.md> --slack-line "<the fix that matters most to the wizard>"
```

The body follows upstream's `.github/pull_request_template.md`, which the fork inherits with
the sync: What (with the upstream changes the wizard uses, the rest collapsed), Why, Merge
conflicts (from the merge message), Testing (a checklist of what ran), Risk, How to revert,
Environment variables, and the merge note. It also writes the title and a short review note
for the team's channel into the notes folder, refuses text with machine-local paths and
lists any `[[fill: ...]]` still open. When a check failed for a reason older than the sync,
add a line saying so with `--notes-extra <file>` and set the note's last line with
`--slack-state`; `--risk` replaces the computed risk line.

Show the plan summary, `git log --oneline origin/develop..HEAD` in the worktree, the check
results, the PR text and the review note, and where the worktree is so it can be looked at
directly. Then wait: pushing, opening the PR and posting the note each need a go.

```bash
git -C <worktree> push -u origin chore/gaik-X.Y.Z
gh pr create --draft --repo NCF-public/gaik-toolkit-configuration-wizard-v2 --base develop \
  --head chore/gaik-X.Y.Z --title "Bring gaik X.Y.Z into develop" --body-file <notes>/pr-X.Y.Z.md
```

Push the branch only, never `--tags`: the upstream tags stay local. The draft lets CI run
what the machine could not (wizard_api with Postgres, the deploy manifests, the image
security audit) before anyone is asked to review. When CI is green, tick those lines in the
PR body, run `gh pr ready`, and post the note in the team's review channel:
"Review: <link>" and one to three plain lines.

## Upstream moved while the PR is open

When upstream gets changes the open sync PR should carry too, add them to the same PR
instead of opening a second one. In the sync's worktree (make one from the PR's branch if
this machine has none), merge the target again with `--no-ff` and the same message form,
run the checks again, and update the numbers in the PR body: the commit the sync stands
on, the count of upstream changes and commits, the table row for each new change, and the
Testing lines that changed. Push the branch; CI runs again on the PR.

## What keeps the PR easy to review

- One sync per PR, merged with a merge commit, not a squash, so the shared history stays,
  the next merge-base is the tag, and the next sync stays small. The PR text says so.
- Only what the sync needs: the merge, the image pins and fixes the checks require. Fork
  features and unrelated version bumps go in their own PRs.
- Both repositories are public: no machine-local paths, secret names or exploit details in
  commits, PR text or issues. Report a weakness privately: in gaik through upstream's
  `SECURITY.md`, in the wizard through the fork team's private channel.
- gaik library fixes belong upstream in `GAIK-project/gaik-toolkit`, not as fork edits.

After the PR is merged: `git worktree remove <worktree>` and `git branch -d chore/gaik-X.Y.Z`.
The next plan then reports the new tag as the last sync point.
