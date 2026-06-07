---
name: solution-wizard
description: GAIK Solution Configuration Wizard. Guides the user from a natural-language use-case description to a validated executable blueprint (JSON), a Mermaid workflow diagram, a standards-based BPMN 2.0 visual blueprint, a runnable PoC, and a use-case documentation suite. Collects the complete requirement set with a completeness gate, reasons about each component's behaviour-changing options, selects GAIK components, and validates everything.
---

See the full implementation at: implementation_layer/solution_wizard/SKILL.md

That directory holds the authoritative skill instructions plus the component
registry, reference cards, schemas, templates, and the deterministic scripts
(`scripts/check_requirements.py`, `validate_blueprint.py`, `generate_mermaid.py`,
`generate_bpmn.py`, `generate_docs.py`, `generate_schema.py`, `scaffold_poc.py`).
Load and follow that SKILL.md exactly; run its scripts from that directory.
