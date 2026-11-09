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
| `README.md`, `.gitignore` | both |
| `graphify-out/` | upstream's: it is a generated graph |

A file one side deleted and the other changed: ask the user.

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
