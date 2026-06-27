# Solution Wizard V2 — Gherkin use cases

Executable-style specifications for product review with GAIK. Each `.feature` file maps to a GitHub user story or example domain from source materials.

## Sources

| Material | Used for |
|----------|----------|
| `Simplified User Stories for an SME Solution Wizard.docx` | SME-1 … SME-10 structure and acceptance criteria |
| `configuration wizard onboarding guide.pdf` | 12-phase workflow, Gate 1–4 |
| `solution wizard example use cases.docx` (Umair) | Domain examples: maintenance, hospital, factory |
| `Solution wizard_test 20.6_chat.docx` (Dmitry) | Maintenance MMS dialogue patterns |
| Apple Jam guest description files (Dmitry) | Structured reference data example |
| Sprint board epics #3, #12, #14–15 | Sprint assignment |

## Sprint mapping

| Sprint | Feature files |
|--------|---------------|
| **Sprint 1** (17 Jun – 6 Jul 2026) | `sprint-1/US-S1-01-session-persistence.feature` |
| **Sprint 2** (7 Jul – 7 Aug 2026) | `sprint-2/SME-01` … `SME-07` |
| **Sprint 5** (proposal) | `sprint-5/SME-08-prototype.feature` |
| **Sprint 6** (proposal) | `sprint-6/SME-09-refinement.feature`, `SME-10-package.feature` |
| **Examples** (validation) | `examples/*.feature` — end-to-end domain scenarios |

## Tags

- `@sprint-N` — target sprint
- `@SME-N` / `@US-S1-01` — backlog ID
- `@gate-N` — approval gate (onboarding guide)
- `@example` — concrete domain from GAIK materials (not a separate backlog item)

## Note on SME-7 vs V1 phases

SME-7 (define output) is listed after SME-6 (workflow) in the SME document for business readability. Technically, output requirements are collected early (V1 phase 2) and schema design runs before blueprint (V1 phase 5). Scenarios reference both where relevant.
