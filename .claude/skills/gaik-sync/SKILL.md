---
name: gaik-sync
description: Audits the GAIK Solution Wizard's component registry, reference cards, and SKILL.md guidance against the installed gaik package, then proposes and applies the updates needed to keep them in sync. Use after changing gaik components (new component, renamed constructor/method, changed options, removed component, new install extra, new module) or after bumping the gaik version. Runs a deterministic introspection scan, classifies each finding, and edits only after you approve a change table.
---

# GAIK Sync — keep the Solution Wizard in step with gaik

The Solution Wizard ([implementation_layer/solution_wizard/](../../../implementation_layer/solution_wizard/)) drives PoC generation from four assets that mirror the gaik API. When gaik changes, these drift and the wizard silently produces wrong blueprints or PoCs that fail at runtime:

| Wizard asset | File | What drifts |
|---|---|---|
| Component registry | `registries/gaik_component_registry.json` | components added/removed/renamed, `input/output_artifact_types`, `supported_providers`, `subsumes`/`uses_components`, `install_extra` |
| Reference cards | `registries/component_reference_cards.json` | `import`, `construct` kwargs, `call` method, `returns`, `options` |
| Selection guidance | `SKILL.md` (Phase 5/6) | option-inference rules, subsumption rules, provider/model consistency |
| Schema constraints | `CLAUDE.md` + `SKILL.md` Phase 4 | `ExtractionRequirements.field_type` enum, Azure structured-output rules |

**Operating principle (same as the wizard itself): Python detects, the agent decides.** The scan is deterministic; mapping each finding to the right edit — and judging whether a change is intentional — is your job. Never blind-delete a finding.

This skill does **not** modify gaik. It only edits the four wizard assets above.

### Mandatory approval gate (applies in BOTH modes — never skip)

Regardless of mode, the order is always **scan → present findings → wait for approval → sync only what was approved → test**. Concretely:

1. **Always present the findings first.** After the scan (and, in discovery mode, the diff reconstruction), show the user the full change table from Phase 3 before editing anything. This holds even in informed mode where the user already named the change, and even when there is only one finding.
2. **Never edit a wizard asset until the user has approved it.** The user may approve all findings, approve a subset, amend rows, or reject. Apply (Phase 4) **only** the approved rows; leave everything else untouched.
3. **If the user approves nothing** (or there are zero findings), stop after presenting — make no edits, run no sync, change no pin.
4. Only after applying the approved subset do you run the tests and re-scan (Phase 5). Tests run against the synced changes, not before approval.

Do not batch-apply, do not "fix while scanning", and do not assume approval from the fact that the user invoked the skill. Invoking the skill authorizes the **scan and the proposal**, not the edits.

---

## Inputs

Run in one of two modes. Prefer **informed mode** when the user tells you what they changed — it is faster and avoids false positives.

- **Informed mode** — the user names the change ("I renamed `model_provider` to `provider` on LLMJudge", "I added a `diarization` option to Transcriber", "I added a new `FormUnderstander` component"). Treat that as the hypothesis and confirm it against gaik + the scan.
- **Discovery mode** — the user just says "sync the wizard" or "check what changed". Reconstruct the change set yourself from the git diff and the scan.

---

## Phase 1 — Scan (deterministic backbone)

Always start here. From the repo root:

```bash
python .claude/skills/gaik-sync/scripts/audit_registry.py --json
```

This introspects the *installed* gaik and returns structured findings. Categories:

- `version` — installed gaik vs the wizard's last-validated pin (`gaik_validated_version.txt`). Informational; it is the trigger, not a defect.
- `removed` — a reference-card `import` no longer resolves (class gone or moved).
- `api_drift` — a `construct` kwarg or `call` method no longer exists on the gaik class.
- `options` — a card `option` name is not a real constructor parameter (often it moved to a method argument, or was renamed/removed).
- `parity` — a registry component has no reference card.
- `new` — a gaik subpackage no card references (a new component family, or an internal helper to ignore).

