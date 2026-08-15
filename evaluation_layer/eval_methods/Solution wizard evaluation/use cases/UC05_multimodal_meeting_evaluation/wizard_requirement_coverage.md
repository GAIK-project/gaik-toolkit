# Wizard Requirement Coverage

This file maps each required wizard topic to its frozen scripted answer and scenario-oracle checks. The JSON file is the machine-readable source; this table is its reviewer-friendly representation.

| Wizard field | Scripted answer | Oracle checks |
|---|---|---|
| Users, current process, and problem | SA01 | EQ1-R01 to EQ1-R05 |
| Business objective and success | SA02 | EQ1-R06 to EQ1-R08 |
| Inputs and language | SA03 | EQ1-R09 to EQ1-R14 |
| Target-output schema | SA04 | EQ1-R15 to EQ1-R27 |
| Provenance, uncertainty, and conflicts | SA05 | EQ1-R29 to EQ1-R36 |
| Human review and return path | SA06 | EQ1-R37, EQ1-R38 |
| Employee interaction and downloadable output | SA07 | EQ1-R28, EQ1-R39 |
| Security, integration, and unspecified values | SA08 | EQ1-R40, EQ1-R41, EQ1-D01, EQ1-D02 |
| Scale and service levels | SA09 | EQ1-D03 |
| PoC goal, interface, fixture, and acceptance | SA10 | EQ1-R42, EQ4-E01 to EQ4-E04 |

If a required topic is not asked about, its scripted answer is not volunteered. Questions outside this mapping receive the fixed unexpected-question response in `scripted_answers.json`.
