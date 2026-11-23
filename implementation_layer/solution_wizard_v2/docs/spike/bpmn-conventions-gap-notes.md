# BPMN conventions (#46) — gap notes (2026-07-27)

Source: GAIK modeling guide (`GAIK_BPMN_Models.docx`) + `public/bpmn/official/`.

## Implemented (generator + V2 adapter)

| Convention | Status |
|------------|--------|
| Official BPMN shapes only (bpmn-js standard) | OK |
| Lanes: Business User / GenAI / Reviewer | OK (V2 adapter participants) |
| Task naming: verb–object (from step names) | OK when steps are named well |
| `[CODE]` prefix on automated tasks | OK (+ lowercase aliases: `transcriber`→STR, `rag`→RAG, …) |
| Descriptive start/end (`Started …` / `… completed`) | OK |
| Data objects = **data** names, not task titles | OK (2026-07-27 fix) |
| Approval gateway `Approved?` + Rejected end | OK |

## Example: incident / audio pipeline (V2 → BPMN)

Steps: Record Voice → Transcribe → Extract → Review

| Element | Generated label |
|---------|-----------------|
| Lanes | Business User, GenAI, Reviewer |
| Tasks | Record Voice Description; `[STR] Transcribe Audio`; `[SE] Extract Structured Data`; Review Report |
| Data objects | Voice Note Audio; Raw Transcript; Structured JSON; Reviewed Output |
| Start / end | Started Incident reporting; Incident reporting completed |

## Remaining (not blocking code merge)

1. **PO visual sign-off** on 11 Aug demo set vs customer reference diagrams (role-specific lanes like Observer/Safety Manager are *use-case* lanes; wizard uses generic roles by design).
2. **#50** — deeper structural diff vs `Use_Case_*.bpmn` (pools, data stores, multi-lane org charts).
3. **Verb–object quality** still depends on agent/UI step names; generator does not rewrite free text.

## Code touchpoints

- `solution_wizard/v2_adapter.py` — `_infer_artifact`
- `solution_wizard/bpmn_generator.py` — `_COMPONENT_CODES`, `_data_object_label`
- `solution_wizard/bpmn_sync.py` — artifact↔step map uses synthesizer
