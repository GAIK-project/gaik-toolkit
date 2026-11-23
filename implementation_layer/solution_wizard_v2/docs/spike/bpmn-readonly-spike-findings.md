# F2 iter 1 — BPMN read-only spike findings (#40)

**Sprint 1 spike** for epic [#13 — Interactive BPMN + JSON sync](https://github.com/perttiy/gaik-toolkit-configuration-wizard-v2/issues/13).  
**Scope:** evaluate viewers, integrate read-only preview in the Workflow tab. No editing, no JSON↔BPMN sync.

---

## Architecture (GAIK path)

```
User chat / requirements
  → V1 agent builds blueprint JSON (source of truth)
  → solution_wizard/bpmn_generator.py → workflow.bpmn (BPMN 2.0 XML)
  → V2 UI (bpmn-js) renders read-only diagram
```

BPMN is **derived**, never hand-edited. The V1 generator already targets bpmn-js, Camunda Modeler, and draw.io (see `bpmn_generator.py` docstring).

**Not in scope for GAIK:** LLM text→BPMN pipelines (research papers in local `docs/26.6 statuscheck/BPMN/`). We use rule-based generation from structured blueprint JSON.

---

## Editor / viewer comparison

| Option | Read-only | Edit (Sprint 2+) | BPMN 2.0 | React/Next fit | Notes |
|--------|-----------|------------------|----------|----------------|-------|
| **bpmn-js NavigatedViewer** | ✅ | — (use Modeler for edit) | ✅ | ✅ dynamic import | `bpmn-js/lib/NavigatedViewer` — pan/zoom, no palette. Same family as bpmn.io. **Recommended.** |
| **bpmn-js Modeler** | ✅ | ✅ | ✅ | ✅ | Full editing; needed for F2 iter 2 / #34. Heavier bundle; defer to Sprint 2. |
| **bpmn.io (hosted)** | ✅ | ✅ | ✅ | iframe | External dependency, branding, no offline/Docker story. |
| **Camunda Modeler (desktop)** | ✅ | ✅ | ✅ | ❌ | Good for SME review export; not embeddable in web UI. |
| **draw.io / diagrams.net** | ✅ | ✅ | partial | iframe | Generic diagram editor; weaker BPMN semantics than bpmn-js. |
| **Custom SVG / Mermaid** | ✅ | ❌ | ❌ | ✅ | Would duplicate V1 generator; loses BPMN 2.0 interchange. |

**Recommendation:** **bpmn-js** (`NavigatedViewer` now, `Modeler` in Sprint 2). Aligns with V1 XML output, Camunda ecosystem, and future interactive editing (#34, #13).

---

## Spike implementation (this branch)

| Piece | Location |
|-------|----------|
| Pre-generated sample XML | `public/bpmn/incident-reporting.bpmn` (from V1 `incident_reporting_blueprint.json` via `generate_bpmn.py`) |
| API | `GET /api/sessions/[id]/bpmn` — serves XML for spike sessions only |
| Viewer | `components/bpmn-viewer.tsx` — client-side `NavigatedViewer`, fit-viewport |
| Workflow tab | `components/workspace-panel.tsx` — BPMN + collapsible mock step list |
| Session gate | `lib/bpmn-spike.ts` — `ses_chatbot`, `ses_laskut` |
| Phase gate | **Step ≥ 8** only (`BPMN_VISUAL_STEP` / onboarding phase “Visuaalinen työnkulku”) — before that, Workflow tab shows the text step list |

Other mock sessions keep the step-list placeholder until Sprint 2 wires active blueprint → generator.

---

## Risks & follow-ups

1. **Bundle size** — bpmn-js is ~200 KB+ gzipped; acceptable for wizard workspace; use dynamic import (done).
2. **Blueprint shape** — V2 mock blueprint is simplified; production path (#34) must use full V1 blueprint from API/storage.
3. **Regeneration** — when blueprint changes, re-run `generate_bpmn()` server-side; UI refetches XML (no client-side generation).
4. **Interactive editing** — out of Sprint 1; Modeler + JSON sync is E2 / Sprint 3–4.

---

## Acceptance (#40 checklist)

- [x] Workflow tab shell (#1)
- [x] Read-only bpmn-js preview on Workflow tab
- [x] Editor comparison / recommendation (this document)
- [x] Spike findings for #13 input

**Next (Sprint 2, #34):** session active blueprint → API generates BPMN on demand; remove hard-coded spike asset map.

---

## Sprint 2 update (2026-07-11) — V2 BPMN started

| Change | Status |
|--------|--------|
| Official BPMN 2.0 reference XML (customer `6.7_demo` set) in `public/bpmn/official/` | ✅ |
| Native bpmn-js rendering (`rendererMode: standard`) — no custom GAIK shapes | ✅ |
| Inline diagram on Workflow tab (no full-screen modal) | ✅ |
| bpmn-js Modeler + save (canvas → JSON → regenerate BPMN) | ✅ |
| Dynamic BPMN from session blueprint (V1 `generate_bpmn` via adapter) | ✅ |
| `PATCH /sessions/{id}/blueprint` + `POST /sessions/{id}/bpmn/sync` (wizard_api) | ✅ |

**Still open (Sprint 2–3):** bpmnlint validation before save; gateway/artifact round-trip into full V1 artifact model (V2 stores data-object label edits under `data_objects` only).

### Sprint 2+ update (2026-07-12) — conventions + deeper sync

| Change | Status |
|--------|--------|
| Generator follows official naming (verb-object, `[CODE]` prefix, GenAI lane, human data objects, descriptive start/end) | ✅ |
| V2 adapter synthesizes artifacts + GenAI/Business User/Reviewer lanes | ✅ |
| V2 data objects use guide-style data names (Audio/Transcript/JSON), not task titles (2026-07-27) | ✅ |
| Component code aliases for lowercase UI ids (`transcriber`→STR, `rag`→RAG, …) | ✅ |
| Sync: Activity_↔step id mapping, rename/reorder/add/remove, documentation→description, data-object labels | ✅ |
| Properties panel (name / type / id) beside Modeler canvas | ✅ |
| bpmnlint before save | ✅ (#47 — Next sync route + UI; `lib/bpmn-lint.ts`) |
| Gateway snapshot on sync (`gateways[]`) | ✅ partial (#48 — labels persisted; topology still regenerated) |
| Reference comparison doc (#50) | ✅ `docs/spike/bpmn-reference-comparison-2026-07-27.md` |