Read the human-readable report too for a quick overview:

```bash
python .claude/skills/gaik-sync/scripts/audit_registry.py
```

The scan only sees what introspection exposes. It **cannot** see `subsumes` relationships, `install_extra` packaging, `input/output_artifact_types`, or selection semantics — those need the diff (Phase 2) and your reading of gaik source.

## Phase 2 — Reconstruct the change set

**Informed mode:** start from what the user told you. For each named change, open the relevant gaik source under [implementation_layer/src/gaik/](../../../implementation_layer/src/gaik/) and the matching card/registry entry to confirm the exact new signature, option, or path.

**Discovery mode:** find what changed in gaik since the last validated point.

```bash
# What does the wizard consider its last-validated state?
cat implementation_layer/solution_wizard/gaik_validated_version.txt 2>/dev/null

# Local source changes (when gaik is edited in-repo):
git log --oneline -15 -- implementation_layer/src/gaik/
git diff HEAD~1 -- implementation_layer/src/gaik/
```

If gaik arrived as a *dependency bump* (no local source diff), the introspection scan in Phase 1 is your only signal — lean on it and read the installed source directly via the module paths in the findings.

For every scan finding, and every diff hunk, read the actual gaik class to establish ground truth before proposing an edit. Pay special attention to changes the scan can't detect on its own:
- a component now provides a capability internally → a new `subsumes` entry (so the wizard stops adding a redundant step);
- a new `install_extra` / pip extra → registry entry + `pip_requirements` will pick it up;
- changed `input`/`output` artifact types → registry `*_artifact_types`;
- a new option that should be auto-inferred from a blueprint field (e.g. `human_review == yes`) → SKILL.md Phase 5.

## Phase 3 — Classify and propose (no edits yet)

Map every finding to a concrete edit and present a **change table** for approval. Use this exact shape (it mirrors the wizard's own Phase 11.1 change table):

```
| # | Finding | Category | File | Field / location | Current | Proposed | Confidence |
|---|---------|----------|------|------------------|---------|----------|------------|
| 1 | LLMJudge construct kwarg 'model_provider' gone | api_drift | component_reference_cards.json | LLMJudge.construct | model_provider= | provider= | high |
| 2 | parallel_transcriber subpackage untracked | new | gaik_component_registry.json + cards | new entry | (none) | add ParallelTranscriber | needs decision |
```

Rules for the table:
- One row per finding. Group obviously-related rows (a rename usually touches `construct` + `call` + an `option` + SKILL.md).
- For `new` findings, **always ask** whether it is a user-facing component to add or an internal helper to ignore — do not assume. `llm`-style provider layers are usually internal.
- For `options` findings, check whether the option moved to a *method* argument before deleting it from the card; the wizard may still need to document it, just not as a constructor option.
- Mark confidence. Anything below "high" gets an explicit question to the user before Phase 4.
- If a finding is an intentional gaik deprecation with no wizard-side equivalent, say so and propose removing the registry/card entry (and any SKILL.md reference).

**STOP here and present the table.** Do not proceed to Phase 4 until the user responds. Explicitly ask them to approve all rows, approve a subset (by number), amend, or reject. If they approve nothing, end the run cleanly with no edits.

## Phase 4 — Apply (approved rows only — requires explicit approval from Phase 3)

Edit only the four wizard assets, only the approved rows:
- `registries/gaik_component_registry.json` — add/remove/modify entries; keep `input_artifact_types`, `output_artifact_types`, `required_parameters`, `supported_providers`, `subsumes`, `install_extra` correct.
- `registries/component_reference_cards.json` — fix `import`, `construct`, `call`, `returns`, `options`; add cards for newly-tracked components.
- `SKILL.md` (Phase 5/6, and Phase 4 schema constraints if the extraction contract changed) — selection rules, option inference, subsumption, provider/model consistency.
- `CLAUDE.md` in the wizard dir — only if a schema/`field_type` constraint changed.

Keep edits surgical and in the existing JSON/markdown style. Do not reformat whole files.

### Authoring a new entry from documentation (for approved `new` findings)

When the approved finding is a **new component/module to add**, do not guess the
fields — *source* them. Introspection gives the mechanical fields; the component's
own docs give the semantic ones. Gather, in this order:

1. **Constructor + method signatures** — `inspect.signature` on the class
   (`__init__` and the primary method). Gives `required_parameters`,
   `optional_parameters`, and the card's `construct`/`call` argument names.
2. **The component's `README.md`** (under `implementation_layer/src/gaik/software_components/<component>/`)
   — gives `best_for`, `known_limitations`, `quality_tradeoffs`, and the prose for
   what the component is *for*. Do not invent these; quote/condense the README.
3. **The example script** (`implementation_layer/examples/software_components/<component>/`)
   — gives the *verified* `call` snippet, the `returns` shape, and a working
   `construct` line. The card's `call`/`returns` must match a real example, not a
   plausible-looking guess (this is the field most likely to break the scaffolded PoC).
4. **`pyproject.toml` / `setup.cfg` extras** — gives `install_extra` (the `gaik[<extra>]` name).
5. **Artifact-type mapping** — translate the Python input/output types into the
   blueprint's artifact-type vocabulary (`audio`, `video`, `text`, `transcript`,
   `document`, `image`, `structured_json`, `answer`, …), **not** raw Python types.
   Reuse the exact strings already used by sibling entries.
