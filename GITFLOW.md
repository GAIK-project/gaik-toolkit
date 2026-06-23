# GitFlow — Fork Development Process

This document describes the branching model and commit conventions for this fork
(`perttiy/gaik-toolkit-configuration-wizard-v2`). It keeps day-to-day development
separate from stable, production-ready code.

For coding guidelines (module structure, tests, releases), see
[`guidance_layer/CONTRIBUTING.md`](guidance_layer/CONTRIBUTING.md).

---

## Branch roles

| Branch | Purpose | Who merges here |
|--------|---------|-----------------|
| **`main`** | Stable, tested, deployable code only | Maintainer via PR from `develop` or `hotfix/*` |
| **`develop`** | Integration branch for ongoing work | Contributors via PR from `feature/*` |
| **`feature/*`** | New features or non-urgent changes | — (merge target: `develop`) |
| **`hotfix/*`** | Urgent fixes to production-ready code | — (merge target: `main`, then back-merge to `develop`) |

### Rules

- **Never commit directly to `main`.** All changes reach `main` through a reviewed pull request.
- **`develop` may be ahead of `main`.** That is expected — it is the integration branch.
- **`main` must always build and pass CI.** Do not merge into `main` unless tests pass.
- **Delete feature branches** after they are merged.

---

## Daily workflow

### Start a new change

```bash
git checkout develop
git pull origin develop
git checkout -b feature/short-description
```

Use a short, kebab-case slug that describes the change, e.g. `feature/wizard-bpmn-export`.

### Work, commit, push

```bash
git add <files>
git commit
git push -u origin feature/short-description
```

Open a **pull request into `develop`**. Wait for CI to pass before merging.

### Promote stable code to `main`

When `develop` is ready for release:

1. Open a PR: `develop` → `main`
2. Confirm CI is green
3. Merge (prefer squash or merge commit — stay consistent within the team)
4. Tag releases on `main` only: `git tag v0.X.Y && git push origin v0.X.Y`

### Hotfix (urgent production fix)

```bash
git checkout main
git pull origin main
git checkout -b hotfix/short-description
# fix, commit, push
# PR → main, then merge main back into develop
```

---

## Syncing with upstream

This fork tracks the upstream GAIK toolkit. Add the upstream remote once:

```bash
git remote add upstream https://github.com/GAIK-project/gaik-toolkit.git
```

To pull upstream changes into the fork:

```bash
git fetch upstream
git checkout develop
git merge upstream/main    # or: git rebase upstream/main
# resolve conflicts, run tests, push
git push origin develop
```

After upstream sync is verified, open a PR from `develop` → `main` to promote stable changes.

---

## Commit message conventions

Every commit must be documented clearly so the history is readable without opening
the diff. We follow [Conventional Commits](https://www.conventionalcommits.org/)
— the same style already used in this repository.

### Format

```
<type>(<scope>): <short summary>

<optional body — explain why, not just what>

<optional footer — issue refs, breaking changes>
```

### Subject line (first line)

- Use the imperative mood: `add`, `fix`, `update` — not `added` or `fixes`
- Keep it ≤ 72 characters
- No trailing period
- Scope is optional but encouraged when the change is localized

### Types

| Type | When to use |
|------|-------------|
| `feat` | New feature or user-visible behaviour |
| `fix` | Bug fix |
| `docs` | Documentation only |
| `refactor` | Code change that neither fixes a bug nor adds a feature |
| `test` | Adding or updating tests |
| `chore` | Build, CI, tooling, dependencies |
| `style` | Formatting, whitespace (no logic change) |
| `perf` | Performance improvement |

### Scope examples

Use the area of the codebase affected:

- `solution-wizard`, `demo-app`, `transcriber`, `RAG`, `skills`, `website`, `ci`

### Body (required when the change is non-trivial)

Write 1–5 lines explaining:

- **Why** the change was made (problem, requirement, context)
- **What** changed at a high level (if not obvious from the subject)
- **How to verify** (test command, manual step) when helpful

### Footer

- Reference issues: `Closes #42`, `Refs #17`
- Breaking changes: start a paragraph with `BREAKING CHANGE:` describing migration steps

### Examples

**Simple fix:**

```
fix(parallel_transcriber): raise api_timeout_seconds default 180→600
```

**Feature with body:**

```
feat(admin): per-user report limit override + summary stats

Allow admins to set individual report quotas per user and view
aggregate usage in the admin panel. Defaults remain unchanged for
existing users.

Test: pytest implementation_layer/unit_tests/ -k admin
```

**Documentation:**

```
docs: add GitFlow branching model for fork development

Documents main/develop workflow, upstream sync, and commit conventions
so contributors follow a consistent process.
```

**Breaking change:**

```
refactor(evaluation_layer): move output methods to evaluation_layer/

BREAKING CHANGE: import paths changed from
implementation_layer/evaluation/ to evaluation_layer/. Update imports
before upgrading.
```

### What to avoid

- Vague messages: `fix stuff`, `update`, `wip`, `changes`
- Mixing unrelated changes in one commit
- Commit messages that only restate the diff without context

---

## Pull request checklist

Before merging into `develop`:

- [ ] Branch is up to date with `develop`
- [ ] CI passes (tests + format check)
- [ ] Commit messages follow the conventions above
- [ ] PR description explains **why** and how to test
- [ ] No secrets, credentials, or `.env` files committed

Before merging into `main`:

- [ ] All `develop` checklist items satisfied
- [ ] Changes have been integrated and tested on `develop`
- [ ] Version/tag plan is clear if this is a release

---

## CI triggers

GitHub Actions runs tests on:

- Push to `main` or `develop`
- Pull requests targeting `main` or `develop`

Publishing to PyPI is triggered only by version tags (`v*.*.*`) on `main`.
