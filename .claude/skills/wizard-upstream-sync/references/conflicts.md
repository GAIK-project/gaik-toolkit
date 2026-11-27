# Resolving sync conflicts

The fork edits a few upstream files on purpose, and merges conflict only there. For any
conflicted file, read both intents before choosing:

```bash
git diff <last-sync-point> origin/develop -- <file>   # what the fork changed
git diff <last-sync-point> <tag> -- <file>            # what upstream changed
```

`<last-sync-point>` is in the plan ("Last sync point"). Keep both intents where they do
not contradict. Upstream wins for what it owns (the validated pin, its components'
registry entries and cards, the gaik library); the fork wins for its deliberate wizard v2
and PoC-generation changes.

| File | Usual resolution |
|---|---|
| `implementation_layer/solution_wizard/gaik_validated_version.txt` | the tag's version |
| `pyproject.toml` | both: upstream's change plus the fork's lines (`pyyaml` in `dev` for the manifest tests, the `git_describe_command` that matches only `v*.*.*` tags, the ruff per-file ignore for `wizard_api/tests/conftest.py`) |
| `implementation_layer/solution_wizard/registries/component_reference_cards.json`, `gaik_component_registry.json` | upstream's entries for what upstream changed; keep the fork's own notes and fields (in the 0.8.10 sync: the note on the shape of VisionExtractor's `.data`) and bring them up to the new API; the audit and `test_reference_cards.py` must pass |
| `implementation_layer/solution_wizard/SKILL.md` | both, section by section |
| `implementation_layer/solution_wizard/src/`, `templates/poc/`, `scripts/scaffold_poc.py` | combine; the fork's BPMN and PoC-generation changes from sprints 1–4 are deliberate (for example "a generated PoC package actually runs"); then run the solution_wizard and wizard_api tests |
| `implementation_layer/src/gaik/` (the fork edits `software_components/vision_extractor/vision_extractor.py`) | ask the user first. If upstream now carries the same fix, take upstream's; otherwise keep the fork's edit and note that it belongs upstream |
| `implementation_layer/solution_wizard_v2/`, `wizard_api/`, `deploy/`, `gaik-aiops/`, the wizard workflows | the fork's. The plan marks upstream's commits there "wizard v2 (fork-owned)": keep each intent the fork still lacks (a CI guard, a formatting fix, a security bump), and take a lock file with the manifest it belongs to |
| `README.md`, `.gitignore` | both |
| `graphify-out/` | upstream's: it is a generated graph |

A file one side deleted and the other changed: ask the user.

A file upstream deleted and the fork left unchanged goes without a conflict; the plan's
merge preview lists these. A delivery leaves the fork's own files out of upstream, so they
come back as deletions: `GITFLOW.md`, `.github/workflows/codeql.yml` and
`.github/codeql/codeql-config.yml` (upstream uses CodeQL's default setup), and
`implementation_layer/unit_tests/test_vision_strict_schema.py` (the test of the fork's
VisionExtractor edit). Restore each before committing the merge
(`git checkout origin/develop -- <file>`) and name it in the "Conflicts:" paragraph. A
deleted upstream file the fork never changed, such as a demo file, goes as upstream decided.

A fork PR whose commits upstream already carries (a delivery took it while it was open)
merges into `develop` with a merge commit, not a squash: the commits then stay shared and
the sync has nothing to resolve there. For the sync after v0.12.0, `git merge-tree` found
seven conflicting files with fork PRs 291 and 299 squashed, and two with merge commits.

Write one line per file into the merge commit's "Conflicts:" paragraph: the file, the side
kept and why. The 0.8.10 merge (fork commit 26a64db7) is the model:

```text
Conflicts: gaik_validated_version.txt (0.8.10), pyproject.toml (upstream's
comment), component_reference_cards.json (upstream's VisionExtractor call; the
note on the shape of .data with include_verification is kept and names the
new found_in_text and page keys).
```

`pr-body` copies that paragraph into the PR's "Merge conflicts" section. Before committing,
`git diff <tag> -- <file>` should show only the fork's lines on top of upstream's version.
