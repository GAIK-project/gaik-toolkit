# Wizard Requirement Coverage

This file documents how wizard fields are covered by the frozen scripted answers and scenario-oracle checks. Update it whenever a scripted answer, required wizard field, or oracle requirement changes.

| Wizard field | Scripted answer | Oracle check |
|---|---|---|
| `business_spec.users` | SA01 | EQ1-R01 |
| `technical_spec.runtime_interface` | SA04 | EQ1-R04 |
| `poc.goal_and_acceptance` | SA05 | EQ1-R05, EQ4-E01 |

Every required wizard field should have at least one scripted source or be explicitly supplied in `initial_prompt.txt`. The JSON file is the machine-readable source; this Markdown file is its reviewer-friendly counterpart.
