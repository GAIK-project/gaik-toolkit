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

A fork change the delivery did not take comes back from upstream without a conflict: the
file is deleted or changed back. The plan's merge preview lists these files. For the sync
after v0.12.0 they are `GITFLOW.md`, the fork's CodeQL workflow and config (upstream uses
CodeQL's default setup), `.github/dependabot.yml` (the fork's updates to `develop`),
`CLAUDE.md`, `README.md`, the fork's notes in `gaik_component_registry.json`, a test fix in
`test_provider_scaffolding.py`, and the fork's VisionExtractor edit with its test
(`vision_extractor.py`, `test_vision_strict_schema.py`).

Keep the fork's version of each one unless upstream's now covers it. Restore it from the
merge's first parent: `git checkout HEAD -- <file>` while the merge is paused. If `prepare`
already committed a clean merge, run `git checkout HEAD^1 -- <file>`, then amend the merge
commit before the pin bump. Name each file in the "Conflicts:" paragraph. The VisionExtractor
pair is a gaik library change: ask the user first, and keep or drop the edit and its test
together, since the test imports the edit's helpers.

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