6. **`subsumes`** — only set this if the new component provides a capability that an
   existing component also provides (so the wizard won't add both). This is a
   semantic judgement — state your reasoning in the change table and confirm with
   the user if unsure.

**Registry entry required fields** (validated on load against
`schemas/component_registry.schema.json`): `id`, `name`, `type`,
`input_artifact_types`, `output_artifact_types`, `required_parameters`, `best_for`,
`known_limitations`, `import_path`, `source_path`, `readme_path`,
`example_script_path`. Match the shape of the nearest existing entry of the same
`type` (component vs module). For modules, also populate `uses_components`.

**Reference card required keys**: `import`, `construct`, `call`, `returns`
(+ `install_extra`, and `options` for behaviour-changing flags with `infer_from`
hints, + `subsumes` where relevant).

If any field cannot be sourced from the docs (e.g. there is no example script),
say so explicitly in your summary and mark that field as a best-effort draft for
the user to confirm — never silently fabricate `best_for`/`known_limitations`.

## Phase 5 — Verify, then update the pin

Run the wizard's own structural tests (they cross-check cards against gaik via `inspect`) plus re-scan:

```bash
cd implementation_layer/solution_wizard
python -m pytest tests/test_reference_cards.py -q
cd ../..
python .claude/skills/gaik-sync/scripts/audit_registry.py --strict   # expect exit 0 (version finding alone is OK)
```

When the only remaining finding is `version` (i.e. every defect is resolved), **record the validated version** so future runs detect the next drift:

```bash
python -c "from importlib.metadata import version; print(version('gaik'))" \
  > implementation_layer/solution_wizard/gaik_validated_version.txt
```

Report a short summary: which assets changed, which findings were intentionally ignored (and why), and the new validated version.

---

## Notes

- The scan is safe to run any time and edits nothing. Treat it as the wizard's "what changed in gaik?" probe.
- `parity` and `new` findings are decisions, not defects — they may be deliberately unsupported. `removed`/`api_drift`/`options` are almost always real and should be fixed.
- This skill complements the always-on guard `tests/test_reference_cards.py`. The tests fail loudly in CI when gaik is present; this skill is the guided remediation when they do, or a proactive check after a gaik change.
- The version pin lives next to the registries it validates (`implementation_layer/solution_wizard/gaik_validated_version.txt`); it is created/updated only after a clean verify, so it never falsely claims sync.
