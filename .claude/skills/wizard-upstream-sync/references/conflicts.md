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
| `implementation_layer/src/gaik/` (the fork edits `software_components/vision_extractor/vision_extractor.py`) | ask the user first. If upstream now carries the same fix, take upstream's; otherwise keep the fork's edit and note that it belongs upstream. Upstream PR 364 carries the VisionExtractor fix (decided with the user on 27 Nov 2026): from the release that has it, take upstream's `vision_extractor.py` and `unit_tests/test_vision_strict_schema.py` |
| `implementation_layer/solution_wizard_v2/`, `wizard_api/`, `deploy/`, `gaik-aiops/`, the wizard workflows | the fork's. The plan marks upstream's commits there "wizard v2 (fork-owned)": keep each intent the fork still lacks (a CI guard, a formatting fix, a security bump), and take a lock file with the manifest it belongs to |
| `GITFLOW.md`, `.github/dependabot.yml`, `.github/workflows/codeql.yml`, `.github/codeql/` | each repository keeps its own: the fork's branch model, its Dependabot updates to `develop`, and its CodeQL workflow (upstream uses CodeQL's default setup, and ad63ba6c keeps the CodeQL files out). A sync keeps the fork's, also when upstream deleted the file; a delivery keeps upstream's `dependabot.yml` and leaves the other files out |
| `README.md`, `.gitignore` | both |
| `graphify-out/` | upstream's: it is a generated graph |

A file one side deleted and the other changed: ask the user, except for the files the table
says each repository keeps its own.

A clean merge can still undo fork work. When a delivery kept upstream's version of a fork
change or left a fork file out, the next sync changes the fork's file back or deletes it
without a conflict. The plan's merge preview lists every file where the fork has its own
version (against the upstream commit it last took in) and the merge changes it, deletes it
or adds it back without a conflict; `prepare` then stops before committing. For the sync
after v0.12.0 the list includes `GITFLOW.md` and the fork's CodeQL workflow and config
(deleted; upstream uses CodeQL's default setup), `.github/dependabot.yml` (the fork's
updates to `develop`) and the fork's VisionExtractor edit with its test.

Read each one's diff from the fork (`git diff HEAD -- <file>` in the paused merge) and keep
the fork's lines it still wants; upstream's own changes in the same file stay. A file only
the fork has can come back whole: `git checkout HEAD -- <file>`. In a file upstream also
has, put back only the fork's change, for example `git diff <last-taken> HEAD -- <file> |
git apply -3` with the upstream commit the preview names; a whole-file checkout would undo
upstream's fixes there. Name each file in the "Conflicts:" paragraph. The VisionExtractor
pair is a gaik library change, settled in the table above: keep or drop the edit and its
test together, since the fork's test imports the edit's helpers.

A fork PR whose commits upstream already carries (a delivery took it while it was open)
merges into `develop` with a merge commit, not a squash: the commits then stay shared, and
the sync has less to resolve. Fork PRs 291 and 299 are such PRs after the v0.12.0 delivery.

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
